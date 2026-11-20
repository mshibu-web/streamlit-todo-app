"""開発用プレビュー（ローカルで画面を確認するためだけのもの）。

起動方法:
    streamlit run dev_preview.py --server.address localhost --server.port 8502

このプレビューでは、次の3つを「偽物」に差し替えてから app.py を動かす。
  1. ログイン   … 架空の本人（preview@example.com）がログインしている扱いにする
  2. 設定       … 本物の secrets.toml は読まず、一時フォルダに作ったダミーの設定だけを使う
  3. データ     … Googleスプレッドシートには接続せず、メモリ上の見本データを使う（停止すると消える）

安全のための設計
  - app.py には「ログインを飛ばす」仕組みを一切入れていない。飛ばせるのはこのファイルを
    直接起動したときだけ。Streamlit Cloud（本番）は app.py を起動するため、本番では必ずログインが必要
  - このファイルは本物の鍵・シートIDを読まず、シートへの接続も偽物に差し替えるため、
    たとえ誤って起動しても本番・開発用のデータには触れない
  - localhost 以外から開かれた場合は表示しない
"""

import runpy
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.user_info
from streamlit import config

import todo_repository
from todo_repository import HEADERS

APP_PATH = Path(__file__).resolve().parent / "app.py"
PREVIEW_EMAIL = "preview@example.com"
PREVIEW_USER = {"is_logged_in": True, "email": PREVIEW_EMAIL, "email_verified": True}

# ダミーの設定（本物の値は1つも含まない）
DUMMY_SECRETS = f"""
[spreadsheet]
id = "preview-dummy"
worksheet = "todos"

[gcp_service_account]
type = "service_account"

[auth]
redirect_uri = "http://localhost:8502/oauth2callback"
cookie_secret = "preview-only-dummy"
client_id = "preview-only-dummy"
client_secret = "preview-only-dummy"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[access]
allowed_emails = ["{PREVIEW_EMAIL}"]
"""

SAMPLE_ROWS = [
    ("s1", "資料作成", "週次会議用のスライドを作る", 0, "", "高"),
    ("s2", "買い物", "牛乳、卵、パン", -2, "done", "低"),
    ("s3", "Streamlitの復習", "", 10, "", "中"),
    ("s4", "期限切れの例", "過去日も表示できる", -10, "", "高"),
    ("s5", "歯医者", "", 0, "", "中"),
    ("s6", "請求書の確認", "", 3, "", "低"),
]


class MemoryWorksheet:
    """メモリ上の偽物のシート（gspread の Worksheet と同じ使い方ができる最小限のもの）。"""

    def __init__(self, rows):
        self.rows = [list(r) for r in rows]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_row(self, values, **kwargs):
        self.rows.append([str(v) for v in values])

    def update(self, values=None, range_name=None, **kwargs):
        start, end = range_name.split(":")
        row_number = int("".join(c for c in start if c.isdigit()))
        first_col = ord(start[0]) - ord("A")
        while len(self.rows) < row_number:
            self.rows.append([])
        row = self.rows[row_number - 1]
        row.extend([""] * (first_col + len(values[0]) - len(row)))
        for offset, value in enumerate(values[0]):
            row[first_col + offset] = str(value)

    def acell(self, label):
        col, row_number = ord(label[0]) - ord("A"), int(label[1:])
        cells = self.rows[row_number - 1] if row_number <= len(self.rows) else []
        return type("Cell", (), {"value": cells[col] if col < len(cells) else ""})()

    def delete_rows(self, start_index, end_index=None):
        del self.rows[start_index - 1 : (end_index or start_index)]


def sample_sheet() -> MemoryWorksheet:
    from datetime import timedelta

    today = todo_repository.today_jst()
    now = todo_repository.now_jst_text()
    rows = [list(HEADERS)]
    for todo_id, title, content, days, done, priority in SAMPLE_ROWS:
        due = (today + timedelta(days=days)).strftime(todo_repository.DATE_FORMAT)
        rows.append([todo_id, title, content, due, now, now, now if done else "", priority])
    return MemoryWorksheet(rows)


def is_localhost() -> bool:
    """ブラウザから localhost で開かれているか。

    ブラウザからの通信には必ず Host ヘッダーがある。ヘッダーが1つも無いのは
    ブラウザを使わない自動テスト（AppTest）のときだけなので、その場合は許可する。
    """
    headers = st.context.headers
    if len(headers) == 0:
        return True
    host = (headers.get("Host") or "").rsplit(":", 1)[0]
    return host in ("localhost", "127.0.0.1", "[::1]")


def setup_preview() -> None:
    """偽物への差し替え（サーバーを起動して最初の1回だけ行う）。"""
    if getattr(todo_repository, "_dev_preview_ready", False):
        return
    secrets_file = Path(tempfile.mkdtemp(prefix="todo-preview-")) / "secrets.toml"
    secrets_file.write_text(DUMMY_SECRETS, encoding="utf-8")
    config.set_option("secrets.files", [str(secrets_file)])  # 本物の secrets.toml を読まない
    st.secrets._reset()

    sheet = sample_sheet()
    todo_repository.open_worksheet = lambda *args, **kwargs: sheet  # シートに接続しない
    streamlit.user_info._get_user_info = lambda: dict(PREVIEW_USER)  # ログイン済みの扱い
    todo_repository._dev_preview_ready = True


if not is_localhost():
    st.error("このプレビューは開発用です。ローカル（localhost）でだけ使えます")
    st.stop()

setup_preview()
st.info("開発用プレビュー：ログインを省略し、見本データで表示しています（Googleには接続していません）", icon="🧪")
runpy.run_path(str(APP_PATH), run_name="__main__")
