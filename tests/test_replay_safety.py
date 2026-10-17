"""Regression tests for ambiguous outcomes and duplicate API execution."""
from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from scheduled_api_runner import RunnerError, ScheduledRunner


def configuration(root: Path, method: str = "POST") -> dict:
    return {
        "root_dir": str(root),
        "allow_hosts": ["allowed.example"],
        "failure_retry_seconds": 1,
        "running_stale_seconds": 60,
        "jobs": [
            {
                "name": "export",
                "enabled": True,
                "retries": 3,
                "schedule": {"type": "interval", "seconds": 60},
                "request": {"url": "https://allowed.example/task", "method": method},
            }
        ],
    }


class AlwaysFailOpener:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, request, timeout=30):
        self.calls += 1
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)


class Response:
    status = 200

    def __init__(self, url: str) -> None:
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int) -> bytes:
        return b"ok"

    def geturl(self):
        return self.url


class FailThenSucceedOpener:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, request, timeout=30):
        self.calls += 1
        if self.calls == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)
        return Response(request.full_url)


class ApiReplaySafetyTests(unittest.TestCase):
    def test_mutating_http_error_never_auto_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            config = configuration(Path(temp), method="POST")
            runner = ScheduledRunner(config)
            opener = AlwaysFailOpener()
            with patch("scheduled_api_runner.urllib.request.build_opener", return_value=opener):
                with patch("scheduled_api_runner.time.sleep") as sleep:
                    with contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(RunnerError, "http_503"):
                            runner._request(config["jobs"][0])
            self.assertEqual(opener.calls, 1)
            sleep.assert_not_called()

    def test_patch_and_delete_also_use_single_attempt(self):
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temp:
                config = configuration(Path(temp), method=method)
                runner = ScheduledRunner(config)
                opener = AlwaysFailOpener()
                with patch("scheduled_api_runner.urllib.request.build_opener", return_value=opener):
                    with contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaises(RunnerError):
                            runner._request(config["jobs"][0])
                self.assertEqual(opener.calls, 1)

    def test_get_can_retry_after_temporary_http_error(self):
        with tempfile.TemporaryDirectory() as temp:
            config = configuration(Path(temp), method="GET")
            runner = ScheduledRunner(config)
            opener = FailThenSucceedOpener()
            with patch("scheduled_api_runner.urllib.request.build_opener", return_value=opener):
                with patch("scheduled_api_runner.time.sleep"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        runner._request(config["jobs"][0])
            self.assertEqual(opener.calls, 2)

    def test_failed_post_slot_is_uncertain_and_not_reclaimed(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = ScheduledRunner(configuration(Path(temp)))
            key = "export|interval|60|123"
            with patch.object(runner, "_schedule_key", return_value=key):
                with patch.object(runner, "_request", side_effect=RunnerError("timeout")) as req:
                    with contextlib.redirect_stdout(io.StringIO()):
                        runner.run_due()
                        runner.run_due()
            req.assert_called_once()
            with runner._connect() as con:
                row = con.execute("SELECT status, last_error FROM runs WHERE run_key=?", (key,)).fetchone()
            self.assertEqual(row, ("uncertain", "RunnerError"))

    def test_stale_running_post_never_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = ScheduledRunner(configuration(Path(temp)))
            key = "export|interval|60|456"
            self.assertTrue(runner._begin_run(key, retry_allowed=False))
            with runner._connect() as con:
                con.execute("UPDATE runs SET updated_at=0 WHERE run_key=?", (key,))
            self.assertFalse(runner._begin_run(key, retry_allowed=False))

    def test_unknown_outcome_blocks_get_recovery_too(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = ScheduledRunner(configuration(Path(temp), "GET"))
            key = "export|interval|60|789"
            self.assertTrue(runner._begin_run(key))
            runner._finish_run(key, success=False, error="unknown", uncertain=True)
            self.assertFalse(runner._begin_run(key))

    def test_duplicate_job_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = configuration(Path(temp))
            cfg["jobs"].append(dict(cfg["jobs"][0]))
            with self.assertRaisesRegex(RunnerError, "Duplicate job name"):
                ScheduledRunner(cfg, dry_run=True)

    def test_empty_job_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = configuration(Path(temp))
            cfg["jobs"][0]["name"] = " "
            with self.assertRaisesRegex(RunnerError, "non-empty name"):
                ScheduledRunner(cfg, dry_run=True)

    def test_dry_run_does_not_create_state_db_or_send_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = ScheduledRunner(configuration(root), dry_run=True)
            with patch("scheduled_api_runner.urllib.request.build_opener") as opener:
                with contextlib.redirect_stdout(io.StringIO()):
                    runner.run_due()
            opener.assert_not_called()
            self.assertFalse((root / ".state").exists())

    def test_sqlite_connection_closes_after_context(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = ScheduledRunner(configuration(Path(temp)))
            with runner._connect() as con:
                con.execute("SELECT 1")
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
