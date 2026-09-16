# Scheduled API Runner

指定時刻または一定間隔で、許可済みHTTPS APIを決められた設定どおりに呼び出す小型ジョブランナーです。

## MVP

- `daily` / `interval` スケジュール
- HTTPSのみ
- `allow_hosts` に含まれるAPIだけ実行
- 3xx redirectは追従せず拒否
- URL userinfo/fragmentを拒否
- 固定回数Retry
- Timeout
- Dry Run
- SQLiteで同じスケジュール枠の二重実行を防止
- `running` / `failed` / `succeeded` の実行状態管理
- JSON Lines監査ログ
- `${ENV:NAME}` で秘密情報を環境変数から参照

## 実行

```powershell
python scheduled_api_runner.py jobs.example.json --once --dry-run
python scheduled_api_runner.py jobs.example.json --once
python scheduled_api_runner.py jobs.example.json
python -m unittest discover -s tests -v
```

## 実行枠の扱い

- `succeeded`: 同じrun keyは再実行しない
- `failed`: `failure_retry_seconds` 経過後に再試行可能
- `running`: `running_stale_seconds` 未満は二重実行を防止し、古くなった実行は再取得可能

API実行前に永久claimする方式ではないため、ネットワーク障害等で失敗しても、その時間枠を回復不能にしません。

## Network safety / ネットワーク安全性

最初のURLがallowlist済みでも、HTTP redirectで別ホストへ移動することは許可しません。接続先は最初から最後まで指定したHTTPSホストに固定します。ログには認証ヘッダや完全な秘密値を記録しない設計を維持します。

Google OAuthは別Connectorとして追加し、Refresh Token等を設定JSONへ直書きしない設計にします。
