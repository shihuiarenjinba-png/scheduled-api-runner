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

## Local preflight

1. Checkout the exact `product.source_sha` from `store-product-handoff.json`.
2. Run `python -m unittest discover -s tests -v`.
3. Recompute the MSIX SHA256 and require an exact match to both
   `msix.sha256.txt` and `store-product-handoff.json`.
4. Use MakeAppx only to unpack for inspection; do not weaken Windows security or
   install a trust certificate merely to run an unsigned technical draft.
5. Confirm the unpacked EXE SHA matches `package.exe_sha256`.
6. Run the unpacked EXE self-test and physical GUI acceptance.

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
