# Scheduled API Runner — Identity and MSIX version audit — 2026-10-23

**Status: DRAFT / PUBLIC RELEASE HOLD.** No merge, Partner Center upload, certification submission, publication, certificate-store change, or Windows security change was performed by this audit.

## Scope and provenance

- Repository: `shihuiarenjinba-png/scheduled-api-runner`
- Existing Draft PR: https://github.com/shihuiarenjinba-png/scheduled-api-runner/pull/6
- Work branch: `codex/store-draft-validation-20261019`
- Start HEAD: `3f7c32a8b5e3760d5e4debcf63b7af9b0a6c3e82`
- Resolved historical candidate `16bb2bc`: `16bb2bc93ef4d2064cb05fcb6c55b5902ea48c69`
- Prior source `f849d989`: `f849d9897abbbb544be9744c6352ae2a3462ed01`
- The branch was one commit ahead of the historical candidate at start. That later commit was retained.

## Identity normalization

The canonical identity record is `store/partner-center-identity.json`. The builder and regression tests read that record. The duplicate legacy identity JSON was removed only after these references were migrated.

The recorded values are retained from the owner-provided Partner Center identity screenshot dated 2026-10-18:

- Store ID: `9PND0HG61XD6`
- Identity Name: `OkinawaDesktopTools.ScheduledAPIRunner`
- Publisher: `CN=46263F21-A700-41DB-8C9B-114C22FB82FC`
- PublisherDisplayName: `Okinawa Desktop Tools`
- Recorded PFN: `OkinawaDesktopTools.ScheduledAPIRunner_j8yefg9jgfh58`

The canonical record explicitly has `partner_center_rechecked: false` and `submission_allowed: false`. The screenshot is historical evidence, not a live Partner Center verification. These values must be copied and compared character-for-character from the existing product before submission. No new Store product is to be created.

## Version normalization

The former draft metadata recorded `0.1.0.0` as the initial MSIX version. That value is retained as `legacy_initial_msix_version`, not used as the current package version. The current source does not define a separate internal application version, so `internal_app_version` is explicitly null with status `NOT_DEFINED_IN_SOURCE`; no runtime or project version is invented.

The explicit technical build candidate is `1.0.0.0` in `store/msix-version.json`. It is **not** approved as a public release version. The previous accepted Store package version and Partner Center package history have not been independently verified, so public release remains on hold.

Microsoft's package-version guidance for Windows 10/11 Store packages states that the first component cannot be 0 and that the fourth component is reserved for Store use and must be 0:
https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements

The builder uses the version configuration through `store/msix_version.py`; it no longer falls back to the internal version or a hardcoded `0.1.0.0`. Validation requires the supported `msix` / `packaged_classic_desktop` package type, exactly four canonical numeric components, each no greater than 65535, major at least 1, and revision 0. Missing or invalid settings fail closed.

## Validation status

- Source migration and regression tests are committed on the existing Draft PR branch only.
- GitHub Actions after the migration: pending observation; a queued or pre-run failure is not a test pass.
- Local Windows test execution and fresh MSIX build: not run by this audit session.
- Fresh MSIX SHA-256: not yet available until a current-head Windows build completes.
- MSIX install/launch, installed app input/output, restart/persistence, screenshots, and WACK: not tested here.
- Previous install error `0x800B0109` remains a trust/certificate issue; no certificate stores or security settings were changed.
- Partner Center package-history verification: pending owner-side check.
- Submission and public release: BLOCKED.

The historical test/build numbers in the 2026-10-20 status report refer to its recorded source head and must not be treated as fresh results for this migration.
