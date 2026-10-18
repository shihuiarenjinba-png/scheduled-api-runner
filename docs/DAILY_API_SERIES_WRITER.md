# Daily API time-series writer — implementation and release gates

**Development-only / HOLD as of 2026-10-18.** This branch continues the earlier JSON API explorer while specializing in read-only HTTPS API ingestion. The standalone Browser Runner is separate. No main/release/Store submission changed.

## Customer example

An authorized sales API returns JSON containing the date and today's sales/number of orders. The owner chooses a local CSV history:

- 2026-10-16, 110000, 38
- 2026-10-17, 132000, 41

A daily job at 09:00 extracts data.sales, data.orders, and data.date, then appends one row for the date returned by the API. An Excel-compatible CSV spreadsheet now contains the history plus the new observation. Existing records remain. Multiple jobs may be configured in advanced JSON.

## Beginner GUI

The Start here/New setup tab now includes:
- Work folder, job name, HTTPS URL, daily time
- Checkbox to enable CSV history output
- Relative CSV filename under the chosen work folder
- Desired JSON field paths, one per line (sales = data.sales)
- Optional date field path (data.date). Blank means the PC's local calendar date at request time; do NOT assume this reflects the provider's observation date.
- Save new JSON (never overwrites), offline Dry Run, explicit live/Start Scheduler approval

The separate API Data Explorer tab lets the user manually preview fields and try a GET before scheduling. The existing advanced JSON scheduler can maintain several jobs.

## Engine invariants

- CSV updating only for GET. POST/PATCH/PUT/DELETE remain legacy advanced execution but cannot set csv_update.
- Dated row must have every required field; missing/null, unexpected arrays, schema mismatch and malformed dates stop without modifying the original.
- CSV destination is relative to root_dir; only an existing parent directory is accepted. No symlink destinations, traversal or alternate extension. Max original/output CSV 25 MB, response JSON 2 MB.
- Locked via exclusive sibling .lock file per CSV. A stale lock is **never** silently cleared; investigate before manual removal.
- Duplicate date defaults to SKIP and does not modify file. Explicit replace is available through advanced JSON; it creates a backup.
- Before changing existing CSV, create an immutable sibling .backup-* hard link preserving the original bytes. Stage complete new file in the same directory and os.replace it only after checking the original metadata. If creating a new file, use an exclusive hard link. Prior backups are retained; inform customer to manage retention safely.
- Local filesystem semantics are required; network/OneDrive/cloud-synced paths and external concurrent writers are not yet certified. A process crash can leave the lock file.
- Existing CSV columns must include date plus every configured output column; other columns and historical dates are preserved. This is not a generic spreadsheet editor or chart engine.
- Formula-looking CSV text is escaped. API authentication can use the pre-existing environment-variable substitution in advanced JSON.
- Daily scheduler catches up later on the same calendar day (if the app was running / started after scheduled minute) and still uses SQLite per-date keys; it cannot run while PC is off, and timezone/DST/business-day API delays need authorized live tests.

## Must test before sale

1. Run python -m unittest discover -s tests -v on the exact checkout (including tests/test_api_series_store.py) and desktop_app.py --self-test.
2. Check GUI source/fields/date mapping in both languages, windows size 100/125/150%, network failures, cancellation, secret redaction.
3. Use authorized private test API with test keys, one successful daily append, a repeat (skip), explicit same-date correction (backup), historical schema mismatch (preserves original), restart/catch-up and network disconnect.
4. Open CSV in Excel and verify date cells, numeric values and formula-injection guard. CSV is not a preexisting .xlsx workbook; **direct XLSX edits are NOT implemented**.
5. Check server 429 limits, provider license and endpoint documentation. Do not publish secrets in logs/screenshots.
6. Code operator must resolve prior GitHub Actions jobs failing before steps and produce CI evidence. Real Windows EXE/MSIX, WACK, rights/licenses, review of Store descriptions and owner sign-off remain HOLD.

Example advanced config: jobs.dated-csv.example.json. It is disabled and requires customer changes (including a real existing output directory for nested paths).


## Opt-in Windows scheduled API history (source draft, 2026-10-18)

The Windows GUI Advanced tab offers an optional **Register daily Windows
task** button and an explicit **Remove registered task** control, in addition
to in-app Start/Stop Scheduler. Register is gated on an unchanged successful
offline Dry Run and a second consent dialog. Windows task registration is
limited to **one enabled daily HTTPS GET job** with a validated dated CSV
output; no POST/PATCH/PUT/DELETE and no multi-job config. Multiple API
datasets may be maintained as **separate approved task/config files**.

The task runs the frozen EXE (or Python source launcher) in non-GUI
--run-locked mode and does a *single due-jobs check*. Its argument includes a
SHA-256 of the approved full JSON file. If any byte of that file changes,
future scheduled executions fail closed until the user explicitly removes and
re-registers the task. Create does NOT use schtasks /F, so it never silently
replaces an existing named Windows task. Removal requires a separate dialog
and does not delete the JSON file or customer data. Failure of a due GET
returns a nonzero task exit status.

Restrictions: registration is supported on Windows only, and the scheduled
job is interactive-logon / non-elevated. It does **not** work when the PC is
off or no user is signed in. OS user environment variables used for credentials
must be accessible to the scheduled user after sign-in. After an app install
location/version changes, re-register tasks and verify the EXE path. This
registration does not install a Windows service or hidden cloud agent.

Operator QA: run tests/test_windows_tasks.py, register on a disposable
Windows account, verify at HH:MM with GUI closed, repeat (date skipped),
change JSON (blocked), unplug network (nonzero exit), remove task (customer
files remain), restart PC/logon, inspect Windows Task Scheduler History.
Do not enable /F or change task privileges to bypass user consent.
