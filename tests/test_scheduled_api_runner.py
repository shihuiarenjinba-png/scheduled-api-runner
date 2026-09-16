from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from scheduled_api_runner import RunnerError, ScheduledRunner, _RejectRedirectHandler


class _RedirectingOpener:
    def open(self, request, timeout=30):
        raise urllib.error.HTTPError(request.full_url, 302, "Found", {"Location": "https://evil.example/"}, None)


def config(root: Path) -> dict:
    return {
        "root_dir": str(root),
        "allow_hosts": ["allowed.example"],
        "state_db": ".state/scheduler.sqlite3",
        "log_path": "logs/api.jsonl",
        "failure_retry_seconds": 1,
        "running_stale_seconds": 60,
        "jobs": [
            {
                "name": "sample",
                "enabled": True,
                "schedule": {"type": "interval", "seconds": 60},
                "request": {"method": "GET", "url": "https://allowed.example/data"},
            }
        ],
    }


class ScheduledRunnerTests(unittest.TestCase):
    def test_redirect_handler_never_follows(self) -> None:
        handler = _RejectRedirectHandler()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))

    def test_request_rejects_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = ScheduledRunner(config(Path(tmp)))
            with patch("scheduled_api_runner.urllib.request.build_opener", return_value=_RedirectingOpener()):
                with self.assertRaisesRegex(RunnerError, "redirect_rejected"):
                    runner._request(config(Path(tmp))["jobs"][0])

    def test_failed_run_is_retryable_but_success_is_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = ScheduledRunner(config(Path(tmp)))
            key = "sample|interval|60|1"
            self.assertTrue(runner._begin_run(key))
            runner._finish_run(key, success=False, error="failure")
            self.assertFalse(runner._begin_run(key))

            with runner._connect() as con:
                con.execute("UPDATE runs SET updated_at=? WHERE run_key=?", (time.time() - 2, key))
            self.assertTrue(runner._begin_run(key))
            runner._finish_run(key, success=True)
            self.assertFalse(runner._begin_run(key))

    def test_legacy_claims_migrate_as_succeeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".state" / "scheduler.sqlite3"
            state.parent.mkdir(parents=True)
            with sqlite3.connect(state) as con:
                con.execute("CREATE TABLE run_keys (run_key TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
                con.execute("INSERT INTO run_keys(run_key) VALUES ('legacy-key')")
            runner = ScheduledRunner(config(root))
            self.assertFalse(runner._begin_run("legacy-key"))

    def test_url_userinfo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = ScheduledRunner(config(Path(tmp)), dry_run=True)
            job = {"name": "bad", "request": {"url": "https://user:pass@allowed.example/path"}}
            with self.assertRaisesRegex(RunnerError, "userinfo"):
                runner._request(job)


if __name__ == "__main__":
    unittest.main()
