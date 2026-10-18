# API JSON Explorer — source implementation draft (2026-10-18)

Status: **SOURCE DRAFT / COMMERCIAL HOLD.** This changes only a new Git branch. No main/release rewrite, no signed MSIX, no Store submission.

## What a customer can do on this branch

1. Open the desktop application and select the new default **API Data Explorer** tab.
2. On the **left**, enter an HTTPS API URL, an optional header name and a session-only secret header value. Add up to **10 independent endpoints**.
3. Name the response fields to extract, one per line. For example:
   - Order = orders[*].id
   - Revenue = orders[*].total
   - Customer = orders[*].customer_name
   - Grand Total = total
4. Click **Offline preview** to check the URL and field paths without any network calls.
5. Click **Fetch GET**, review each destination host in the confirmation, and then make exactly one GET per configured source. The old preview is consumed on entry.
6. See the selected API response on the **right** as rows and a shortened raw JSON preview; select among fetched sources. Click **Suggest fields** to put automatically discovered JSON paths back into the left-side field editor, then review and preview again.
7. Explicitly save the fetched data to a **new** .xlsx workbook (one sheet per API, real JSON numeric values remain numeric), .txt file (textual values), or raw .json. Existing output files are never overwritten.
8. Save and reload a separate JSON **template** of source URLs/field paths; sensitive header *values* are intentionally not written to the template.

The extractor works for objects, top-level arrays, nested keys, fixed indexes [0], and a **single repeating array** [*] per field. Multiple fields sharing one repeating array are aligned into the same spreadsheet row; a scalar field is repeated for each such row. Nested wildcards, joins between unrelated arrays, paginated APIs, XML/CSV responses and provider-specific OAuth are **not** implemented. Text values are not guessed to be numbers.

Example response:
- {"orders":[{"id":1,"total":42.5},{"id":2,"total":10.0}],"total":52.5}
- Desired fields:
  - Order = orders[*].id
  - Revenue = orders[*].total
  - Grand Total = total

This generates two rows, keeping Revenue and Grand Total numeric in Excel.

## Safety boundaries

- HTTPS, DNS hostnames, port 443 only. IP literals and local names refused.
- DNS resolves immediately before each network call. All resulting IPs must be public; connect to the validated IP with TLS hostname verification, avoiding a second unchecked DNS lookup.
- No redirects, automatic retries, cookies, external proxies, mutating HTTP methods or automatic upload.
- GET can still cause provider-side effects in an unusual API; only use a service/account you are authorized to call.
- Only one in-flight UI acquisition, up to 2 MB response per source and 50,000 extracted rows. Display truncates to 500 visible rows/30 KB JSON but exports all extracted rows.
- No URLs or auth header values printed to error dialogs. An auth value lives only in the UI process memory; never stored in templates or exports.
- URLs containing obvious credential query parameter names are refused; callers must not put credentials in URL paths or nonstandard query names.
- Saving writes to same-directory temporary file and exclusively hard-links to a new output, never replacing existing customer files.
- Do not assume every JSON API can be handled: field selection, access limits, pagination, authentication and licensing vary by provider.
- Export may contain sensitive provider data; user explicitly chooses a local output destination.

## Validation needed

Run on exact commit: python -m unittest discover -s tests -v
And: python desktop_app.py --self-test

Still required:
- Real Windows Tk display at 100/125/150%, Japanese and English, source switching and scrolling; no clipping.
- Check workbook in Excel and third-party spreadsheet apps (including Unicode, formulas-as-text, empty arrays and malformed values).
- Authorized external API trial with header auth and varying JSON schemas; do not use production keys in evidence.
- Ensure connection failure, HTTP 429, timeouts and closing the window during a request are handled clearly.
- Multi-source partial failure review and secret-redaction review.
- Packaging/install/update/uninstall, rights/notice, Store description, price and complete MSIX validation.
- GitHub Actions job steps currently absent, so authored tests must **not** be called PASS until executed.

## Scheduling distinction

The **new** JSON explorer provides **manual fetch and export**. The existing legacy scheduler remains accessible on the separate tab and retains its prior JSON-based job format. The two formats are NOT interchangeable, and scheduled collection into Excel is NOT YET implemented. Design that capability separately after acceptance testing; avoid claiming it works in Store listing copy.
