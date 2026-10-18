"""Explicit per-user Windows Task Scheduler registration for daily CSV jobs.

No elevated privileges, passwords, credentials or hidden background service.
The scheduled task executes the saved JSON once at its local daily time.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


class TaskError(RuntimeError):
    pass


NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", NS)


def _tag(name: str) -> str:
    return "{" + NS + "}" + name


def validate_job(path: Path) -> tuple[str, str]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        jobs = config["jobs"]
        if len(jobs) != 1 or not isinstance(jobs[0], dict):
            raise TaskError("A scheduled task requires exactly one job")
        job = jobs[0]
        name = job["name"]
        at = job["schedule"]["at"]
        if job["schedule"]["type"] != "daily":
            raise TaskError("Only daily schedules are supported")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,50}", name):
            raise TaskError("Invalid job name")
        if not isinstance(at, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
            raise TaskError("Invalid daily HH:MM")
        return "ScheduledApiRunner-" + name, at
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise TaskError("Invalid saved job settings") from exc


def task_xml(at: str, executable: str, script: str, config: str,
             *, today: str | None = None, username: str | None = None) -> bytes:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
        raise TaskError("Invalid daily HH:MM")
    today = today or datetime.now().strftime("%Y-%m-%d")
    username = username or os.environ.get("USERNAME", "")
    if not username:
        raise TaskError("Cannot determine Windows user")
    domain = os.environ.get("USERDOMAIN", "")
    if "\\" not in username and domain:
        username = domain + "\\" + username
    root = ET.Element(_tag("Task"), {"version": "1.4"})
    registration = ET.SubElement(root, _tag("RegistrationInfo"))
    ET.SubElement(registration, _tag("Description")).text = "User-approved local daily HTTPS API CSV update"
    triggers = ET.SubElement(root, _tag("Triggers"))
    calendar = ET.SubElement(triggers, _tag("CalendarTrigger"))
    ET.SubElement(calendar, _tag("StartBoundary")).text = today + "T" + at + ":00"
    ET.SubElement(calendar, _tag("Enabled")).text = "true"
    by_day = ET.SubElement(calendar, _tag("ScheduleByDay"))
    ET.SubElement(by_day, _tag("DaysInterval")).text = "1"
    principals = ET.SubElement(root, _tag("Principals"))
    principal = ET.SubElement(principals, _tag("Principal"), {"id": "Author"})
    ET.SubElement(principal, _tag("UserId")).text = username
    ET.SubElement(principal, _tag("LogonType")).text = "InteractiveToken"
    ET.SubElement(principal, _tag("RunLevel")).text = "LeastPrivilege"
    settings = ET.SubElement(root, _tag("Settings"))
    for key, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("DisallowStartIfOnBatteries", "false"),
        ("StopIfGoingOnBatteries", "false"),
        ("StartWhenAvailable", "true"),
        ("ExecutionTimeLimit", "PT1H"),
        ("Enabled", "true"),
    ):
        ET.SubElement(settings, _tag(key)).text = value
    actions = ET.SubElement(root, _tag("Actions"), {"Context": "Author"})
    action = ET.SubElement(actions, _tag("Exec"))
    ET.SubElement(action, _tag("Command")).text = executable
    ET.SubElement(action, _tag("Arguments")).text = subprocess.list2cmdline([script, config, "--once"])
    ET.SubElement(action, _tag("WorkingDirectory")).text = str(Path(script).parent)
    return ET.tostring(root, encoding="utf-16", xml_declaration=True)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["schtasks.exe", *args], shell=False, capture_output=True,
                          text=True, timeout=30, check=False)


def register(path: Path, *, executable: str | None = None,
             script: str | None = None) -> str:
    if sys.platform != "win32":
        raise TaskError("Windows Task Scheduler is only supported on Windows")
    path = path.expanduser().resolve(strict=True)
    name, at = validate_job(path)
    if _run("/Query", "/TN", name).returncode == 0:
        raise TaskError("Task already exists; remove it explicitly before replacing")
    executable = executable or sys.executable
    script = script or str(Path(__file__).with_name("scheduled_api_runner.py").resolve())
    if not Path(executable).is_file() or not Path(script).is_file():
        raise TaskError("The Python executable or runner script is missing")
    xml = task_xml(at, executable, script, str(path))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix="scheduled-api-", suffix=".xml",
                                         delete=False) as handle:
            handle.write(xml)
            temporary = Path(handle.name)
        result = _run("/Create", "/TN", name, "/XML", str(temporary))
        if result.returncode:
            raise TaskError("Windows rejected task registration (exit code " + str(result.returncode) + ")")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return name


def unregister(path: Path) -> str:
    if sys.platform != "win32":
        raise TaskError("Windows Task Scheduler is only supported on Windows")
    name, _ = validate_job(path.expanduser().resolve(strict=True))
    if _run("/Query", "/TN", name).returncode != 0:
        raise TaskError("This task was not found")
    result = _run("/Delete", "/TN", name, "/F")
    if result.returncode:
        raise TaskError("Windows rejected task removal (exit code " + str(result.returncode) + ")")
    return name
