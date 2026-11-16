# Scheduled API Runner — Store readiness status

Updated: 2026-11-16 JST

**GITHUB ENGINEERING COMPLETE / LOCAL FINAL QA HOLD / STORE WRITE HOLD**

Repository branch: `codex/scheduled-standard-consumer-ui-20261113`  
Draft PR: #8

## GitHub-side completed

- guided bilingual consumer UI;
- guarded GET/CSV workflow and replay-safety regressions;
- Windows Task Scheduler contract tests;
- exact-head Windows + Ubuntu reliability CI;
- frozen Windows EXE build and no-network self-test;
- unsigned MSIX build;
- Manifest Identity / Publisher / Version validation;
- MakeAppx pack/unpack;
- EXE roundtrip SHA validation;
- exact-package `store-product-handoff/2` generation;
- Store handoff profile;
- local final-QA runbook;
- Store listing/privacy/runFullTrust material bundled with the Store artifact.

The Store artifact is the source of truth. Local QA must download those exact package
bytes and must not rebuild the candidate before acceptance.

## Canonical Store identity record

Historical Partner Center record:

- Store ID: `9PND0HG61XD6`
- Identity: `OkinawaDesktopTools.ScheduledAPIRunner`
- Publisher: `CN=46263F21-A700-41DB-8C9B-114C22FB82FC`
- PFN reference: `OkinawaDesktopTools.ScheduledAPIRunner_j8yefg9jgfh58`
- technical MSIX version: `1.0.0.0`

These repository values are evidence, not live authorization. Re-read Partner Center
before any write.

## Commercial position

Launch model: FREE candidate.

No Partner Center price/market change is authorized merely by this repository state.

## Local-only remaining gates

- exact package SHA verification;
- physical Windows JP/EN GUI;
- 100/125/150% DPI;
- controlled authorized HTTPS GET;
- dated CSV append/duplicate-date behavior;
- secret-redaction check;
- Task Scheduler register/run/verify/unregister;
- normal restart/exit;
- live Partner Center identity and submission-state reverification;
- owner review of final assets/security/audience.

Return local PASS using `local-final-qa-receipt/1` bound to the exact source/MSIX.

## Store sequencing

After local PASS:

1. apply the exact-package QA receipt in Windows-all-auto;
2. reverify Partner Center identity/submission state;
3. complete owner-confirmed Store fields;
4. VALIDATE_ONLY;
5. DRY_RUN;
6. obtain separate package-upload approval.

Certification and Publish remain separate later approvals. No security-policy or trust
store bypass is required or authorized.
