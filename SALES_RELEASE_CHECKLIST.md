# Sales release checklist / 販売直前チェック

## Automated / code gates

- [x] HTTPS allowlist validation
- [x] Redirects rejected and final URL revalidated
- [x] Running / failed / succeeded run-state model
- [x] Failed runs can retry after backoff; succeeded runs are not duplicated
- [x] Secret-bearing URL data is minimized in logs/UI
- [x] Explicit **`言語 / Language`** selector with persisted `日本語` / `English`
- [x] Language UI and mutating-method warning regression tests
- [x] Japanese and English user guides

## Real Windows / controlled API gates

- [ ] Windows 10 smoke test
- [ ] Windows 11 smoke test
- [ ] Switch 日本語 → English → 日本語; restart and confirm persistence
- [ ] Check 100%, 125%, 150% display scaling
- [ ] Validate a known-good config and deliberately invalid configs
- [ ] Dry Run a GET-only job and confirm no network side effect beyond validation behavior
- [ ] Execute a controlled GET job and confirm host/timeout/audit behavior
- [ ] Execute a controlled POST/PUT/PATCH/DELETE test endpoint and verify the extra warning is clear in both languages
- [ ] Confirm redirect to an unapproved host is blocked
- [ ] Confirm timeout/5xx creates a failed retryable run rather than a permanent success claim
- [ ] Confirm a successful run is not duplicated for the same run key
- [ ] Run scheduler across multiple due slots and restart it cleanly
- [ ] Verify `.env`/environment secrets never appear in UI screenshots or audit output
- [ ] Build packaged Windows executable from a path with spaces/non-ASCII characters
- [ ] Run Windows Defender/AV scan and record release SHA-256
- [ ] Prepare LICENSE/NOTICE/SBOM and lock dependency versions
- [ ] Review every bundled API/provider's current commercial/automation terms before sale
- [ ] Sign the final installer/executable if distributed commercially

Do not mark this product sales-ready until every applicable unchecked item has been completed using controlled endpoints/accounts.

未チェック項目が残っている間は販売完成扱いにしません。
