"""Validated, atomic date-keyed updates from an HTTPS JSON response to a CSV.

CSV is used deliberately: no Excel macros/formulas are executed and no previous
records are silently replaced. This module neither performs networking nor schedules.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class DailyStoreError(ValueError):
    pass


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _inside_root(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise DailyStoreError('Invalid destination path')
    root = root.resolve(strict=True)
    dest = (root / relative).resolve()
    if not dest.is_relative_to(root) or dest == root:
        raise DailyStoreError('Destination must be beneath root_dir')
    if dest.suffix.lower() != '.csv':
        raise DailyStoreError('The verified daily append mode currently supports CSV only')
    return dest


def _extract(value: Any, pointer: str) -> Any:
    """Require explicit JSON field names or indexes, never guess similar fields."""
    if not isinstance(pointer, str) or not pointer or len(pointer) > 250:
        raise DailyStoreError('Each source field must have an explicit nonempty path')
    current = value
    for component in pointer.split('.'):
        if isinstance(current, dict) and component in current:
            current = current[component]
        elif isinstance(current, list) and component.isdecimal() and int(component) < len(current):
            current = current[int(component)]
        else:
            raise DailyStoreError(f'JSON field is missing or ambiguous: {pointer}')
    if current is None or isinstance(current, (dict, list)):
        raise DailyStoreError(f'JSON field must contain one scalar value: {pointer}')
    return current


def _cell(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    result = str(value)
    if '\x00' in result or len(result) > 25000:
        raise DailyStoreError('Unsafe or oversized value')
    probe = result.lstrip(' \t\r\n')
    if probe and probe[0] in ('=', '+', '-', '@'):
        if not (probe[0] in ('+', '-') and re.fullmatch(r'[+-](?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', probe)):
            raise DailyStoreError('CSV formula-like string rejected; review the source field')
    return result


def update_daily_csv(root_dir: str | Path, payload: Any, config: dict[str, Any], *,
                     recorded_at: datetime | None = None) -> dict[str, Any]:
    """Update a dated CSV record; return auditable paths + before/after hashes.

    config fields: target_file, columns {CSV-name: JSON.path}, date_column,
    date_field (optional), duplicate_policy = error|skip|replace, create_if_missing.
    """
    root = Path(root_dir).expanduser().resolve(strict=True)
    target = _inside_root(root, config.get('target_file'))
    columns = config.get('columns')
    if not isinstance(columns, dict) or not columns or len(columns) > 250:
        raise DailyStoreError('columns must explicitly map output headers to JSON fields')
    date_col = config.get('date_column', 'date')
    if not isinstance(date_col, str) or not date_col or date_col in columns:
        raise DailyStoreError('Invalid or duplicate date_column')
    header = [date_col, *columns.keys()]
    if any(not isinstance(x, str) or not x.strip() or '\n' in x or '\r' in x for x in header):
        raise DailyStoreError('Invalid CSV header')
    if len(set(header)) != len(header):
        raise DailyStoreError('CSV headers must be unique')
    policy = config.get('duplicate_policy', 'error')
    if policy not in ('error', 'skip', 'replace'):
        raise DailyStoreError('Invalid duplicate_policy')
    if recorded_at is None:
        recorded_at = datetime.now().astimezone()
    if 'date_field' in config:
        date_text = str(_extract(payload, config['date_field']))
    else:
        date_text = recorded_at.date().isoformat()
    try:
        parsed_date = datetime.strptime(date_text, '%Y-%m-%d').date()
    except (ValueError, TypeError) as exc:
        raise DailyStoreError('Date must be YYYY-MM-DD') from exc
    if parsed_date.isoformat() != date_text:
        raise DailyStoreError('Invalid date representation')
    row = {date_col: date_text}
    for dest_col, pointer in columns.items():
        row[dest_col] = _cell(_extract(payload, pointer))

    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise DailyStoreError('Destination cannot be a symlink or directory')
    if not target.parent.exists() or not target.parent.is_dir():
        raise DailyStoreError('Destination parent folder must already exist')
    lock = target.with_name(target.name + '.update.lock')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DailyStoreError('Another update is running or a stale lock needs review') from exc
    temp_path: Path | None = None
    backup: Path | None = None
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write('exclusive update in progress\n')
        previous_hash = None
        existing: list[dict[str, str]] = []
        if target.exists():
            if target.stat().st_size > 20 * 1024 * 1024:
                raise DailyStoreError('Existing CSV exceeds verified 20 MiB limit')
            previous_hash = _digest(target)
            with target.open('r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, strict=True)
                if reader.fieldnames != header:
                    raise DailyStoreError('Existing CSV headers do not match exactly; no data changed')
                for record in reader:
                    if None in record or any(v is None for v in record.values()):
                        raise DailyStoreError('Malformed existing CSV row')
                    existing.append(record)
                    if len(existing) > 250_000:
                        raise DailyStoreError('Existing CSV exceeds verified row limit')
        elif not config.get('create_if_missing', False):
            raise DailyStoreError('Existing CSV is missing; creation needs explicit permission')
        matches = [i for i, r in enumerate(existing) if r[date_col] == date_text]
        if len(matches) > 1:
            raise DailyStoreError('Existing CSV contains duplicate date keys')
        if matches:
            if policy == 'error':
                raise DailyStoreError('Date already exists; choose skip or replace explicitly')
            if policy == 'skip':
                return {'status':'SKIPPED_EXISTING_DATE', 'target':str(target),
                        'date':date_text,'before_sha256':previous_hash,'after_sha256':previous_hash,
                        'row_count':len(existing),'backup':None}
            existing[matches[0]] = row
            operation = 'REPLACED_DATE'
        else:
            existing.append(row)
            operation = 'APPENDED_DATE'
        if target.exists():
            backup = target.with_name(target.name + '.backup-' + uuid.uuid4().hex[:12])
            with target.open('rb') as src, backup.open('xb') as dst:
                shutil.copyfileobj(src, dst, length=1024*1024)
                dst.flush()
                os.fsync(dst.fileno())
            if _digest(backup) != previous_hash:
                raise DailyStoreError('Backup integrity failed; original not changed')
        with tempfile.NamedTemporaryFile('w', newline='', encoding='utf-8',
                                         dir=target.parent, prefix=target.name + '.new-',
                                         suffix='.tmp', delete=False) as f:
            temp_path = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=header, lineterminator='\n')
            writer.writeheader()
            writer.writerows(existing)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target)
        temp_path = None
        return {'status': operation, 'target':str(target), 'date':date_text,
                'before_sha256':previous_hash, 'after_sha256':_digest(target),
                'row_count':len(existing), 'backup':str(backup) if backup else None}
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
