"""Transactional dated API JSON -> existing CSV time-series update.

The scheduler owns when GET occurs. This module owns *only* validating and
publishing the response into a customer-selected local CSV series.
No overwrites without a durable pre-update backup and an explicit policy.
"""
from __future__ import annotations

import csv
from datetime import datetime, date
import os
import shutil
from pathlib import Path
import re
import tempfile
import uuid

from api_data_explorer import extract_rows, parse_fields


class SeriesError(ValueError):
    pass


MAX_CSV_BYTES = 25_000_000
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_writer(cfg: dict, root: Path) -> tuple[Path, list[str]]:
    if not isinstance(cfg, dict):
        raise SeriesError("csv_update must be an object")
    path_string = cfg.get("path")
    if not isinstance(path_string, str) or not path_string.strip():
        raise SeriesError("csv_update.path is required")
    raw = Path(path_string)
    if raw.is_absolute() or ".." in raw.parts or raw.suffix.lower() != ".csv":
        raise SeriesError("CSV path must be a relative .csv path inside root_dir")
    base = root.expanduser().resolve()
    target = base / raw
    cursor = base
    for piece in raw.parts:
        cursor = cursor / piece
        if cursor.is_symlink():
            raise SeriesError("Symbolic links are not allowed in CSV destination")
    if not target.resolve().is_relative_to(base):
        raise SeriesError("CSV destination escapes root_dir")
    if cfg.get("on_duplicate", "skip") not in {"skip", "replace"}:
        raise SeriesError("on_duplicate must be skip or replace")
    fields = cfg.get("fields")
    if not isinstance(fields, str):
        raise SeriesError("csv_update.fields must contain JSON field mappings")
    try:
        parsed = parse_fields(fields)
    except ValueError as exc:
        raise SeriesError(str(exc)) from exc
    if any("*" in tokens for _, tokens in parsed):
        raise SeriesError("Dated CSV needs one value per field, not [*] arrays")
    names = [name for name, _ in parsed]
    if "date" in names:
        raise SeriesError("Use date_path to specify the date; do not map a date column")
    date_path = cfg.get("date_path")
    if date_path:
        if not isinstance(date_path, str):
            raise SeriesError("date_path must be a JSON field path")
        try:
            checks = parse_fields("date = " + date_path)
        except ValueError as exc:
            raise SeriesError(str(exc)) from exc
        if len(checks) != 1 or "*" in checks[0][1]:
            raise SeriesError("date_path must refer to one scalar JSON date")
    else:
        if cfg.get("date_source") != "run_local":
            raise SeriesError("Supply date_path or explicitly set date_source=run_local")
    if target == base:
        raise SeriesError("Choose a CSV filename")
    return target, ["date"] + names


def _date_from_response(payload: object, config: dict, now: datetime) -> str:
    if config.get("date_path"):
        _, rows = extract_rows(payload, "date = " + config["date_path"])
        raw = rows[0]["date"] if rows else ""
        if not isinstance(raw, str):
            raise SeriesError("Response date must be ISO YYYY-MM-DD or ISO datetime")
        chosen = raw[:10]
        try:
            if _DATE_PATTERN.fullmatch(raw):
                date.fromisoformat(raw)
            elif (len(raw) > 11 and _DATE_PATTERN.fullmatch(chosen)
                  and raw[10] in ("T", " ")):
                datetime.fromisoformat(raw.replace("Z", "+00:00"))
            else:
                raise ValueError("Not an ISO date/time")
        except ValueError:
            raise SeriesError("API returned an invalid ISO date/time") from None
    else:
        if now.tzinfo is None:
            raise SeriesError("An aware local datetime is required")
        chosen = now.date().isoformat()
    try:
        date.fromisoformat(chosen)
    except ValueError as exc:
        raise SeriesError("Invalid calendar date in API response") from exc
    return chosen


def _csv_safe(value: object) -> str:
    if value is None or value == "":
        raise SeriesError("A required API value is missing: do not append incomplete daily data")
    if isinstance(value, (dict, list)):
        raise SeriesError("Daily CSV cells must be scalar values")
    text = str(value)
    if len(text) > 25_000:
        raise SeriesError("API field value is too long")
    # Spreadsheet CSV formula injection: prefix text even when cells begin with whitespace.
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) and not _number(text):
        text = "'" + text
    return text


def _number(value: str) -> bool:
    try:
        from decimal import Decimal
        number = Decimal(value)
        return number.is_finite() and bool(re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value))
    except Exception:
        return False


