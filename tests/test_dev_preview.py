"""開発用プレビュー（dev_preview.py）のテスト。

- プレビューではログインなしで見本データのToDo画面が見られること
- プレビューは本物の設定・本物のシートを使わないこと
- 本番の入口（app.py）にはログインを飛ばす仕組みが無いこと
"""

from pathlib import Path

import pytest
import streamlit as st
import streamlit.user_info
from streamlit.testing.v1 import AppTest

import todo_repository

ROOT = Path(__file__).resolve().parent.parent
PREVIEW_PATH = str(ROOT / "dev_preview.py")
APP_PATH = str(ROOT / "app.py")


@pytest.fixture
def restore_after_preview(monkeypatch):
    """プレビューが行う差し替えを、テストの後に必ず元に戻す（ほかのテストに影響させない）。"""
    real_open_calls = []

    def must_not_connect(*args, **kwargs):
        real_open_calls.append(1)
        raise AssertionError("本物のシートに接続しようとした")

    monkeypatch.setattr(todo_repository, "open_worksheet", must_not_connect)
    monkeypatch.setattr(streamlit.user_info, "_get_user_info", streamlit.user_info._get_user_info)
    monkeypatch.setattr(todo_repository, "_dev_preview_ready", False, raising=False)
    st.cache_resource.clear()
    st.cache_data.clear()
    yield real_open_calls
    st.cache_resource.clear()
    st.cache_data.clear()


def all_markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_プレビューはログインなしで見本データのToDo画面を表示する(restore_after_preview):
    at = AppTest.from_file(PREVIEW_PATH, default_timeout=30).run()
    assert not at.exception
    assert not at.error
    assert "開発用プレビュー" in at.info[0].value
    assert "資料作成" in all_markdown(at)
    assert [b for b in at.button if b.key == "fab_add"]  # ＋ボタンがある
    assert "Googleでログイン" not in [b.label for b in at.button]
    assert "preview@example.com" in [m.value for m in at.sidebar.markdown]
    assert restore_after_preview == []  # 本物の open_worksheet は1回も呼ばれない


def test_プレビューで登録しても見本データにだけ保存される(restore_after_preview):
    at = AppTest.from_file(PREVIEW_PATH, default_timeout=30).run()
    at.button(key="fab_add").click().run()
    at.text_input(key="new_title").input("プレビューで追加")
    at.button(key="add_submit").click().run()
    assert not at.exception
    assert "プレビューで追加" in all_markdown(at)
    assert restore_after_preview == []


def test_プレビューは本物の設定ファイルを読まない():
    source = Path(PREVIEW_PATH).read_text(encoding="utf-8")
    assert "/.secrets/" not in source and "\\.secrets\\" not in source  # 本物の置き場所を参照しない
    assert 'config.set_option("secrets.files"' in source


def test_本番の入口app_pyにはログインを飛ばす仕組みが無い():
    source = Path(APP_PATH).read_text(encoding="utf-8")
    for word in ("dev_preview", "PREVIEW", "_get_user_info", "skip_login", "os.environ", "getenv"):
        assert word not in source, word


def test_プレビューの差し替えを戻した後のapp_pyはログインが必要(restore_after_preview, monkeypatch):
    AppTest.from_file(PREVIEW_PATH, default_timeout=30).run()
    monkeypatch.undo()  # プレビューの差し替えを元に戻す（本番と同じ状態）
    check_app_requires_login(monkeypatch)


def test_app_pyはログインしていなければToDoを表示しない(monkeypatch):
    check_app_requires_login(monkeypatch)


def check_app_requires_login(monkeypatch):
    calls = []
    monkeypatch.setattr(todo_repository, "open_worksheet", lambda *a, **k: calls.append(1))
    st.cache_resource.clear()
    st.cache_data.clear()
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.secrets["spreadsheet"] = {"id": "dummy", "worksheet": "todos"}
    at.secrets["gcp_service_account"] = {"type": "service_account"}
    at.secrets["auth"] = {
        "redirect_uri": "http://localhost:8501/oauth2callback",
        "cookie_secret": "x",
        "client_id": "x",
        "client_secret": "x",
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
    }
    at.secrets["access"] = {"allowed_emails": ["preview@example.com"]}
    at.user = {"is_logged_in": False}
    at.run()
    assert [b.label for b in at.button] == ["Googleでログイン"]
    assert calls == []
