# Scheduled API Runner: Partner Center identity and acceptance gate

**Source:** Owner-provided Microsoft Partner Center "View product identity" screenshot, 2026-10-18. The product frame already exists; **do not reserve/create another product**.

| Field | Owner screenshot |
|---|---|
| Product | Scheduled API Runner |
| Partner Center Store ID | `9PND0HG61XD6` |
| Package/Identity/Name | `OkinawaDesktopTools.ScheduledAPIRunner` |
| Package/Identity/Publisher | `CN=46263F21-A700-41DB-8C9B-114C22FB82FC` |
| PublisherDisplayName | `Okinawa Desktop Tools` |
| Package Family Name (PFN) | `OkinawaDesktopTools.ScheduledAPIRunner_j8yefg9jgfh58` |
| Package SID | `S-1-15-2-3008249920-2929892902-3778477264-271625836-470284654-1826978305-727288587` |
| Product release | `Start submission` available; no submission shown |

**Important:** Before preparing a final MSIX, independently re-copy Store ID, Identity Name, Publisher and PFN using Partner Center's copy buttons. In particular distinguish similar-looking letters and digits in a screenshot (0/O). Never silently invent or change an ID to pass packaging. Package SID/PFN are references; they do **not** go into a manifest Identity. The MSIX manifest Name and Publisher must exactly match Partner Center.

## State of the app code (not the Store registration)

The draft branch includes a joined beginner workflow: manually inspect JSON fields, transfer selected scalar fields into a multiline daily CSV wizard, set optional API auth ENV references, preview, and register an opt-in Windows task. Source has not been Windows-verified; private Actions jobs still fail before steps, and the MSIX is the code operator's next stage.

## No-sales acceptance conditions

1. Code operator clones the exact Draft PR branch into a new isolated Windows folder. Never overwrite `main`, published EXEs/MSIX, saved client configuration, or backups.
2. Run the complete Windows tests and collect `PASS` logs for the exact commit. Current GitHub Actions workflows on this repository show **failed jobs with zero executed steps**. Cause is **not established**. Do not count them as test failures or passes without runner evidence.
3. Verify real interactive GUI navigation (Japanese/English), fresh-user setup, full windows at 100%, 125%, 150% display scaling, keyboard navigation, DPI clipping and clear error messages. Current GUI implementations are **not equivalent in beginner usability**.
4. Use safe, user-owned test fixtures only, including interrupted operations, duplicate outputs, concurrent actions, changed rules after a preview, and prevention of repeated destructive actions.
5. Build a versioned MSIX with the exact Name/Publisher, validate manifest, package signing and installation on a clean Windows machine, update/uninstall behavior and persistence; run store-related certification tests.
6. Check brand rights, third-party licenses/notices, approved icons and genuine screenshots, support/privacy links, Store descriptions, pricing and markets.
7. Keep Partner Center in a draft. Do not upload or submit for certification until acceptance is signed off and the owner explicitly authorizes it.

**Result today: STORE PRODUCT FRAME CREATED; SOURCE WORK IN DRAFT; COMMERCIAL RELEASE HOLD.**


## Repository identity source update — 2026-10-23

The canonical repository record is now `store/partner-center-identity.json`. It preserves the owner-provided 2026-10-18 screenshot values but explicitly records `partner_center_rechecked: false`. It is not proof of a live Partner Center recheck. Re-copy the fields from the existing Store product immediately before any submission. The product remains on submission hold.
