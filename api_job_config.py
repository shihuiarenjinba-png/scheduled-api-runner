"""Strict GUI-friendly configuration for dated JSON -> existing CSV jobs."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path


class ConfigurationError(ValueError):
    pass


def parse_column_mapping(spec: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in spec.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '=' not in line:
            raise ConfigurationError('Each column needs header=json.field.path')
        header, path = (part.strip() for part in line.split('=', 1))
        if not header or not path or len(header) > 100 or len(path) > 250:
            raise ConfigurationError('Column header/path missing or too long')
        if header in mapping:
            raise ConfigurationError(f'Duplicate column: {header}')
        if header.lower().startswith(('=', '@', '+')):
            raise ConfigurationError('Invalid CSV column header')
        if not re.fullmatch(r'[A-Za-z0-9_\-.]+(?:\.[A-Za-z0-9_\-]+)*', path):
            raise ConfigurationError('JSON field path must be explicit and simple')
        mapping[header] = path
    if not mapping:
        raise ConfigurationError('Specify at least one source field')
    return mapping


def build_daily_job(*, url: str, csv_path: str, mapping: str,
                    job_name: str = 'daily_api', at: str = '09:00',
                    duplicate_policy: str = 'error',
                    token_env_name: str = '') -> dict:
    url = url.strip()
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    if (parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.fragment):
        raise ConfigurationError('Valid HTTPS endpoint without URL credentials is required')
    if any(k.lower() in ('token','api_key','access_token','password','secret') for k in urllib.parse.parse_qs(parsed.query)):
        raise ConfigurationError('Secret query parameters are not supported')
    if not re.fullmatch(r'\d{2}:\d{2}',at):
        raise ConfigurationError('Schedule must use HH:MM')
    hh, mm = (int(v) for v in at.split(':'))
    if not 0 <= hh <= 23 or not 0 <= mm <= 59:
        raise ConfigurationError('Invalid scheduled time')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_\-]{0,50}',job_name):
        raise ConfigurationError('Invalid job name')
    if duplicate_policy not in ('error', 'skip', 'replace'):
        raise ConfigurationError('Choose explicit duplicate policy')
    fields = parse_column_mapping(mapping)
    if 'date' in fields:
        raise ConfigurationError('Date header is reserved for scheduling')
    dest = Path(csv_path).expanduser().resolve()
    if dest.suffix.lower()!='.csv' or not dest.is_file() or dest.is_symlink():
        raise ConfigurationError('Select an existing regular CSV; the file will never be silently created')
    headers = {}
    if token_env_name:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',token_env_name):
            raise ConfigurationError('Environment variable name is invalid')
        headers['Authorization'] = 'Bearer ' + '$' + '{ENV:' + token_env_name + '}'
    return {
        'root_dir': str(dest.parent),
        'allow_hosts': [host],
        'poll_seconds': 10,
        'jobs': [{
            'name': job_name,
            'schedule': {'type':'daily','at':at},
            'request': {'url':url,'method':'GET','headers':headers,'timeout_seconds':30},
            'retries': 2,
            'retry_wait_seconds': 3,
            'persist': {
                'target_file':dest.name,
                'columns': fields,
                'date_column': 'date',
                'duplicate_policy': duplicate_policy,
                'create_if_missing': False,
            },
        }],
    }
