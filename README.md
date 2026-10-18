# Scheduled API Runner

指定時刻または一定間隔で、許可済みHTTPS APIを決められた設定どおりに呼び出す小型ジョブランナーです。

## MVP

- `daily` / `interval` スケジュール
- HTTPSのみ
- `allow_hosts` に含まれるAPIだけ実行
- 固定回数Retry
- Timeout
- Dry Run
- SQLiteで同じスケジュール枠の二重実行を防止
- JSON Lines監査ログ
- `${ENV:NAME}` で秘密情報を環境変数から参照

## 実行

```powershell
python scheduled_api_runner.py jobs.example.json --once --dry-run
python scheduled_api_runner.py jobs.example.json --once
python scheduled_api_runner.py jobs.example.json
```

Google OAuthは別Connectorとして追加し、Refresh Token等を設定JSONへ直書きしない設計にします。

## Daily CSV desktop flow (improvement branch)

Run `python api_job_gui.py` to set an approved HTTPS JSON source, select an **existing** CSV, choose fields and an explicit same-date policy, then validate/save/run. Saving creates a new JSON file; it never silently overwrites an existing configuration. Use **Install Windows daily task** only after saving and explicitly confirming. This per-user Windows Task Scheduler task calls `scheduled_api_runner.py --once` at the configured local time when the user is signed in. Remove the task from the GUI before changing installations or job IDs. The original in-window Start/Stop control still stops when the window closes. Python, the runner script, environment variables and the saved JSON must remain available at the registered paths. No direct .xlsx update or unattended signed-out service is claimed.

Run `python -m unittest discover -s tests -v` and inspect the actual Windows task before sale. GitHub Actions on this private repo have previously failed before any steps execute; a failed runner-allocation job is not a test verdict. The separately evolving `feat/api-dated-series-writer-20261018` branch has a richer desktop implementation: compare and integrate deliberately before choosing the release candidate. Store submission: **HOLD**.
