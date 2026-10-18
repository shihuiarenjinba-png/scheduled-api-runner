# Code operator → Microsoft Store packaging handoff (2026-10-18)

## Decision and role boundary

The owner requests **UI/feature/integration-first source development**, then
delegates Windows launch tests, build/package creation and technical validation
to the separate code operator. A Draft PR is the handoff source, not a
certified binary. Do not claim a PASS without a log from the exact commit.

Use **the indicated existing GitHub branch only** in an isolated new Windows
working directory. Do not edit `main`, overwrite any published EXE/MSIX,
delete source branches, alter customer files, reuse another SKU's Store
identity, or merge a layered PR out of order. Preserve logs and test fixtures
without secrets. All source fixes must be committed to a dedicated branch
and linked to a reviewable PR; do not quietly patch a packaged artifact.

## Standard Windows acceptance gate

1. Capture the current branch's **exact full Git SHA**. Run:
   `python -m compileall -q .`
   and `python -m unittest discover -s tests -v`.
   Do not ship if even one test fails, skips a required Windows feature or
   if expected GUI actions do not execute. Keep the complete redacted logs.
2. Open the real GUI at 100%, 125%, 150% DPI in Japanese and English. Verify
   no clipping, unusable hidden actions, labels inconsistent with features,
   keyboard-only tab navigation, and that user data persists as described.
3. Exercise the exact UI → configuration → offline preview → explicit
   live confirmation → safe output → restart flow on authorized synthetic
   fixtures. Repeat, fail mid-operation, change settings after preview, and
   test existing-file collisions. Never use real customers' data.
4. Build fresh EXE in a unique new output path; test both source and packaged
   `--self-test` modes and any product-specific runtime smoke.
5. Build a **Store-appropriate MSIX / MSIXBundle** with the exact reserved
   Name and Publisher copied from Partner Center. Validate signing requirements,
   required assets/rights, dependencies, icons, package architecture,
   install, launch, update, uninstall and Windows App Certification Kit/Store
   validations. Store upload requires the MSIX file, **not** merely an EXE ZIP.
6. Validate file/secret protection, logs, startup registrations and persistence
   across the install/update/uninstall lifecycle, including different users.
7. Prepare actual JP/EN Store screenshots from the built UI, final listing,
   support/privacy URL, license/third-party notice evidence and pricing
   review. Use the owner's existing product slot only.
8. Report in one evidence table: SHA; Python tests; GUI JP/EN 100/125/150%;
   live synthetic workflow; frozen EXE; MSIX manifest; Windows install/update;
   WACK/Store certification; security and data; license and screenshots;
   all PASS/FAIL/BLOCKED with log/artifact paths. If a gate fails, send the
   exact failure back for repair without claiming sales readiness.

**GitHub Actions caveat:** private sibling repositories' hosted CI jobs have
failed before allocating any runner steps (and the job logs could not be
downloaded); this is not proof that test code failed. Investigate Actions
billing/permissions/runner allocation without buying more allowance without
the owner's approval. Use local Windows operator verification meanwhile.

Do not submit to Partner Center automatically; owner reviews the completed
package and explicitly authorizes the actual submission.

## This product

- Product: **Scheduled API Runner**
- Reserved Microsoft Store ID: `9PND0HG61XD6`
- Package Identity Name: `OkinawaDesktopTools.ScheduledAPIRunner`
- Package Publisher: `CN=46263F21-A700-41DB-8C9B-114C22FB82FC`
- Publisher display name: `Okinawa Desktop Tools`
- Source: `shihuiarenjinba-png/scheduled-api-runner` / Draft PR #4: https://github.com/shihuiarenjinba-png/scheduled-api-runner/pull/4
- Full source branch (do not use only PR base): `feat/api-dated-series-writer-20261018`
- Actual desktop GUI entrypoint: `desktop_app.py`
- Initial non-sales validation command: `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`
- This source can be handed over for operator verification, but do not mark binary PASS until logs exist.

## Product-specific end-to-end scenario

From GUI tab 2, GET JSON with a synthetic authorized API, suggest/select fields
and transfer the source's URL and selected scalar fields to tab 1. Ensure the
daily CSV wizard accepts **multiple newline-separated fields**. Set an optional
header name + environment-variable reference, save a new JSON without any
credential value inside, then run Dry Run and explicitly approve a live GET.

Use a local CSV with yesterday's data and a synthetic authorized real HTTPS
API returning today's ISO observation date. Verify one new row; repeat today
(skip); explicitly replace a correction and inspect byte-identical backup of
the previous version; corrupt the payload/schema/date and confirm no original
history is modified. Confirm UTF-8 Japanese labels and spreadsheet numeric
data. The CSV updater does **not** directly edit a pre-existing .xlsx book.

Use GUI to register a separate GET-only Windows daily task after Dry Run.
Verify task works with the GUI closed **while signed into Windows**, refuses
changed JSON (SHA-256 pinning), and can be removed without deleting CSV.
Test restart/logon and response errors. Windows Task Scheduler must not
overwrite an unrelated task or register POST. A package update changes the
versioned WindowsApps EXE path: test/update the launcher registration strategy
(e.g. a properly packaged stable app execution alias) or prompt a clear
re-registration before sale. Do not claim scheduling while logged out/PC off.
Advanced mutating jobs must stay separate from the GET-only scheduled CSV
registration.

Build GUI EXE with `build_windows.ps1`; manually validate
`python desktop_app.py --self-test`, `python desktop_app.py`, and
`tests/test_api_series_store.py`, `tests/test_api_data_explorer.py`,
`tests/test_windows_tasks.py`, `tests/test_guided_config.py`.
Obtain production-permission terms for each real API; no API keys bundled.

## Where to send evidence

Record build report, SHA256 of tested binaries, new MSIX name/version,
real JP/EN GUI screenshots, redacted test results and final QA decision in
an additional dated file under `store/` on the same product branch. Surface
every discovered source defect in a follow-up PR. Keep `main` and any
previous release unchanged until separately authorized.
