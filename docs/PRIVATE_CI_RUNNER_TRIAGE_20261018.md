# Private-repository CI runner triage — 2026-10-18

**This document records an external test-execution blocker, not an application PASS/FAIL.**

New GitHub Actions runs on this **private** repository report failure
within seconds with **zero recorded execution steps**. Attempts to retrieve a
failed job log returned GitHub's 404 BlobNotFound. Public sibling
workflow-automation-hub, by contrast, successfully ran Windows tests,
GUI evidence capture, EXE build and unsigned MSIX validation.

This pattern is **consistent with**, but does not prove, a GitHub Actions
hosted-runner allocation/billing/usage restriction on private repositories.
Do not edit code or rerun jobs blindly as if they were failing unittest
assertions. Per GitHub official documentation, standard Actions runners are
free for public repositories but private runners draw from the account's
monthly minutes/storage allowance and may be blocked by billing/budget limits.

## Owner/operator verification procedure

1. Open the exact failed run, read the top-level failure banner and any
   account-level notification. Do not infer cause from missing steps alone.
2. In GitHub Settings → Billing and licensing → Usage/Budgets, inspect current
   Actions minutes, artifact storage, payment eligibility and any account
   spending caps. Review the repository Settings → Actions → General
   permissions for workflow execution.
3. Check whether the private repositories are suspended/disabled from Actions
   or have runner policy restrictions. Never expose API tokens/billing
   information in a public issue or test log.
4. If the blocker is account billing, resolve it in the user's own account
   controls with consent. Do **not** autonomously purchase or increase budget.
5. After runner allocation becomes available, run unittest on the *exact PR
   head SHA* for Windows and Ubuntu, then record the run URL and SHA.
6. A local Windows code-operator test can reveal code failures without waiting
   for hosted runner usage; but it does not count as GitHub CI success.
7. Keep customer files, published releases and `main` unchanged until
   regression testing, executable/MSIX packaging, licensing and owner approval.

Official docs:
- https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/how-tos/monitor-workflows/view-job-execution-time

**Do not remove the Store HOLD merely because the runner is unblocked.**

## Confirmed example run

Repository: `scheduled-api-runner`
Failed run URL: https://github.com/shihuiarenjinba-png/scheduled-api-runner/actions/runs/39112085948

