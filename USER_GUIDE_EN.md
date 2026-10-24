# Scheduled API Runner — User Guide

## Language

Use **`言語 / Language`** in the upper-right corner to select `日本語` or `English`. The selection is retained for the next launch.

## Normal workflow

1. Choose the configuration JSON.
2. Use `Validate` to check configuration, environment references, and allowed hosts.
3. Run `Dry Run All` first.
4. After reviewing the result, use `Run Enabled Once` or `Start Scheduler` only when appropriate.

## Safety behavior

- Live execution sends real requests to external APIs.
- Enabled POST / PUT / PATCH / DELETE jobs trigger an additional warning.
- 3xx redirects are rejected rather than followed.
- Requests cannot leave the allowed-host boundary.
- Only successful runs are permanently claimed; failed runs can retry after the configured delay.
- Secret values and full sensitive URLs are not intentionally shown in the UI/audit view.

Complete every applicable item in `SALES_RELEASE_CHECKLIST.md` before commercial distribution.
