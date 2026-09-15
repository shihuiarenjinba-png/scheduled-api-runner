# Roadmap

## Phase 1 — Scheduled HTTPS Core（現在）

- daily / interval schedules
- HTTPS-only requests
- host allowlist
- retry / timeout
- Dry Run
- SQLite duplicate-run prevention
- audit log
- `${ENV:NAME}` secret references
- `root_dir` boundary for state/log files

## Phase 2 — Production Scheduling

- explicit timezone setting
- missed-run policy
- exponential/fixed backoff options
- response-to-file output
- manual rerun command
- job-level success/failure history

## Phase 3 — Authentication Connectors

- Google OAuth Desktop Flow
- secure Refresh Token storage
- automatic token refresh
- API-specific connectors for Drive / Sheets / Blogger / YouTube

## Phase 4 — Windows Product

- tray/service mode
- schedule editor GUI
- start-with-Windows
- job templates
- signed build

## Release Gate

Clock/timezone tests, restart/idempotency tests, retry tests, timeout tests, secret-redaction review, API egress audit, Windows 10/11 smoke tests.
