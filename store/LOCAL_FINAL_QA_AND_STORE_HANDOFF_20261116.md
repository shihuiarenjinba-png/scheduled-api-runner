# Scheduled API Runner — local final QA and Store handoff

GitHub is responsible for building and binding the exact candidate. Local Windows is
responsible only for final physical QA and the later approved Store action.

## Download

Use the successful exact-head workflow artifact:
`ScheduledApiRunner-Store-MSIX-UNSIGNED-DRAFT`.

The artifact must contain:
- the MSIX;
- `msix_validation.json`;
- `msix.sha256.txt`;
- `store-product-handoff.json`;
- Store listing/privacy/runFullTrust documents.

Do not rebuild before QA. A rebuild creates different package bytes.

## Exact artifact staging

Use Windows-all-auto's checked-in Group B registry rather than manually typing the
repository/artifact name:

```powershell
python scripts/pull_group_b_store_product.py `
  --product-id scheduled-api-runner `
  --run-id <exact successful GitHub Actions run id> `
  --target-root C:\path\to\group-b-local-inbox `
  --receipt C:\path\to\evidence\artifact-pull-receipt.json
```

The pull receipt is immutable evidence only. It must record no Store submission,
certification, or publication.

## Local preflight

GitHub CI is the primary test environment. Do not duplicate the full unit/reliability
suite locally merely because the artifact reached the physical Windows machine.

1. Use the exact successful GitHub artifact and its `store-product-handoff.json`.
2. Confirm the local MSIX file exists and recompute its SHA256; require an exact match
   to both `msix.sha256.txt` and the handoff.
3. Use Windows-all-auto's common local pre-upload conveyor to unpack the same MSIX and
   verify Manifest Identity / Publisher / Version / Architecture plus the main EXE SHA.
4. Do not rebuild the product locally. A rebuild is a different candidate.
5. Do not install a temporary certificate, weaken Windows security, or bypass
   Application Control merely to run an unsigned technical draft.
6. Perform only Windows-specific/product-specific physical acceptance that GitHub CI
   cannot prove.

Preferred common entrypoint after the exact artifact is staged:

```powershell
pwsh -File .\scripts\run_store_preupload_readiness.ps1
```

from the checked-out Windows-all-auto worktree with this product's exact handoff and
package path. `READY_FOR_MSIX_UPLOAD_APPROVAL` is only an approval boundary; it does
not authorize an upload.

## Product acceptance

- JP/EN first-run workflow;
- 100/125/150% DPI;
- authorized non-production HTTPS GET;
- dated CSV append and duplicate-date protection;
- secret redaction;
- Windows Task Scheduler register -> run -> verify -> unregister;
- restart/persistence and normal exit.

Record failures as HOLD. Do not upload a package that differs from the verified SHA.

## Store lane

After local PASS:
1. reverify the existing Partner Center product and exact identity;
2. classify initial submission vs update from the live page, never from repo memory;
3. complete security/assets/price/audience fields with owner-confirmed values;
4. run Windows-all-auto validation and Windows-Automator DRY_RUN;
5. obtain separate approval for package upload.

Certification submission and Publish remain separate later approvals.
