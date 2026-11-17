"""すべてのテストに共通の設定。

ローカルの .streamlit/config.toml は本物の secrets.toml を指しているため、
テスト中は存在しない空の場所に差し替え、本物の認証情報を絶対に読まないようにする。
"""

import pytest
import streamlit as st
from streamlit import config


@pytest.fixture(autouse=True)
def isolate_real_secrets(tmp_path):
    original = config.get_option("secrets.files")
    config.set_option("secrets.files", [str(tmp_path / "no_secrets.toml")])
    st.secrets._reset()
    yield
    config.set_option("secrets.files", original)
    st.secrets._reset()
