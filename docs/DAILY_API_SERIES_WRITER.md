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
