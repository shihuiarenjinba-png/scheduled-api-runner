# Scheduled API Runner — QA handoff and release gates

**Status: HOLD.** No Microsoft Store submission authorized.

## Improvements (2026-10-18)
- Mutating API requests (POST, PUT, PATCH, DELETE) have no blind HTTP retries;
  uncertain scheduled slots cannot be reclaimed or auto-replayed.
- A live API action or starting the scheduler now **requires a successful Dry
  Run for the same configuration file path and identical JSON content**.
  Changing request payload, host, method, schedule or file path invalidates
  the prior preview.
- Live execution and scheduler start consume this approval **before** any
  request can run. A lost remote response cannot leave the old approval usable.
- Dry Run sets the same GUI busy guard as a live operation. Language changes
  are prevented during a run.
- Fixed delayed tkinter error callback so exception details are preserved
  instead of losing the caught exception after the worker exits.
- GUI now explains the three-step workflow; real requests are never sent by
  a Dry Run. This is a config validation/count preview, NOT a server-simulated
  request result.

### Tests for code operator
```powershell
python -m compileall -q desktop_app.py scheduled_api_runner.py tests
python -m unittest discover -s tests -v
python desktop_app.py
```
Use owned/local mock HTTPS servers or a private account only for live cases:
lost connection after remote POST processed; 3xx cross-host redirect; request
timeouts; 429/500 retries for GET only; double-click concurrent GUI execution;
schedule start while preview is stale; changing JSON while preview runs; closing
the window during a live request; private token/URL redaction.

**GitHub CI blocker:** latest Actions jobs fail with **zero recorded steps**
and no downloadable logs, including Windows/Ubuntu matrix jobs. This does NOT
prove code failure; it also does NOT prove any tests passed. Operator must
inspect GitHub Actions quota/policy/runner availability and execute tests on
the exact branch SHA.

Further HOLD gates: user-oriented GUI/JSON configuration onboarding,
dependency locks/SBOM/notices, validated Windows EXE/MSIX, real API QA, terms,
product support and privacy URLs, package identity and WACK/Store validation.

## GUI uplift implemented in code (2026-10-18)

The default tab is now **Start here / New setup** rather than a JSON pathname
with no context. It explains the product's job, what the customer needs, and
the order `Choose folder → Fill one GET job → Save new JSON → Dry Run →
Confirm Run Once or Start Scheduler`. Saving does **not** send an API call.

The wizard is intentionally **GET-only**, and only creates one daily
request. POST/PATCH/etc., authorization headers, multiple jobs and complex
triggers still require the existing Advanced JSON view, which must not be
misrepresented as a finished visual workflow builder.

The new `guided_config.py` rejects blank/nonexistent work directories,
HTTP URLs, local or IP hosts, embedded credentials, URL fragments/queries,
and non-standard HTTPS ports. The JSON save uses exclusive creation, so
it will not overwrite an existing file. Both Japanese/English guide copy
is available; language and form state are retained on rebuilding.

`tests/test_guided_config.py` checks form validation, exclusive JSON
persistence, safe offline Dry Run, and wizard save without API calls.
**Tests are authored but have not passed CI:** latest Actions job starts
and terminates with 0 steps; see logs/account runner/usage/policy. Use:
`python -m unittest discover -s tests -v`.
The code operator must run the exact branch SHA and review Tk GUI interactively
at 100%, 125%, 150% real system scaling.

For Windows EXE, use `desktop_app.py` as the GUI entrypoint and include
`jobs.example.json`; Store packaging/certification is not complete.
Product identity recorded at
`store/PARTNER_CENTER_IDENTITY_HANDOFF_20261018.md`.


## Additional draft API JSON Explorer scope (new development branch)

- The new default desktop tab allows left-side multi-source GET settings,
  selected JSON paths, right-side result preview, and .xlsx/.txt/.json exports.
- A template is a separate JSON format (schema_version: 1, sources), **not**
  a scheduler jobs JSON file. Auth header values stay in application memory.
- This is NOT recurring scheduled export; the pre-existing scheduler remains
  on a different tab with its previous functionality.
- All export targets use exclusive new-file publication: never overwrite old
  customer files. Treat failed hard-link publication as failure, not as consent
  to replace a destination.
- API data can be sensitive. No actual endpoint, credential or downloaded
  response should appear in shared CI artifacts, screenshots or logs.
- New tests in tests/test_api_data_explorer.py need to run on the exact branch
  SHA. The known GitHub Actions runner issue prevents calling them PASS.
- Complete Windows GUI and spreadsheet interoperability checks before sale.
- The existing Store text still describes the prior feature set: reconcile
  with final tested behavior and request owner sign-off before publication.
