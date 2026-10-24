# Store readiness status — 2026-10-20

**DRAFT / NOT READY FOR SUBMISSION**

Validated source head: `f849d9897abbbb544be9744c6352ae2a3462ed01`.

## Verified

- Local code tests: 72 passed; 50 subtests passed.
- Fresh unsigned MSIX build/round-trip: PASS; SHA256 `f2735ffb7d35efc880c0c8747ea40766fb9c4e24c091551995ab01dce4ed6935`.
- Local-validation signed copy SHA256 `de33b6bd83fccbfea02f5774852eac7515e4369d2b1f748facae111393af6596`; signer matched thumbprint `60BB363D9BE876439137DFB31247952463106BDD`.
- Manifest Identity `OkinawaDesktopTools.ScheduledAPIRunner` + Publisher `CN=46263F21-A700-41DB-8C9B-114C22FB82FC` produced PFN `OkinawaDesktopTools.ScheduledAPIRunner_j8yefg9jgfh58` through Windows `PackageFamilyNameFromId`, matching the captured draft.

## CI

Current-head runs `39400003589` and `39400003585` are **CI_FAIL_UNDIAGNOSED**. All Ubuntu/Windows matrix and build jobs failed before a runner was named; `steps=[]`; job-log download returns no blob. This is not enough evidence to call the cause an infrastructure incident, billing issue, or code failure.

## Not yet verified

MSIX installation, Start-menu launch, installed JP/EN UI, persistence/restart, real approved API/CSV/task I/O, Store screenshots, WACK, and live Partner Center identity are NOT TESTED. The prior install failed `0x800B0109`; no trust-store change is authorized. The API data pane is an offline configuration preview, not proof of retrieval.

## Submission safeguards

- Microsoft Standard Application License Terms (SALT) are the default when **Additional license terms** is left blank. A custom EULA is not an engineering prerequisite unless the owner chooses different terms.
- Prices and Japan/United States markets remain proposals only. Disable future-market automatic expansion.
- Immediately before certification submission, select **Don't publish this submission until I select Publish now**. The default can publish automatically after certification.
- AI-generated icons remain unapproved concepts and are not package or Store assets.
- Certificate-store changes, Store upload/submission/publication, and main/release merges remain unauthorized.
