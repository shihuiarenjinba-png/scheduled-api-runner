# Scheduled API Runner

指定時刻または一定間隔で、許可済みHTTPS APIを決められた設定どおりに呼び出す小型ジョブランナーです。

## Windows Desktop / デスクトップ

通常利用では `desktop_app.py` / 将来のWindows EXEから操作できます。

GUIは秘密値を表示せず、次だけを概要表示します。
- ジョブ名
- daily / interval schedule
- HTTP method
- 接続先host
- enabled状態
- `allow_hosts`

実API送信の前に **Dry Run All** を用意しています。POST / PUT / PATCH / DELETEを含む有効ジョブがある場合、Live実行前に追加警告を表示します。

```powershell
python desktop_app.py
# または
run_desktop.bat
```

## Core MVP

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

## CLI / 開発者向け

```powershell
python scheduled_api_runner.py jobs.example.json --once --dry-run
python scheduled_api_runner.py jobs.example.json --once
python scheduled_api_runner.py jobs.example.json
python -m unittest discover -s tests -v
```

## 安全な更新系API実行（レビュー中）

この作業ブランチでは、GETとPOST/PUT/PATCH/DELETEを区別します。

- **GET**: 設定した回数まで再試行し、失敗時はスケジュール枠のバックオフ後に再実行できます。
- **POST/PUT/PATCH/DELETE**: 通信タイムアウトやHTTPエラーがあっても、**同じリクエストの自動再送は行いません**。設定済みのretries値は無効になります。
- 更新系ジョブの結果が失敗・不明なとき、そのスケジュール枠の状態を `uncertain` として記録します。実行中にアプリが落ちた場合も、古い `running` を同じ枠では自動回収しません。
- 同名ジョブを拒否し、状態DBの接続を明示的に閉じます。GUIは手動実行中の重複操作を防ぎます。

**重要な限界:** 外部APIが実際に処理したかまでは判定できません。「厳密な一度だけ実行」を保証するものではありません。更新系ジョブは**次のスケジュール枠**や明示的な手動 `--once` で再び送信できます。送信後に応答を失った場合は提供元の処理履歴・idempotency keyなどで状態を照合してから、手動で再送してください。送信を伴うテストでは所有・許可されたAPI環境を使ってください。

追加回帰テスト: `python -m unittest discover -s tests -v`。GitHub ActionsまたはWindows実機での実行結果を確認するまでは未検証として扱い、Store販売を承認しません。

## 実行枠の扱い

- `succeeded`: 同じrun keyは再実行しない
- `failed`: GETのみ `failure_retry_seconds` 経過後に再試行可能
- `uncertain`: 更新系の結果が不明。同じ枠では自動再実行しない
- `running`: GETは `running_stale_seconds` を超えると再取得可能。更新系は再取得禁止

GETの再試行は維持しますが、更新系APIは未確認の副作用を避けるため安全停止を優先します。

## Network safety / ネットワーク安全性

最初のURLがallowlist済みでも、HTTP redirectで別ホストへ移動することは許可しません。接続先は最初から最後まで指定したHTTPSホストに固定します。ログとGUIには認証ヘッダや秘密値を表示しない設計を維持します。

Google OAuth系は専用Connector側で扱い、Refresh Token等をこのRunnerの設定JSONへ直書きしません。

## GUI preview-before-live change (2026-10-18, unverified draft)

The Japanese/English desktop now shows an explicit three-stage workflow:
select a JSON file → Validate/Dry Run → confirm once or start scheduler.

- The desktop requires a **successful** Dry Run for the exact unchanged
  JSON file path and content. Validation of one config never approves another.
- While Dry Run is active, a second live/scheduled operation is blocked.
- A live run or start of scheduling consumes approval before any API call,
  so an ambiguous response cannot silently grant another replay.
- UI worker-error callbacks preserve the error text for the main thread;
  changing the display language is blocked while processing.
- This is a **GUI safety gate**. The explicit CLI `--once` entrypoint remains
  a user-directed operation and must not be advertised as guarded by the GUI.
- **GitHub Actions is blocked before test steps** on this branch; see
  `QA_HANDOFF_20261018.md`. Do not claim PASS or sell this code.

## 起動時に分かる画面 / First-run guided GUI (draft 2026-10-18)

Windows用GUIは起動すると **「はじめに・新規設定 / Start here」** を表示します。

- **何をする商品か：** Windows上で指定したHTTPS APIへ、指定時刻にリクエストを送るツール。クラウドサーバー不要。定期実行にはアプリを開いたままにする必要があります。
- **初心者向け設定：** 作業用フォルダー、ジョブ名、HTTPS URL、毎日の時刻を入力 → 新規JSON保存 → 詳細画面でDry Run → 明示的承認 → 1回実行または定期実行。
- **この画面で作れるのはGETのみ：** POST/PUT/PATCH/DELETE、認証ヘッダー、複数ジョブなどは既存の詳細JSONが必要です。無い機能をあるように販売説明しません。
- **保存時の安全性：** JSONを保存するだけではAPIを送信しません。既存JSONは上書きしません。秘密値入りURL、IPアドレス、ローカルホスト、非HTTPS、非標準ポートを初心者フォームで拒否します。
- **試運転：** 通信しない設定検証です。サーバーの応答を予測・再現するものではありません。設定が変わったら試運転からやり直し。
- **販売状況：** CI/実機/MSIX/Store審査はHOLD。コード担当は初心者の操作体験をWindows実機で検証してください。

### Japanese/English
The opening page explains the product purpose, includes a GET-only daily-check
wizard, saves a new JSON without making network requests, then navigates to
the advanced view for Dry Run and deliberate execution. Advanced requests
still require JSON editing; the beginner wizard does not support arbitrary API
configuration. Run `python -m unittest discover -s tests -v` on a verified
Windows build and review `tests/test_guided_config.py`.


## JSONデータ取得画面 / JSON API Data Explorer (Draft 2026-10-18)

A new **first tab** lets customers enter one or more HTTPS GET endpoints on the
left, select JSON field paths, then view fetched rows and raw JSON on the right.
It supports up to 10 independent API sources and up to 32 selected fields each.
Examples: Order = orders[*].id, Revenue = orders[*].amount, Total = total.
You can save a new, non-overwriting Excel .xlsx workbook (real JSON numbers are
numeric cells), text .txt, or raw .json. User-created source/field templates
are JSON behind the GUI; header **values** are not saved.

**Important:** This is a new, **manual** fetch/export feature, not scheduled
Excel export. The old advanced JSON scheduler remains in its own tab. Offline
preview is NOT a test of the live API response. Running a GET requires separate
confirmation of the destination hosts; there are no automatic retries. Some
services require OAuth, pagination or rate-limit handling which this initial
feature does not yet support. Use authorized APIs only.

Implementation and QA limits: docs/API_JSON_EXPLORER_DRAFT.md.
The new tests are *authored*, not CI-PASS. No main merges, MSIX sale or Store
submission are authorized from this branch.
