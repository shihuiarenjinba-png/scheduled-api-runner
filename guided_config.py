"""Generate a deliberately limited first-run GET-only API job.

This module does not make network requests, store tokens, or alter old configs.
Advanced requests remain available via manual JSON review.
"""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from api_series_store import validate_writer, SeriesError


class GuidedConfigError(ValueError):
    pass


def https_host(url: str) -> str:
    url = str(url).strip()
    if not url or any(c.isspace() for c in url):
        raise GuidedConfigError("Enter a full HTTPS URL without spaces / HTTPSのURLを入力してください")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise GuidedConfigError("Invalid URL / URLが正しくありません") from exc
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.fragment:
        raise GuidedConfigError("Use HTTPS without credentials or fragments / HTTPSで認証情報や#を含めないでください")
    if parts.query:
        raise GuidedConfigError("Remove URL query parameters; use advanced setup for query strings")
    if port is not None and port != 443:
        raise GuidedConfigError("For the guided setup, use standard HTTPS port 443")
    if host.endswith(".local") or host in {"localhost"}:
        raise GuidedConfigError("Local hostnames are not supported by guided setup")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host) or "." not in host:
            raise GuidedConfigError("Enter a public DNS hostname / 公開ホスト名を指定してください")
        return host.lower()
    raise GuidedConfigError("IP literal addresses are not supported by guided setup")


def make_get_job(*, root_dir: str, name: str, url: str, daily_at: str) -> dict:
    root_value = str(root_dir).strip()
    if not root_value:
        raise GuidedConfigError("Select a data folder first / 最初に保存先フォルダーを選択してください")
    root = Path(root_value).expanduser()
    if not root.is_dir():
        raise GuidedConfigError("Choose an existing data folder / 既存の保存用フォルダーを選んでください")
    job_name = str(name).strip()
    if not job_name or len(job_name) > 80 or any(ch in job_name for ch in "\r\n|"):
        raise GuidedConfigError("Enter a short job name / 短いジョブ名を入力してください")
    try:
        from datetime import datetime
        parsed = datetime.strptime(str(daily_at), "%H:%M")
    except ValueError as exc:
        raise GuidedConfigError("Time must be HH:MM, e.g. 09:00 / 時刻は09:00などで指定") from exc
    if parsed.strftime("%H:%M") != daily_at:
        raise GuidedConfigError("Use two-digit time HH:MM")
    host = https_host(url)
    return {
        "root_dir": str(root.resolve()),
        "allow_hosts": [host],
        "poll_seconds": 30,
        "state_db": ".state/scheduler.sqlite3",
        "log_path": "logs/api.jsonl",
        "jobs": [{
            "name": job_name,
            "enabled": True,
            "schedule": {"type": "daily", "at": daily_at},
            "retries": 0,
            "request": {"method": "GET", "url": url.strip(), "timeout_seconds": 20},
        }],
    }


def add_daily_csv_output(config: dict, *, path: str, fields: str,
                         date_path: str = "", on_duplicate: str = "skip") -> dict:
    """Opt-in extension of an existing GET wizard configuration, no side effects."""
    if on_duplicate not in {"skip", "replace"}:
        raise GuidedConfigError("Choose skip or replace for a repeated date")
    update = {"path": str(path).strip(), "fields": str(fields).strip(),
              "on_duplicate": on_duplicate}
    if str(date_path).strip():
        update["date_path"] = str(date_path).strip()
    else:
        update["date_source"] = "run_local"
    try:
        validate_writer(update, Path(config["root_dir"]))
    except SeriesError as exc:
        raise GuidedConfigError(str(exc)) from exc
    revised = dict(config)
    jobs = [dict(job) for job in config["jobs"]]
    jobs[0]["csv_update"] = update
    revised["jobs"] = jobs
    return revised


def save_new_config(path: str | Path, config: dict) -> Path:
    destination = Path(path)
    # Exclusive creation avoids deleting or overwriting customer JSON.
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return destination


def add_auth_header_env(config: dict, *, header_name: str, env_name: str) -> dict:
    """Add optional API auth without ever embedding raw secrets in saved JSON."""
    header_name = str(header_name).strip()
    env_name = str(env_name).strip()
    if not header_name and not env_name:
        return config
    if not header_name or not env_name:
        raise GuidedConfigError("Provide both API header name and environment variable")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", header_name):
        raise GuidedConfigError("Header name must contain letters, numbers and hyphens")
    if header_name.lower() in {"host", "connection", "content-length", "cookie",
                                "proxy-authorization", "transfer-encoding"}:
        raise GuidedConfigError("Restricted HTTP header; choose an API authentication header")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", env_name):
        raise GuidedConfigError("Environment variable name must be letters, numbers and underscores")
    result = dict(config)
    jobs = [dict(x) for x in config["jobs"]]
    req = dict(jobs[0]["request"])
    headers = dict(req.get("headers", {}))
    if any(x.casefold() == header_name.casefold() for x in headers):
        raise GuidedConfigError("The API header was already configured")
    headers[header_name] = "$" + "{ENV:" + env_name + "}"
    req["headers"] = headers
    jobs[0]["request"] = req
    result["jobs"] = jobs
    return result
