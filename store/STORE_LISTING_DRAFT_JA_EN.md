# Microsoft Store listing copy — scheduled-api-runner

**DRAFT / Commercial HOLD.** Product slot already exists in Partner Center (Store ID `9PND0HG61XD6`). Do not create a duplicate listing or submit unapproved packages.

## 日本語

**製品名（予約済み）:** Scheduled API Runner

**短い説明:**
指定したHTTPS APIへのリクエストを、Windows PCから手動または定期実行。設定の試運転・承認に対応。

**長い説明:**
Scheduled API Runnerは、設定したHTTPS APIを指定時刻に呼び出すWindowsデスクトップツールです。初回画面では保存場所・ジョブ名・URL・時刻を入力し、GETリクエストの設定を作れます。試運転で通信先と設定を確認し、承認後に1回実行または定期実行を開始します。定期実行はアプリが動作している間に限られます。POST等の更新操作、認証ヘッダー、複数ジョブなどの高度な設定は、別途JSON編集が必要です。実際のAPIの接続先と利用権限は利用者が準備します。

**動作条件・注意:** User-controlled API endpoints, credentials and network permissions; no hosted service.
Microsoft Store版の正式な対応OS、アイコン、販売価格、データ宣言、プライバシー/サポートURLは未承認です。第三者の情報・権利・利用規約に従って使用してください。

## English

**Short description:**
Run approved HTTPS API requests once or on a schedule from Windows, with dry-run validation before live execution.

**Long description:**
Scheduled API Runner runs explicitly configured HTTPS API requests from your Windows PC. The first-run wizard creates a daily GET check; after an offline Dry Run, you can approve a single run or start the scheduler. Scheduling works while the app is running. Mutating requests, headers, authentication and multi-job workflows require advanced JSON configuration. Users supply their authorized API endpoint and credentials.

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
