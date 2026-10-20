# Store readiness status — 2026-10-20

**DRAFT / NOT READY FOR SUBMISSION**

Source head reviewed before this documentation commit: `f849d9897abbbb544be9744c6352ae2a3462ed01`.

## Verified

- Code tests: 72 passed; 50 subtests passed locally.
- Fresh MSIX build/round-trip validation: PASS.
- Package hashes: unsigned f2735ffb7d35efc880c0c8747ea40766fb9c4e24c091551995ab01dce4ed6935; local-validation signed de33b6bd83fccbfea02f5774852eac7515e4369d2b1f748facae111393af6596.
- The local-validation signer matched the intended code-signing certificate thumbprint `60BB363D9BE876439137DFB31247952463106BDD`.

## Not yet verified

- Local signed MSIX installation.
- Launch from the Windows Start menu.
- Installed-package Japanese/English UI, setting persistence, close/restart, and real safe input/output.
- Installed-package Store screenshots.
- Windows App Certification Kit report.
- Live Partner Center identity re-copy and final listing review.
- Owner-approved logo, price, markets, IARC answers, privacy/support identity, EULA, and final third-party notices.

The first Scheduled API Runner install attempt failed with `0x800B0109` because the test certificate is not in `LocalMachine\\TrustedPeople`. No certificate-store change is authorized by this document. Never use `CurrentUser\\Root` or `LocalMachine\\Root`, and never weaken Windows security controls.

The API data pane remains an offline configuration preview. It must not be described as proof that an endpoint is reachable or that data was retrieved. Live API/CSV/scheduled-task validation requires an owner-authorized test endpoint.

Store submission, publication, main/release merge, external account access, and destructive customer-data operations are not authorized by this status note.
