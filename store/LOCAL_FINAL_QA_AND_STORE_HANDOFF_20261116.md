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
  --target-root C:\path\to\group-b-local-inbox `
  --receipt C:\path\to\evidence\artifact-pull-receipt.json
```

The wrapper auto-discovers a unique successful Store-build run for the current
registered branch HEAD. If none exists it HOLDs; if more than one exact-head success
exists it requires an explicit `--run-id` rather than guessing.

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

## Current frozen-candidate state — 2026-11-17

The frozen candidate has already completed exact artifact staging and local static
confirmation. Do **not** repeat those steps unless evidence integrity is lost.

Current state:

`APPLICATION_CONTROL_BLOCKED_STORE_SIGNED_QA_REQUIRED`

Frozen candidate:

- source: `28ef873ab2ff325b8f26c61a9ba48701280e8290`
- run: `44093493317`
- artifact ID: `14333575447`
- artifact digest:
  `sha256:b45d53a0473f5b8cdcac64c1ffdcf12957919da2e5cb846564344d757165afa7`
- MSIX SHA256:
  `db599cdfa673688e8fe7db70d11acc69010562636c67f4996b4cba36adfd8877`
- unpacked EXE SHA256:
  `06d3b92bd83281750e5a454f9add6526fa90f6bfc29017fd6919bbeaa64213d9`

Already confirmed locally:

- immutable artifact receipt;
- repeated evidence/workspace/template creation refused and prior evidence hashes
  unchanged;
- MakeAppx unpack PASS;
- Manifest Identity / Publisher / Version / Architecture PASS;
- unpacked EXE SHA PASS;
- Defender custom scan: no threats for the exact MSIX and EXE;
- Authenticode: MSIX and EXE are `NotSigned`, which is expected for this lane;
- no rebuild, install, security bypass, Store write, or local duplicate full CI suite.

The local-final QA template remains `HOLD`. Static verification is complete and the
one-shot unsigned launch has also completed with an Application Control block. Do not
repeat either step. Remaining physical QA resumes only on the Store-signed Private
distribution of the same frozen candidate.

## One-shot unsigned exact EXE launch

After the exact artifact and static package checks are complete, perform at most one
normal-user launch attempt of the exact unpacked EXE. Use the shared
Windows-all-auto wrapper rather than an ad-hoc launcher:

```powershell
pwsh -File .\scripts\run_unsigned_exact_exe_smoke.ps1 `
  -ExePath <exact unpacked ScheduledApiRunner.exe> `
  -ExpectedSha256 <package.exe_sha256 from store-product-handoff.json> `
  -OutputReceipt <new evidence path> `
  -ObservationSeconds 60
```

Requirements:

- run from a non-elevated PowerShell session;
- the wrapper re-hashes the EXE immediately before launch;
- exactly one launch attempt;
- no `RunAs`, temporary certificate, security-policy change, or alternate bypass;
- no MSIX install or Store operation.

If Code Integrity evidence is observed, record
`APPLICATION_CONTROL_BLOCKED` and stop. Do not retry or bypass it.
If the process starts but is still open after the observation window, do not relaunch;
close it normally through the app UI and preserve the HOLD evidence.
A clean exit only proves the launch/normal-exit slice. The overall local QA remains
`HOLD` until the remaining product acceptance checks pass.

Bind the launch evidence into a new QA evidence file with:

```powershell
python scripts/apply_unsigned_exe_launch_receipt.py `
  --handoff <store-product-handoff.json> `
  --qa-template <local-final-qa-template.json> `
  --launch-receipt <unsigned-exe-launch-receipt.json> `
  --output <new launch-bound-local-qa.json>
```

The binder never upgrades the whole product to PASS and never authorizes Store write.

## One-shot launch result — 2026-11-18

The authorized one-shot launch of the frozen exact unsigned EXE is complete.

Final classification:

`APPLICATION_CONTROL_BLOCKED`

Observed:

