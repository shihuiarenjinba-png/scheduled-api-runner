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
