# 📝 Todoリスト Webアプリ

Python（Streamlit）で作ったシンプルなTodoリストです。データは Google スプレッドシートに保存します。
詳しい仕様は [requirements.md](requirements.md) を参照してください。

> ⚠️ テスト用のアプリです。誰でも閲覧・編集できるため、個人情報や機密情報は入力しないでください。

## できること
- Todoの新規登録（タイトル・内容・期日）
- 登録済みTodoの編集
- Todoの一覧表示（期日が近い順）

## ファイル構成
| ファイル | 役割 |
|---|---|
| `app.py` | 画面（入力・表示・ボタンの処理） |
| `todo_repository.py` | スプレッドシートとの読み書き |
| `validators.py` | 入力チェック |
| `tests/` | 自動テスト（本物のスプレッドシートには接続しない） |
| `requirements.txt` | 公開環境で使うライブラリ |
| `requirements-dev.txt` | 開発・テスト用のライブラリ |
| `.streamlit/secrets.toml.example` | 設定ファイルの見本（値はダミー） |

---

## 1. ローカル環境の準備（済）

```powershell
conda create -n todo-app python=3.12 -y
conda activate todo-app
pip install -r requirements-dev.txt
```

## 2. 自動テストの実行

```powershell
conda activate todo-app
python -m pytest
```

## 3. Google スプレッドシートの準備（手作業）

> 開発用と公開用の **2つ** のスプレッドシートを用意します（要件定義書 Q7）。

### 3-1. Google Cloud でサービスアカウントを作る
1. https://console.cloud.google.com/ にログインし、新しいプロジェクトを作成（例：`todo-app`）
2. 「APIとサービス」→「ライブラリ」で **Google Sheets API** を検索して「有効にする」
   （Google Drive API は有効にしなくてよい）
3. 「IAMと管理」→「サービスアカウント」→「サービスアカウントを作成」
   - 名前：例 `todo-app`
   - 「このサービス アカウントにプロジェクトへのアクセスを許可」の**ロールは何も付けずに**「続行」→「完了」
4. 作成したサービスアカウントを開き、「キー」→「鍵を追加」→「新しい鍵を作成」→「JSON」
   - JSONファイルがダウンロードされます。**このファイルは秘密情報です。** プロジェクトのフォルダには置かず、GitHubにも上げないでください
5. サービスアカウントのメールアドレス（`〜@〜.iam.gserviceaccount.com`）を控えておく

### 3-2. スプレッドシートを作る（開発用・公開用それぞれ）
1. Google スプレッドシートで新規作成（例：`todo_app_dev`、`todo_app_public`）
2. 下のタブ名を `シート1` から **`todos`** に変更
3. 1行目は空のままでOK（初回の登録時に、アプリが見出し行を自動で書き込みます）
4. 右上の「共有」で、控えておいた**サービスアカウントのメールアドレスを「編集者」として追加**
   - 「リンクを知っている全員」への共有は**しない**でください
5. URL の `https://docs.google.com/spreadsheets/d/【ここ】/edit` 部分がスプレッドシートIDです

### 3-3. ローカルの設定ファイル（秘密鍵は OneDrive の外に置く）
このフォルダは OneDrive の同期対象のため、秘密鍵を含む `secrets.toml` は **OneDrive の外** に置きます。

| ファイル | 場所 | 内容 | Git |
|---|---|---|---|
| `secrets.toml` | `C:/Users/<ユーザー名>/.secrets/todo-app/secrets.toml` | サービスアカウント鍵・**開発用**シートID | 対象外（プロジェクトの外） |
| `config.toml` | `.streamlit/config.toml` | 上の `secrets.toml` の**場所だけ**を指定（秘密情報なし） | 対象外（`.gitignore`） |

- `secrets.toml` の書き方は `.streamlit/secrets.toml.example` を参照
- `config.toml` の例：
  ```toml
  [secrets]
  files = ["C:/Users/<ユーザー名>/.secrets/todo-app/secrets.toml"]
  ```
- 自動テスト（pytest）は `tests/conftest.py` により本物の Secrets を読まないようにしています

## 4. ローカルで起動

```powershell
conda activate todo-app
streamlit run app.py
```
ブラウザで http://localhost:8501 が開きます。

### 開発用プレビュー（ログインなしで画面だけ確認する）

```powershell
conda activate todo-app
streamlit run dev_preview.py --server.address localhost --server.port 8502
```
ブラウザで http://localhost:8502 を開きます。

- ログインを省略し、メモリ上の見本データで表示します。Google には接続しません（停止するとデータは消えます）
- 本物の `secrets.toml` は読まず、ダミーの設定だけを使います
- localhost 以外から開いた場合は表示しません
- ログインを省略できるのは `dev_preview.py` を起動したときだけです。`app.py`（本番の入口）には省略する仕組みがなく、必ずログインが必要です

## LINE リマインド通知（要件定義書 15章）

毎朝 7:00（日本時間）ごろ、今日が期限の未完了ToDoと期限切れの未完了ToDoを、本人の LINE に1通送ります（0件の日は送りません）。

| ファイル | 役割 |
|---|---|
| `notify.py` | 通知の処理（シートは読むだけ。送り先は本人1人だけ） |
| `.github/workflows/notify.yml` | GitHub Actions の定期実行（UTC 22:00）と手動実行 |
| `requirements-notify.txt` | 通知に必要なライブラリ |

- 秘密の値はすべて GitHub の Secrets に置きます（`NOTIFY_SERVICE_ACCOUNT_JSON`、`SPREADSHEET_ID`、`LINE_CHANNEL_ID`、`LINE_CHANNEL_SECRET`、`LINE_USER_ID`、`APP_URL`）
- 手動実行（Actions → LINE ToDo reminder → Run workflow）は、「送信する」にチェックしない限り件数の確認だけです
- 実行ログには件数だけが出ます（タイトルや秘密の値は出ません）
- 公開リポジトリでは、60日間更新がないと定期実行が止まります。GitHub からメールが届いたら、Actions の画面で再開してください

## 5. 公開（Streamlit Community Cloud）

要件定義書 12.2 の手順で行います。Secrets には **公開用** のスプレッドシートIDを設定します。
非公開リポジトリからデプロイしたアプリは最初「非公開」になるため、
App settings → Sharing で「This app is public and searchable」に切り替えてください。

## セキュリティ上の注意
- `.streamlit/secrets.toml` と JSON 鍵は `.gitignore` で除外しています。GitHub に上げないでください
- 鍵が漏れた場合は、Google Cloud でその鍵を削除し、新しい鍵を作って Secrets を更新してください