- launch attempts: `1`
- normal user context: yes
- process started: no
- exit code: N/A
- normal exit: no
- original wrapper status: `LAUNCH_FAILED`
- delayed Code Integrity block-class events: `3033`, `3077`
- supplemental event: `3118`
- policy: `VerifiedAndReputableDesktop`
- policy GUID: `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`
- policy ID: `27555.1000.240208`
- correlation Activity ID: `{2f3574e4-74dd-0008-cd37-9c3add74dd01}`
- status: `0xc0e90002`
- event flat hash:
  `06D3B92BD83281750E5A454F9ADD6526FA90F6BFC29017FD6919BBEAA64213D9`
- event flat hash == frozen EXE SHA256: yes
- residual process count: `0`
- security bypass: none
- second launch: none

The original launch receipt remains immutable. It must not be edited from
`LAUNCH_FAILED` to `APPLICATION_CONTROL_BLOCKED`.

Instead, normalize the later Code Integrity evidence as a separate
`code-integrity-block-evidence/1` file and produce a third reconciliation receipt:

```powershell
python scripts/reconcile_delayed_code_integrity_launch.py `
  --handoff <frozen store-product-handoff.json> `
  --launch-receipt <original unsigned-exe-launch-receipt.json> `
  --code-integrity-evidence <code-integrity-block-evidence.json> `
  --output <new unsigned-exe-launch-reconciliation-receipt.json>
```

Then bind that reconciliation receipt into a **new** QA evidence file:

```powershell
python scripts/apply_unsigned_exe_launch_receipt.py `
  --handoff <frozen store-product-handoff.json> `
  --qa-template <local-final-qa-template.json> `
  --launch-receipt <unsigned-exe-launch-reconciliation-receipt.json> `
  --output <new launch-blocked-local-qa.json>
```

The full Local Final QA must remain `HOLD`.

Do not launch the unsigned EXE again. Do not change Windows security policy, install a
temporary certificate, use RunAs, or use an alternate launcher.

## Preferred atomic block-lane finalization

Before handing the block evidence to the Store execution owner, prefer the central
one-command finalizer:

```powershell
python scripts/finalize_application_control_block_lane.py `
  --handoff <frozen store-product-handoff.json> `
  --artifact-receipt <immutable artifact-pull-receipt.json> `
  --launch-receipt <original unsigned-exe-launch-receipt.json> `
  --code-integrity-evidence <code-integrity-block-evidence.json> `
  --output-dir <new immutable evidence directory>
```

Expected result:

`PRIVATE_STORE_SIGNING_LANE_READY`

It atomically creates:

- `unsigned-exe-launch-reconciliation-receipt.json`
- `pre-store-static-qa-receipt.json`
- `handoff-after-pre-store-static-block.json`

It does not relaunch the EXE, alter Windows security, install the package, or perform
any Store/Partner Center write. If validation fails, partial staging is removed and
the lane remains HOLD.

## Store-signed Private QA lane

Because the exact unsigned EXE is blocked before process start, the remaining GUI and
product-specific physical QA must move to a Microsoft Store-signed Private
distribution of the same frozen candidate.

The code-owner lane must stop before Store writes. Hand the following immutable
binding to the Store execution owner:

- source `28ef873ab2ff325b8f26c61a9ba48701280e8290`
- run `44093493317`
- artifact ID `14333575447`
- artifact digest
  `sha256:b45d53a0473f5b8cdcac64c1ffdcf12957919da2e5cb846564344d757165afa7`
- MSIX SHA256
  `db599cdfa673688e8fe7db70d11acc69010562636c67f4996b4cba36adfd8877`
- EXE SHA256
  `06d3b92bd83281750e5a454f9add6526fa90f6bfc29017fd6919bbeaa64213d9`
- Store ID `9PND0HG61XD6`
- Identity `OkinawaDesktopTools.ScheduledAPIRunner`
- Application Control policy and events above
- package_rebuilt=false
- security_bypass_used=false
- package_installed=false
- Store write=false

After a Store-signed zero-cost Private acquisition path is available, resume physical
QA with the Store-delivered build. Do not pay to acquire the owner's own application.

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