def _existing_rows(path: Path, required: list[str]) -> tuple[list[str], list[dict], bool]:
    if not path.exists():
        return required, [], True
    if not path.is_file() or path.stat().st_size > MAX_CSV_BYTES:
        raise SeriesError("Existing CSV is not a regular file or exceeds the safety limit")
    with path.open("r", encoding="utf-8-sig", newline="") as reader:
        rows = list(csv.DictReader(reader))
    # Preserve existing column ordering and any extra columns.
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        headers = next(csv.reader(file), None)
    if not headers or len(headers) != len(set(headers)) or any(not h for h in headers):
        raise SeriesError("Existing CSV is missing a valid unique header row")
    if any(item not in headers for item in required):
        raise SeriesError("Existing CSV columns do not match configured output fields")
    if any(None in row for row in rows):
        raise SeriesError("Existing CSV contains malformed extra columns")
    # DictReader uses None for missing fields. Rewriting such a file would
    # silently turn corrupted records into empty cells; fail closed instead.
    if any(any(value is None for value in row.values()) for row in rows):
        raise SeriesError("Existing CSV contains incomplete rows; no update performed")
    seen_dates: set[str] = set()
    for row in rows:
        day = row.get("date")
        if not day:
            raise SeriesError("Existing CSV contains a missing date; no update performed")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError()
        except ValueError:
            raise SeriesError("Existing CSV contains an invalid date; no update performed") from None
        if day in seen_dates:
            raise SeriesError("Existing CSV contains duplicate historical dates; no update performed")
        seen_dates.add(day)
    return headers, rows, False


def update_series(root: Path, cfg: dict, payload: object, now: datetime) -> dict:
    """Append one dated observation; skip duplicates or replace when opted in.

    If an existing file is changed, create a separate immutable backup link
    before the atomic replacement. An exclusive lock avoids concurrent app
    writers. A crash can leave the lock, in which case manual investigation is
    required; auto-removal would be unsafe.
    """
    target, required = validate_writer(cfg, root)
    _, records = extract_rows(payload, cfg["fields"])
    if len(records) != 1:
        raise SeriesError("Expected exactly one daily observation from the API")
    record = records[0]
    day = _date_from_response(payload, cfg, now)
    new_values = {"date": day}
    for field in required[1:]:
        new_values[field] = _csv_safe(record[field])
    parent = target.parent
    if not parent.is_dir():
        raise SeriesError("CSV parent folder must exist; no implicit directory creation")
    lock_path = target.with_name("." + target.name + ".lock")
    try:
        lock_handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SeriesError("CSV is locked; stop other jobs or inspect a leftover lock") from None
    temp = None
    try:
        with os.fdopen(lock_handle, "w", encoding="utf-8") as lock:
            lock.write("Series writer locked\n")
            lock.flush()
        target, required = validate_writer(cfg, root)
        original = target.stat() if target.exists() else None
        headers, old_rows, is_new = _existing_rows(target, required)
        matches = [i for i, row in enumerate(old_rows) if row.get("date") == day]
        if len(matches) > 1:
            raise SeriesError("Duplicate dates already exist; repair historical file manually")
        if matches and cfg.get("on_duplicate", "skip") == "skip":
            return {"status": "skipped_existing_date", "date": day, "rows": len(old_rows)}
        updated = {h: "" for h in headers}
        updated.update(new_values)
        if matches:
            old_rows[matches[0]].update(new_values)
            event = "replaced_date"
        else:
            old_rows.append(updated)
            event = "created_file" if is_new else "appended_date"
        fd, name = tempfile.mkstemp(dir=parent, prefix=".series-write-", suffix=".tmp")
        temp = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers, lineterminator="\n")
            writer.writeheader()
            writer.writerows(old_rows)
            file.flush()
            os.fsync(file.fileno())
        if temp.stat().st_size > MAX_CSV_BYTES:
            raise SeriesError("Updated CSV would exceed the safety limit")
        backup = None
        if original is not None:
            current = target.stat()
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns):
                raise SeriesError("CSV changed while preparing update; operation aborted")
            backup = parent / ("." + target.name + ".backup-" +
                               datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
            # Never hard-link the live original: another process holding it
            # open could change the backup's bytes before final publication.
            # Snapshot into a unique staging file and publish that snapshot
            # under a new backup name, preserving the source file unchanged.
            backup_fd, backup_tmpname = tempfile.mkstemp(
                dir=parent, prefix=".series-backup-stage-", suffix=".tmp")
            backup_stage = Path(backup_tmpname)
            try:
                with os.fdopen(backup_fd, "wb") as dest, target.open("rb") as src:
                    shutil.copyfileobj(src, dest)
                    dest.flush()
                    os.fsync(dest.fileno())
                # Detect a concurrent source change during the copy.
                new_stat = target.stat()
                if (new_stat.st_dev, new_stat.st_ino,
                    new_stat.st_size, new_stat.st_mtime_ns) != (
                        original.st_dev, original.st_ino,
                        original.st_size, original.st_mtime_ns):
                    raise SeriesError("CSV changed while copying backup; aborting")
                os.link(backup_stage, backup)
            finally:
                backup_stage.unlink(missing_ok=True)
        if original is None and target.exists():
            raise SeriesError("CSV appeared while preparing update; operation aborted")
        try:
            if original is None:
                os.link(temp, target)  # exclusive creation
            else:
                os.replace(temp, target)  # atomic local same-directory replacement
                temp = None
        except Exception:
            # If publication fails, the untouched customer file and backup stay.
            raise
        return {"status": event, "date": day, "rows": len(old_rows),
                "backup_created": backup is not None}
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
