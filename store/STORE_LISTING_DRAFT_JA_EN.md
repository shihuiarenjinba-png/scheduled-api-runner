# Microsoft Store listing copy — scheduled-api-runner

**DRAFT / Commercial HOLD.** Product slot already exists in Partner Center (Store ID `9PND0HG61XD6`). Do not create a duplicate listing or submit unapproved packages.

## 日本語

**製品名（予約済み）:** Scheduled API Runner

**短い説明:**
許可したHTTPS APIの必要なJSON項目を日付付きCSV履歴に蓄積。試運転・承認・既存データ保護に対応予定。

**長い説明:**
Scheduled API Runnerは、設定したHTTPS APIを指定時刻に呼び出すWindowsデスクトップツールです。初回画面では保存場所・ジョブ名・URL・時刻を入力し、GETリクエストの設定を作れます。API項目画面の右側は通信しない設定プレビューであり、接続や取得成功を保証するものではありません。試運転で通信先と設定を確認し、承認後に1回実行または定期実行を開始します。アプリ内で開始するスケジューラはアプリの稼働中に動作します。別途、Windowsログオン中の定期GET＋CSV履歴更新用タスクをユーザー承認で登録する機能を開発しています（販売前実機検証中）。POST等の更新操作、認証ヘッダー、複数ジョブなどの高度な設定は、別途JSON編集が必要です。実際のAPIの接続先、利用権限、可用性は利用者が確認します。

**動作条件・注意:** User-controlled API endpoints, credentials and network permissions; no hosted service.
Microsoft Store版の正式な対応OS、アイコン、販売価格、データ宣言、プライバシー/サポートURLは未承認です。第三者の情報・権利・利用規約に従って使用してください。

## English

**Short description:**
Collect authorized HTTPS JSON API values into dated CSV history with dry-run approval and duplicate-date protection.

**Long description:**
Scheduled API Runner runs explicitly configured HTTPS API requests from your Windows PC. The API-fields screen shows an offline configuration preview; it does not verify connectivity or guarantee retrieval. After an offline Dry Run, you can approve a single run or start the scheduler. The in-app scheduler runs while the app remains open. A separate opt-in Windows interactive-logon task for daily dated GET-to-CSV updates is under validation. Mutating requests, headers, authentication and multi-job workflows require advanced JSON configuration. Users supply and verify their authorized endpoint, credentials, permissions, and availability.

**Requirements and limits:** User-controlled API endpoints, credentials and network permissions; no hosted service.

## Screenshots and onboarding captures to collect on Windows

1. First-run homepage showing product purpose and 3-step workflow (JP)
2. Same screen in English
3. Guided form with realistic but fictional inputs and no secrets
4. No-write Dry Run result and one-time confirmation
5. Non-sensitive error state on deliberately invalid input

Screenshots must be genuine program windows with placeholder/test-only data; no account IDs, API keys, personally identifying file names or private website contents.

## Before filling Partner Center

- [ ] Confirm these descriptions against built product on Windows (do not imply features available in GUI when JSON is required)
- [ ] Verify the actual reserved title in Partner Center rather than the repo slug above
- [ ] Approve icon, logo, screenshot rights, third-party notices, license and end-user terms
- [ ] Decide price, markets, age rating, privacy/support URLs and offline/online dependencies
- [ ] Compare the final MSIX Identity/Publisher with `store/PARTNER_CENTER_IDENTITY_HANDOFF_20261018.md`
- [ ] Full QA and explicit owner approval before pressing **Submit for certification**

**This copy is prepared documentation only, not evidence of Microsoft Store acceptance.**



## 次期バージョン候補：API時系列取得（検証前・販売文面未承認）

**日本語の訴求案：** 許可したHTTPS GET APIから必要なJSON項目と観測日付を抽出し、既存のCSV履歴へ1日1行ずつ追加するWindowsツール。同じ日付を重複保存せず、更新前の独立したバックアップを残します。JSON項目の手動プレビュー・設定テンプレート、任意のWindowsタスクスケジューラ登録を開発中です。

**English draft:** Collect selected fields and observation dates from user-approved HTTPS GET JSON APIs. Keep a dated CSV history, skip duplicate dates by default, and create an independent backup before updating an existing file. Optional user-approved Windows Task Scheduler registration is under verification.

**Limitations to disclose:** No generic web scraping, third-party API keys included, hosted/cloud acquisition, unlimited API quotas, automatic OAuth, direct modification of existing .xlsx workbooks or guaranteed catch-up when PC is off. Windows task works only while signed in and config is unchanged. Existing JSON scheduler advanced mutating methods require separate safety warnings. These features are **development-only until exact-commit CI and Windows API/CSV acceptance pass**.

