"""Opt-in Windows Task Scheduler registration for a single dated GET API job.

Never modify another task, auto-register on installation, or run HTTP on setup.
Changing a saved JSON requires explicit re-registration: SHA-256 is pinned in
the scheduled command. This is an interactive-logon task, not a cloud service.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime


class WindowsTaskError(ValueError):
    pass


def _is_windows() -> bool:
    return os.name == "nt"


def task_name(config_path: Path) -> str:
    path = str(config_path.expanduser().resolve())
    return "ScheduledApiRunner_" + hashlib.sha256(path.casefold().encode("utf-8")).hexdigest()[:16]


def validate_dated_get_config(config: dict) -> str:
    """A single daily read-only GET job can run unattended. No POST/PUT etc."""
    if not isinstance(config, dict) or not isinstance(config.get("jobs"), list):
        raise WindowsTaskError("Task config must have a jobs list")
    jobs = [job for job in config["jobs"] if isinstance(job, dict) and job.get("enabled", True)]
    if len(jobs) != 1 or len(config["jobs"]) != 1:
        raise WindowsTaskError("Create one Windows task per single enabled GET job")
    job = jobs[0]
    request = job.get("request", {})
    schedule = job.get("schedule", {})
    if (not isinstance(request, dict) or request.get("method", "GET").upper() != "GET"
            or not isinstance(schedule, dict) or schedule.get("type") != "daily"
            or "csv_update" not in job):
        raise WindowsTaskError("Windows scheduling supports dated CSV GET-only jobs")
    from api_series_store import validate_writer, SeriesError
    try:
        validate_writer(job["csv_update"], Path(config["root_dir"]))
    except (SeriesError, KeyError, ValueError) as exc:
        raise WindowsTaskError("Unsafe CSV output configuration") from exc
    time_value = str(schedule.get("at", ""))
    try:
        at = datetime.strptime(time_value, "%H:%M")
        if time_value != at.strftime("%H:%M"):
            raise ValueError()
    except ValueError as exc:
        raise WindowsTaskError("Daily schedule must use HH:MM") from exc
    return time_value


def _command(config_path: Path, expected_sha256: str) -> str:
    path = str(config_path.expanduser().resolve())
    if getattr(sys, "frozen", False):
        argv = [str(Path(sys.executable).resolve()), "--run-locked",
                path, expected_sha256]
    else:
        launcher = Path(__file__).resolve().parent / "desktop_app.py"
        argv = [str(Path(sys.executable).resolve()), str(launcher),
                "--run-locked", path, expected_sha256]
    return subprocess.list2cmdline(argv)


def build_register_command(path: Path, content: bytes) -> list[str]:
    try:
        cfg = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WindowsTaskError("Config must be valid UTF-8 JSON") from exc
    when = validate_dated_get_config(cfg)
    checksum = hashlib.sha256(content).hexdigest()
    cmd = _command(path, checksum)
    if len(cmd) > 240:
        raise WindowsTaskError("Windows scheduler command is too long; use a shorter config path")
    return ["schtasks", "/Create", "/TN", task_name(path),
            "/TR", cmd, "/SC", "DAILY", "/ST", when,
            "/RL", "LIMITED", "/IT"]


def _execute(args: list[str]) -> None:
    if not _is_windows():
        raise WindowsTaskError("Windows Task Scheduler is available only on Windows")
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=25, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WindowsTaskError("Could not contact Windows Task Scheduler") from exc
    if result.returncode != 0:
        # Do not echo command path or JSON credentials from subprocess output.
        raise WindowsTaskError("Windows rejected task registration or removal; inspect Task Scheduler")


def register_task(config_path: Path) -> str:
    if not _is_windows():
        raise WindowsTaskError("Use this feature on Windows")
    path = config_path.expanduser().resolve()
    if not path.is_file():
        raise WindowsTaskError("Save the task JSON before registration")
    args = build_register_command(path, path.read_bytes())
    # No /F: refuse existing tasks rather than silently replacing them.
    _execute(args)
    return task_name(path)


def unregister_task(config_path: Path) -> str:
    if not _is_windows():
        raise WindowsTaskError("Use this feature on Windows")
    name = task_name(config_path)
    # Deletion of exactly the path-derived task name requires a GUI consent.
    _execute(["schtasks", "/Delete", "/TN", name, "/F"])
    return name


def run_locked_config(config_path: Path, expected_sha256: str) -> int:
    """One scheduled invocation; refuse changed configuration before API GET."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in expected_sha256):
        raise WindowsTaskError("Invalid pinned config digest")
    content = config_path.expanduser().resolve().read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise WindowsTaskError("API configuration changed after task registration; re-register it")
    try:
        cfg = json.loads(content.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise WindowsTaskError("Invalid scheduled task JSON") from exc
    validate_dated_get_config(cfg)
    from scheduled_api_runner import ScheduledRunner
    result = ScheduledRunner(cfg, dry_run=False).run_due()
    return 1 if result else 0
