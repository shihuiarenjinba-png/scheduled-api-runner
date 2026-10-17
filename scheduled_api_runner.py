from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


class RunnerError(RuntimeError):
    pass


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so allowlisted requests cannot escape to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def resolve_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${ENV:") and value.endswith("}"):
        name = value[6:-1]
        result = os.getenv(name)
        if result is None:
            raise RunnerError(f"Missing environment variable: {name}")
        return result
    if isinstance(value, list):
        return [resolve_env(v) for v in value]
    if isinstance(value, dict):
        return {k: resolve_env(v) for k, v in value.items()}
    return value


class ScheduledRunner:
    def __init__(self, config: dict[str, Any], dry_run: bool = False) -> None:
        self.config = resolve_env(config)
        self.dry_run = dry_run
        self.root = Path(self.config.get("root_dir", ".")).expanduser().resolve()
        self.allowed_hosts = {str(x).strip().lower() for x in self.config.get("allow_hosts", []) if str(x).strip()}
        self.poll_seconds = min(max(float(self.config.get("poll_seconds", 10)), 1.0), 3600.0)
        self.failure_retry_seconds = min(max(float(self.config.get("failure_retry_seconds", 30)), 1.0), 3600.0)
        self.running_stale_seconds = min(max(float(self.config.get("running_stale_seconds", 600)), 60.0), 86400.0)
        self.state_db = self._path(str(self.config.get("state_db", ".state/scheduler.sqlite3")))
        self.log_path = self._path(str(self.config.get("log_path", "logs/api.jsonl")))
        self.jobs = self.config.get("jobs", [])
        if not self.allowed_hosts:
            raise RunnerError("allow_hosts must not be empty")
        if not isinstance(self.jobs, list) or not self.jobs:
            raise RunnerError("jobs must be a non-empty list")
        names: set[str] = set()
        for job in self.jobs:
            if not isinstance(job, dict):
                raise RunnerError("Each job must be an object")
            name = job.get("name")
            if not isinstance(name, str) or not name.strip():
                raise RunnerError("Every job needs a non-empty name")
            if name in names:
                raise RunnerError(f"Duplicate job name: {name}")
            names.add(name)
        if not self.dry_run:
            self.root.mkdir(parents=True, exist_ok=True)
            self.state_db.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_state_db()

    def _path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise RunnerError(f"Path is outside root_dir: {path}") from exc
        return path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.state_db, timeout=5.0)
        try:
            con.execute("PRAGMA busy_timeout=5000")
            with con:
                yield con
        finally:
            con.close()

    def _init_state_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            legacy = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_keys'"
            ).fetchone()
            if legacy:
                now = time.time()
                con.execute(
                    """
                    INSERT OR IGNORE INTO runs(run_key, status, updated_at, last_error)
                    SELECT run_key, 'succeeded', ?, '' FROM run_keys
                    """,
                    (now,),
                )

    def log(self, event: dict[str, Any]) -> None:
        row = {"ts": datetime.now().astimezone().isoformat(), **event}
        print(json.dumps(row, ensure_ascii=False))
        if self.dry_run:
            return
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_only(job: dict[str, Any]) -> bool:
        request = job.get("request", {})
        return isinstance(request, dict) and str(request.get("method", "GET")).upper() == "GET"

    def _begin_run(self, run_key: str, *, retry_allowed: bool = True) -> bool:
        if self.dry_run:
            return True
        now = time.time()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status, updated_at FROM runs WHERE run_key=?", (run_key,)).fetchone()
            if row is not None:
                status = str(row[0])
                age = max(now - float(row[1]), 0.0)
                # Mutating requests may have completed remotely even when
                # their local outcome is unknown. Never reclaim their slot.
                if status in {"succeeded", "uncertain"} or not retry_allowed:
                    return False
                if status == "running" and age < self.running_stale_seconds:
                    return False
                if status == "failed" and age < self.failure_retry_seconds:
                    return False
            con.execute(
                """
                INSERT INTO runs(run_key, status, updated_at, last_error)
                VALUES(?, 'running', ?, '')
                ON CONFLICT(run_key) DO UPDATE SET status='running', updated_at=excluded.updated_at, last_error=''
                """,
                (run_key, now),
            )
            return True

    def _finish_run(self, run_key: str, *, success: bool, error: str = "", uncertain: bool = False) -> None:
        if self.dry_run:
            return
        with self._connect() as con:
            con.execute(
                "UPDATE runs SET status=?, updated_at=?, last_error=? WHERE run_key=?",
                ("succeeded" if success else ("uncertain" if uncertain else "failed"), time.time(), str(error)[:1000], run_key),
            )

    def _schedule_key(self, job: dict[str, Any], now: datetime) -> str | None:
        schedule = job.get("schedule", {})
        if not isinstance(schedule, dict):
            raise RunnerError("schedule must be an object")
        schedule_type = schedule.get("type")
        name = str(job.get("name", "unnamed"))
        if schedule_type == "daily":
            at = str(schedule.get("at", ""))
            try:
                datetime.strptime(at, "%H:%M")
            except ValueError as exc:
                raise RunnerError(f"Invalid daily time for {name}: {at}") from exc
            if now.strftime("%H:%M") != at:
                return None
            return f"{name}|daily|{now.strftime('%Y-%m-%d')}|{at}"
        if schedule_type == "interval":
            seconds = int(schedule.get("seconds", 0))
            if seconds < 60:
                raise RunnerError("interval seconds must be at least 60")
            bucket = int(now.timestamp()) // seconds
            return f"{name}|interval|{seconds}|{bucket}"
        raise RunnerError(f"Unsupported schedule type for {name}: {schedule_type}")

    def _request(self, job: dict[str, Any]) -> None:
        request_cfg = job.get("request", {})
        if not isinstance(request_cfg, dict):
            raise RunnerError("request must be an object")
        url = str(request_cfg["url"])
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            raise RunnerError("Only HTTPS URLs are allowed")
        if parsed.username or parsed.password:
            raise RunnerError("Credentials in URL userinfo are not allowed")
        if parsed.fragment:
            raise RunnerError("URL fragments are not allowed")
        if host not in self.allowed_hosts:
            raise RunnerError(f"Host is not allowed: {host}")

        method = str(request_cfg.get("method", "GET")).upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise RunnerError(f"Unsupported HTTP method: {method}")
        if self.dry_run:
            self.log({"event": "dry_run_request", "job": job.get("name"), "method": method, "host": host})
            return

        headers = {str(k): str(v) for k, v in request_cfg.get("headers", {}).items()}
        data = None
        if "json" in request_cfg:
            data = json.dumps(request_cfg["json"]).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        timeout = min(max(float(request_cfg.get("timeout_seconds", 30)), 1.0), 300.0)
        retries = min(max(int(job.get("retries", 0)), 0), 10)
        if method != "GET" and retries:
            # A timeout/HTTP error does not prove that a POST/PATCH/etc
            # failed remotely. A blind retry can duplicate a real operation.
            self.log({"event": "mutating_retry_blocked", "job": job.get("name"),
                      "method": method, "configured_retries": retries})
            retries = 0
        retry_wait = min(max(float(job.get("retry_wait_seconds", 2)), 0.0), 60.0)
        opener = urllib.request.build_opener(_RejectRedirectHandler())

        last_error = "request_failed"
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with opener.open(req, timeout=timeout) as response:
                    final = urllib.parse.urlparse(response.geturl())
                    final_host = (final.hostname or "").lower()
                    if final.scheme != "https" or final_host != host:
                        raise RunnerError("HTTP response URL changed unexpectedly")
                    body = response.read(1_000_000)
                    self.log({"event": "request_ok", "job": job.get("name"), "status": response.status, "host": host, "bytes": len(body)})
                    return
            except urllib.error.HTTPError as exc:
                if 300 <= exc.code < 400:
                    last_error = "redirect_rejected"
                    self.log({"event": "request_error", "job": job.get("name"), "attempt": attempt + 1, "error": last_error, "status": exc.code, "host": host})
                    break
                last_error = f"http_{exc.code}"
                self.log({"event": "request_error", "job": job.get("name"), "attempt": attempt + 1, "error": last_error, "host": host})
            except urllib.error.URLError as exc:
                last_error = "network_error"
                self.log({"event": "request_error", "job": job.get("name"), "attempt": attempt + 1, "error": last_error, "reason_type": type(exc.reason).__name__, "host": host})
            except TimeoutError:
                last_error = "timeout"
                self.log({"event": "request_error", "job": job.get("name"), "attempt": attempt + 1, "error": last_error, "host": host})
            if attempt < retries:
                time.sleep(retry_wait)
        raise RunnerError(f"Request failed: {last_error}")

    def run_job(self, job: dict[str, Any]) -> None:
        if job.get("enabled", True) is False:
            return
        self.log({"event": "job_start", "job": job.get("name")})
        self._request(job)
        self.log({"event": "job_ok", "job": job.get("name")})

    def run_due(self) -> None:
        now = datetime.now().astimezone()
        for job in self.jobs:
            if job.get("enabled", True) is False:
                continue
            run_key = self._schedule_key(job, now)
            if not run_key:
                continue
            read_only = self._read_only(job)
            if not self._begin_run(run_key, retry_allowed=read_only):
                continue
            try:
                self.run_job(job)
            except (RunnerError, OSError, ValueError) as exc:
                self._finish_run(run_key, success=False, error=type(exc).__name__,
                                 uncertain=not read_only)
                self.log({"event": "scheduled_job_uncertain" if not read_only else "scheduled_job_failed",
                          "job": job.get("name"), "error": type(exc).__name__,
                          "auto_retry": read_only})
                continue
            self._finish_run(run_key, success=True)

    def run_all_once(self) -> None:
        for job in self.jobs:
            self.run_job(job)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduled HTTPS API runner")
    parser.add_argument("config", type=Path)
    parser.add_argument("--once", action="store_true", help="Run enabled jobs once, ignoring their schedules")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        runner = ScheduledRunner(config, dry_run=args.dry_run)
        if args.once:
            runner.run_all_once()
            return 0
        while True:
            runner.run_due()
            time.sleep(runner.poll_seconds)
    except KeyboardInterrupt:
        return 0
    except (OSError, json.JSONDecodeError, KeyError, ValueError, RunnerError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
