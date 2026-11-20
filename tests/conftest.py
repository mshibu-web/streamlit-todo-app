"""すべてのテストに共通の設定。

自動テストが本物の Google スプレッドシートに触れないよう、二重に守る。

1. 本物の Secrets を読まない
   ローカルの .streamlit/config.toml は本物の secrets.toml を指しているため、
   テスト中は存在しない空の場所に差し替える。
2. 本物のシートに接続できなくする
   シートを開く入口（todo_repository.open_worksheet と gspread の認証関数）を、
   呼ばれたらテストを失敗させる関数に差し替える。各テストは偽物のシート（tests/fakes.py）を
   自分で差し込んで使う。差し込み忘れがあっても、本物には接続せずテストが失敗する。
"""

import gspread
import pytest
import streamlit as st
from streamlit import config

import todo_repository


@pytest.fixture(autouse=True)
def isolate_real_secrets(tmp_path):
    original = config.get_option("secrets.files")
    config.set_option("secrets.files", [str(tmp_path / "no_secrets.toml")])
    st.secrets._reset()
    yield
    config.set_option("secrets.files", original)
    st.secrets._reset()


class RealSheetAccessError(AssertionError):
    """自動テストが本物のスプレッドシートに接続しようとした。"""


def _forbid_real_sheet(*args, **kwargs):
    raise RealSheetAccessError("自動テストから本物のスプレッドシートに接続しようとしました（偽物のシートを使ってください）")


@pytest.fixture(autouse=True)
def forbid_real_spreadsheet(monkeypatch):
    monkeypatch.setattr(todo_repository, "open_worksheet", _forbid_real_sheet)
    for name in ("service_account", "service_account_from_dict", "authorize", "oauth", "oauth_from_dict"):
        if hasattr(gspread, name):
            monkeypatch.setattr(gspread, name, _forbid_real_sheet)
    st.cache_resource.clear()  # 前のテストで作られた接続（偽物を含む）を持ち越さない
    st.cache_data.clear()
