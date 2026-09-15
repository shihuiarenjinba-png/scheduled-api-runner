from __future__ import annotations

import argparse
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
from typing import Any


class RunnerError(RuntimeError):
    pass


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
        self.allowed_hosts = {str(x).lower() for x in self.config.get("allow_hosts", [])}
        self.poll_seconds = max(float(self.config.get("poll_seconds", 10)), 1.0)
        self.state_db = self._path(str(self.config.get("state_db", ".state/scheduler.sqlite3")))
        self.log_path = self._path(str(self.config.get("log_path", "logs/api.jsonl")))
        self.jobs = self.config.get("jobs", [])
        if not self.allowed_hosts:
            raise RunnerError("allow_hosts must not be empty")
        if not isinstance(self.jobs, list) or not self.jobs:
            raise RunnerError("jobs must be a non-empty list")
        if not self.dry_run:
            self.root.mkdir(parents=True, exist_ok=True)
            self.state_db.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.state_db) as con:
                con.execute("CREATE TABLE IF NOT EXISTS run_keys (run_key TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")

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

    def log(self, event: dict[str, Any]) -> None:
        row = {"ts": datetime.now().astimezone().isoformat(), **event}
        print(json.dumps(row, ensure_ascii=False))
        if self.dry_run:
            return
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _claim(self, run_key: str) -> bool:
        if self.dry_run:
            return True
        try:
            with sqlite3.connect(self.state_db) as con:
                con.execute("INSERT INTO run_keys(run_key) VALUES (?)", (run_key,))
            return True
        except sqlite3.IntegrityError:
            return False

    def _schedule_key(self, job: dict[str, Any], now: datetime) -> str | None:
        schedule = job.get("schedule", {})
        schedule_type = schedule.get("type")
        name = str(job.get("name", "unnamed"))
        if schedule_type == "daily":
            at = str(schedule.get("at", ""))
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
        url = str(request_cfg["url"])
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            raise RunnerError("Only HTTPS URLs are allowed")
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
        timeout = float(request_cfg.get("timeout_seconds", 30))
        retries = max(int(job.get("retries", 0)), 0)
        retry_wait = max(float(job.get("retry_wait_seconds", 2)), 0.0)

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    body = response.read(1_000_000)
                    self.log({"event": "request_ok", "job": job.get("name"), "status": response.status, "bytes": len(body)})
                    return
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                self.log({"event": "request_error", "job": job.get("name"), "attempt": attempt + 1, "error": str(exc)})
                if attempt < retries:
                    time.sleep(retry_wait)
        raise RunnerError(f"Request failed after retries: {last_error}")

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
            if run_key and self._claim(run_key):
                self.run_job(job)

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
