# Microsoft Store スクリーンショット・実入出力証拠収集指示 — 2026-10-19

## 目的と完了条件

この文書は Microsoft Store への提出素材収集を担当する Windows コード担当向けです。
商品コードの機能拡張や全面改修ではなく、**Windowsで動く完成候補を実際に起動し、ユーザーに商品の用途が伝わるPNGと実入出力を取得**します。

- 画像は実際に起動したアプリのキャプチャであること。見本画像、AI生成画像、HTMLモック、合成画像を「実行証拠」や「Storeスクリーンショット」と偽って提出しない。
- 日本語商品ページに日本語GUI、英語商品ページに英語GUI。**日本語4～5枚・英語4～5枚**を目標にする。
- Desktop向けPNGは **1366x768ピクセル以上、1ファイル50MB以内、最大10枚**。最低1枚必要。元画像を拡大して数値だけ合わせない。
- 主役は**アプリの機能を示す実GUI**。ExcelやExplorerだけを写したファイル比較は「入出力実証」の別素材として保存し、Store商品ページではアプリ自身の画面を中心にする。
- サンプルの入力ファイルと**実際に実行して生成された結果ファイル**を別フォルダーで保存し、入出力の差異をSHA256/内容で確認。
- 画像へ別ロゴ・販促キャッチコピーを後付けしない。設定前の秘密値、認証済みアカウント、トークン、個人・顧客情報、プライベートURLなどを表示させない。
- Storeへ画像とパッケージをアップロードする作業はオーナー承認のもとで進める。画像収集だけで正式提出・公開しない。

Microsoft公式:
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/screenshots-and-images
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/upload-app-packages
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements

## Windows PC内の出力先

`%USERPROFILE%\Desktop\portfolio-audit\STORE_UPLOAD_ASSETS_20261019\<Product>\`

この下に下記を用意する。

- `screenshots/ja-JP/01_home.png ...`
- `screenshots/en-US/01_home.png ...`
- `actual_inputs/` — 本当に使用したデモ入力のみ（公開可能・個人情報なし）
- `actual_outputs/` — 実行してアプリが生成したファイル
- `evidence/` — リダクト済み実行ログ、比較ハッシュ、GUI・OS環境、commit SHA、EXE/MSIXハッシュ、スクリーンショット寸法記録
- `README_UPLOAD.txt` — 各言語の画像説明と、Storeへ添付するファイル/まだ提出しないファイルの明確な区別

PNG確認：幅、高さ、PNG形式、50MB上限、画像の重複/内容の曖昧さ、言語一致、ロゴ・権利を確認。画像名とSHA256をmanifestへ記録。

**現在のGitHub ActionsにあるWorkflow Automation HubのGUI画像は964x678で、そのままではDesktop Store提出不可。** 実UI撮影の参考のみに使う。ほかの3製品は確認したCI実行に提出サイズのPNG成果物がないため実機撮影が必要。

## マイクロソフト認定との関係

StoreはMSIX提出後に自動セキュリティ/技術/コンテンツ審査を行い、公開時にStore署名を行う。Store配布のMSIXのために別途有料のCA署名証明書を購入する必要はない。ただしStore認定は個別顧客の入力・出力の動作を完全に保証するものではない。ユーザー向け宣伝画面は実機動作を正確に示すこと。

**StoreのPackagesにはMSIX、Store listingsにはPNGをそれぞれ登録する。** テスト用サンプルCSV/JSONと実出力は主に説明/検証用であり、必要時だけ認定Notes等へ安全な方法で提示する。Secretを含むログはアップロードしない。

## 最終報告

- 実行日時、Windows版、画面解像度/DPI、Git full SHA、使用EXE/MSIXのSHA256
- 製品ID/正式Identity、JP/ENスクリーンショット各枚数とパス、PNGサイズチェックのPASS/FAIL
- 実入力と実出力の絶対パス、差分の説明、元ファイル保全、実際の操作成功/未検証の区別
- 個人情報/認証情報/著作権チェック、採用画像と不採用画像
- 最終的に店頭へアップロードしてよい状態か、残りの必要事項を製品ごとに回答

何も撮影していない場合は「準備だけ完了」と記録する。コード担当のPCで撮影する工程まで実施して初めて「取得完了」とする。

## ScheduledApiRunner

- Store ID: 9PND0HG61XD6
- 最新Draft PR: https://github.com/shihuiarenjinba-png/scheduled-api-runner/pull/6
- branch: `codex/store-draft-validation-20261019`

## Scheduled API Runner の撮影

撮影元は、検証署名したMSIXをWindowsへインストールし、スタートメニューから起動したアプリに限定する。単体EXEや未インストールの展開物はStore画像の撮影元にしない。

操作：①日次GET設定（保存先・JSON抽出項目・日付）→②API項目画面の通信しない設定プレビュー（左：API URL/抽出パス、右：設定内容。取得値ではない）→③Dry Runと実行承認→④所有者が許可したHTTPSテスト環境で別途実GETを行った場合のみCSV更新履歴と結果→⑤Windows日次タスク登録画面。

API項目画面の右側を「取得結果」「通信成功」「取得保証」と説明しない。URLを入力しただけで取得可能と誤認させない。外部通信を伴う撮影は、所有者が利用を許可したテストAPIに限定し、通信日時・応答・生成CSVを別の実行証拠として記録する。

入力・期待値の例（API項目画面のプレビュー自体は通信しない）:
- 旧CSV: `date,sales,orders\n2026-10-17,112000,37\n2026-10-18,126500,42`
- HTTPSテストAPI応答: `{"data":{"date":"2026-10-19","sales":141800,"orders":48}}`
- GUI抽出: `sales = data.sales` / `orders = data.orders`、日付: `data.date`
- 期待される追記: `2026-10-19,141800,48`
上記「期待値」は説明用であり、実行結果は実際の保存済みCSVから確認する。

Store画像: `01_home.png`, `02_api_settings_preview.png`, `03_dry_run.png`, `04_result.png`, `05_schedule.png`。`02_api_settings_preview.png`は通信しない設定確認画面として説明する。`04_result.png`は許可済みテストAPIの実処理が成功した場合だけ採用する。実通信を実施できない場合は、結果画像をStore候補から外し、設定保存や監査ログなど実際に確認できた別画面へ差し替える。出力CSVをExcelで開いて新しい行が存在する画像は `evidence/` に保存。

生のAPIキーやAuthorization値を画像・ログ・GitHubに含めない。既存.xlsxブックの直接編集は販売機能ではないため宣伝しない。Windowsタスク/実サービスを検証していない画面に実行PASSと書かない。

画像説明例:
- JA「必要なAPI項目と取得時刻を画面で設定」
- JA「API URLとJSON項目を通信せずにプレビュー」
- JA「試運転と明示的な実行承認で誤操作を防止」
- JA「既存CSVに日付付きデータを追記」
- EN "Preview an API URL and JSON field paths without sending a request" / "Append dated values without replacing historical CSV rows".
