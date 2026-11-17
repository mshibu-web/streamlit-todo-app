"""画面の動作テスト（Streamlit の AppTest を使用。Google には接続しない）"""

from datetime import date
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import todo_repository
from tests.fakes import FakeWorksheet

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def sheet(monkeypatch):
    fake = FakeWorksheet()
    monkeypatch.setattr(todo_repository, "open_worksheet", lambda *args, **kwargs: fake)
    st.cache_resource.clear()
    st.cache_data.clear()
    return fake


def make_app():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.secrets["spreadsheet"] = {"id": "dummy-id", "worksheet": "todos"}
    at.secrets["gcp_service_account"] = {"type": "service_account"}
    return at.run()


def add(at, title, content, due):
    at.text_input(key="new_title").input(title)
    at.text_area(key="new_content").input(content)
    at.date_input(key="new_due").set_value(due)
    return at.button(key="add_submit").click().run()


def texts(elements):
    return [e.value for e in elements]


def test_初期表示(sheet):
    at = make_app()
    assert not at.exception
    assert "個人情報" in at.info[0].value
    assert "Todoはまだありません" in texts(at.markdown)


def test_M1_登録すると一覧とシートに追加され入力欄が空になる(sheet):
    at = add(make_app(), "資料作成", "会議用", date(2026, 11, 20))
    assert not at.exception
    assert "登録しました" in texts(at.success)
    assert sheet.rows[1][1:4] == ["資料作成", "会議用", "2026-11-20"]
    assert at.text_input(key="new_title").value == ""
    assert at.expander[0].label == "2026/11/20　資料作成"


def test_M2_タイトル空欄なら登録されず入力値は残る(sheet):
    at = add(make_app(), "", "メモだけ", date(2026, 11, 20))
    assert "タイトルを入力してください" in texts(at.error)
    assert len(sheet.rows) == 1
    assert at.text_area(key="new_content").value == "メモだけ"


def test_一覧は期日の昇順(sheet):
    at = make_app()
    add(at, "遅い", "", date(2026, 12, 1))
    add(at, "早い", "", date(2026, 1, 1))
    assert [e.label for e in at.expander] == ["2026/01/01　早い", "2026/12/01　遅い"]


def test_M3_編集して保存するとシートが更新される(sheet):
    at = add(make_app(), "資料作成", "会議用", date(2026, 11, 20))
    todo_id = sheet.rows[1][0]

    at.button(key=f"edit_{todo_id}").click().run()
    assert at.text_input(key="edit_title").value == "資料作成"  # 現在値が入っている

    at.text_input(key="edit_title").input("資料作成（改）")
    at.date_input(key="edit_due").set_value(date(2026, 11, 25))
    at.button(key="save_edit").click().run()

    assert not at.exception
    assert "更新しました" in texts(at.success)
    assert sheet.rows[1][0] == todo_id
    assert sheet.rows[1][1:4] == ["資料作成（改）", "会議用", "2026-11-25"]
    assert at.expander[0].label == "2026/11/25　資料作成（改）"


def test_M4_編集をキャンセルすると何も変わらない(sheet):
    at = add(make_app(), "資料作成", "会議用", date(2026, 11, 20))
    before = [list(r) for r in sheet.rows]
    todo_id = sheet.rows[1][0]

    at.button(key=f"edit_{todo_id}").click().run()
    at.text_input(key="edit_title").input("変更したけどやめる")
    at.button(key="cancel_edit").click().run()

    assert sheet.rows == before
    assert at.expander[0].label == "2026/11/20　資料作成"


def test_編集でタイトルを空にするとエラーで保存されない(sheet):
    at = add(make_app(), "資料作成", "", date(2026, 11, 20))
    todo_id = sheet.rows[1][0]
    at.button(key=f"edit_{todo_id}").click().run()
    at.text_input(key="edit_title").input("")
    at.button(key="save_edit").click().run()
    assert "タイトルを入力してください" in texts(at.error)
    assert sheet.rows[1][1] == "資料作成"


def test_M7_件数上限ならエラー表示で登録されない(sheet):
    sheet.rows += [[str(i), f"t{i}", "", "2026-01-01", "", ""] for i in range(200)]
    at = add(make_app(), "201件目", "", date(2026, 1, 1))
    assert "登録件数の上限（200件）に達しているため、登録できません" in texts(at.error)
    assert len(sheet.rows) == 201


def test_読み込みに失敗しても内部情報は表示しない(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret-detail-should-not-be-shown")

    monkeypatch.setattr(todo_repository, "open_worksheet", broken)
    st.cache_resource.clear()
    st.cache_data.clear()
    at = make_app()
    assert texts(at.error) == ["データの読み込みに失敗しました。時間をおいて再度お試しください"]
    assert not at.exception


def test_設定が無ければ設定不足と表示(sheet):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert "設定が不足しています。管理者に連絡してください" in texts(at.error)
