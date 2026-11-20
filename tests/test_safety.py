"""自動テストが本物のスプレッドシートに触れない仕組み（tests/conftest.py）が働いていることのテスト。"""

import gspread
import pytest
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

import todo_repository
from tests.conftest import RealSheetAccessError


def test_テスト中はシートを開く入口が使えない():
    with pytest.raises(RealSheetAccessError):
        todo_repository.open_worksheet({"type": "service_account"}, "any-id", "todos")


def test_テスト中はgspreadの認証も使えない():
    with pytest.raises(RealSheetAccessError):
        gspread.service_account_from_dict({"type": "service_account"})


def test_テスト中は本物のSecretsを読まない():
    # 設定ファイルの場所が空の一時フォルダに差し替えられているため、Secrets そのものが見つからない
    with pytest.raises(StreamlitSecretNotFoundError):
        st.secrets["gcp_service_account"]
