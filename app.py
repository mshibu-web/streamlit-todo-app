"""Todoリスト Webアプリ（画面）。

起動方法: streamlit run app.py
"""

import logging

import streamlit as st

from todo_repository import (
    Todo,
    TodoError,
    TodoNotFoundError,
    TodoRepository,
    is_rate_limit_error,
    open_worksheet,
    today_jst,
)
from validators import CONTENT_MAX_LENGTH, MAX_TODO_COUNT, TITLE_MAX_LENGTH, validate_todo

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Todoリスト", page_icon="📝")


# ---------- データの準備 ----------


def secrets_ready() -> bool:
    """必要な設定（Secrets）がそろっているか。"""
    try:
        return "gcp_service_account" in st.secrets and "id" in st.secrets.get("spreadsheet", {})
    except Exception:  # secrets.toml が無い場合など
        return False


@st.cache_resource
def get_repository() -> TodoRepository:
    settings = st.secrets["spreadsheet"]
    worksheet = open_worksheet(
        st.secrets["gcp_service_account"],
        settings["id"],
        settings.get("worksheet", "todos"),
    )
    return TodoRepository(worksheet)


@st.cache_data(ttl=30)
def load_todos() -> tuple[list[Todo], int]:
    """一覧を取得する。API の呼び出し回数を減らすため30秒間キャッシュする。"""
    return get_repository().list_todos()


def error_message(exc: Exception, action: str = "保存") -> str:
    """エラーを利用者向けのメッセージに変換する（内部情報は画面に出さない）。

    詳しい原因はログ（Streamlit Community Cloud の Manage app > Logs）にだけ出力する。
    """
    logger.error("スプレッドシートの%sに失敗しました", action, exc_info=exc)
    if isinstance(exc, TodoError):
        return str(exc)
    if is_rate_limit_error(exc):
        return "アクセスが集中しています。しばらく待ってから再度お試しください"
    return f"データの{action}に失敗しました。時間をおいて再度お試しください"


# ---------- 画面に出すメッセージ ----------


def set_message(area: str, kind: str, texts: list[str]) -> None:
    st.session_state["message"] = {"area": area, "kind": kind, "texts": texts}


def show_message(area: str) -> None:
    message = st.session_state.get("message")
    if not message or message["area"] != area:
        return
    show = st.success if message["kind"] == "success" else st.error
    for text in message["texts"]:
        show(text)
    st.session_state["message"] = None


# ---------- ボタンを押したときの処理 ----------


def handle_add() -> None:
    title = st.session_state["new_title"]
    content = st.session_state["new_content"]
    due_date = st.session_state["new_due"]

    errors = validate_todo(title, content, due_date)
    if errors:
        set_message("new", "error", errors)
        return  # 入力値は消さずに残す

    try:
        get_repository().add_todo(title, content, due_date)
    except Exception as exc:
        set_message("new", "error", [error_message(exc)])
        return

    load_todos.clear()
    st.session_state["new_title"] = ""
    st.session_state["new_content"] = ""
    st.session_state["new_due"] = today_jst()
    set_message("new", "success", ["登録しました"])


def start_edit(todo: Todo) -> None:
    st.session_state["editing_id"] = todo.id
    st.session_state["edit_title"] = todo.title
    st.session_state["edit_content"] = todo.content
    st.session_state["edit_due"] = todo.due_date


def handle_save() -> None:
    todo_id = st.session_state.get("editing_id")
    title = st.session_state["edit_title"]
    content = st.session_state["edit_content"]
    due_date = st.session_state["edit_due"]

    errors = validate_todo(title, content, due_date)
    if errors:
        set_message("edit", "error", errors)
        return

    try:
        get_repository().update_todo(todo_id, title, content, due_date)
    except TodoNotFoundError as exc:
        st.session_state["editing_id"] = None
        load_todos.clear()
        set_message("list", "error", [str(exc)])
        return
    except Exception as exc:
        set_message("edit", "error", [error_message(exc)])
        return

    load_todos.clear()
    st.session_state["editing_id"] = None
    set_message("list", "success", ["更新しました"])


def handle_cancel() -> None:
    st.session_state["editing_id"] = None


# ---------- 画面の部品 ----------


def render_new_form() -> None:
    st.subheader("新規登録")
    show_message("new")
    with st.form("new_todo"):
        st.text_input("タイトル（必須）", key="new_title", max_chars=TITLE_MAX_LENGTH)
        st.text_area("内容（任意）", key="new_content", max_chars=CONTENT_MAX_LENGTH)
        st.date_input("期日（必須）", key="new_due", format="YYYY/MM/DD")
        st.form_submit_button("登録する", on_click=handle_add, key="add_submit", type="primary")


def render_edit_form(todo: Todo) -> None:
    show_message("edit")
    with st.form(f"edit_todo_{todo.id}"):
        st.text_input("タイトル（必須）", key="edit_title", max_chars=TITLE_MAX_LENGTH)
        st.text_area("内容（任意）", key="edit_content", max_chars=CONTENT_MAX_LENGTH)
        st.date_input("期日（必須）", key="edit_due", format="YYYY/MM/DD")
        save_col, cancel_col = st.columns(2)
        with save_col:
            st.form_submit_button("保存する", on_click=handle_save, key="save_edit", type="primary")
        with cancel_col:
            st.form_submit_button("キャンセル", on_click=handle_cancel, key="cancel_edit")


def render_list(todos: list[Todo]) -> None:
    st.subheader(f"Todo一覧（{len(todos)} / {MAX_TODO_COUNT}件・期日が近い順）")
    show_message("list")

    if not todos:
        st.write("Todoはまだありません")
        return

    editing_id = st.session_state.get("editing_id")
    for todo in todos:
        is_editing = todo.id == editing_id
        label = f"{todo.due_date:%Y/%m/%d}　{todo.title}"
        with st.expander(label, expanded=is_editing):
            if is_editing:
                render_edit_form(todo)
                continue
            if todo.content:
                st.text(todo.content)
            else:
                st.caption("（内容なし）")
            st.button("編集する", key=f"edit_{todo.id}", on_click=start_edit, args=(todo,))


# ---------- メイン ----------


def main() -> None:
    st.session_state.setdefault("new_due", today_jst())
    st.session_state.setdefault("editing_id", None)

    st.title("📝 Todoリスト")
    st.info("これはテスト用のアプリです。誰でも閲覧・編集できるため、個人情報や機密情報は入力しないでください。")

    if not secrets_ready():
        st.error("設定が不足しています。管理者に連絡してください")
        st.stop()

    render_new_form()
    st.divider()

    try:
        todos, skipped = load_todos()
    except Exception as exc:
        st.error(error_message(exc, action="読み込み"))
        st.stop()

    if skipped:
        st.warning(f"形式が正しくない行が{skipped}件あったため、表示していません")

    render_list(todos)


main()
