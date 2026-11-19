"""ToDoリスト Webアプリ（画面）。カレンダーを中心にした画面（要件定義書 14章）。

起動方法: streamlit run app.py

画面の流れ
    ダッシュボード → カレンダー（または一覧） → 選んだ日のToDo
    左下の＋ボタン → 右から開く登録パネル
    「詳細」ボタン → 右から開く詳細パネル（確認・編集・完了・削除）
"""

import logging
from datetime import date

import streamlit as st

import todo_repository
from todo_logic import (
    FILTER_ALL,
    FILTER_DONE,
    FILTER_OPEN,
    WEEKDAY_LABELS,
    dashboard_counts,
    due_label,
    filter_todos,
    japanese_weekday,
    month_weeks,
    shift_month,
    todos_by_date,
)
from todo_repository import SORT_BY_DUE, SORT_BY_PRIORITY, Todo, TodoError, TodoNotFoundError, sort_todos
from ui_style import CSS, NO_TRANSLATE_SCRIPT, card_text_html, chip_html, more_chip_html, priority_code
from validators import CONTENT_MAX_LENGTH, DEFAULT_PRIORITY, PRIORITIES, TITLE_MAX_LENGTH, validate_todo

logger = logging.getLogger(__name__)

st.set_page_config(page_title="ToDoリスト", page_icon="📝", layout="wide")

VIEW_CALENDAR = "📅 カレンダー"
VIEW_LIST = "📋 一覧"
SORT_OPTIONS = {"期日順": SORT_BY_DUE, "優先度順": SORT_BY_PRIORITY}
FILTER_OPTIONS = {"すべて": FILTER_ALL, "未完了": FILTER_OPEN, "完了済み": FILTER_DONE}
CHIPS_PER_DAY = 3  # カレンダーの1マスに表示するラベルの最大数


def today() -> date:
    """日本時間の今日（テストで日付を固定できるよう、毎回モジュールから呼ぶ）。"""
    return todo_repository.today_jst()


# ---------- データの準備 ----------


def secrets_ready() -> bool:
    """必要な設定（Secrets）がそろっているか。"""
    try:
        return "gcp_service_account" in st.secrets and "id" in st.secrets.get("spreadsheet", {})
    except Exception:  # secrets.toml が無い場合など
        return False


@st.cache_resource
def get_repository() -> todo_repository.TodoRepository:
    settings = st.secrets["spreadsheet"]
    worksheet = todo_repository.open_worksheet(
        st.secrets["gcp_service_account"],
        settings["id"],
        settings.get("worksheet", "todos"),
    )
    return todo_repository.TodoRepository(worksheet)


@st.cache_data(ttl=30)
def load_todos() -> tuple[list[Todo], int]:
    """一覧を取得する。API の呼び出し回数を減らすため30秒間キャッシュする。"""
    return get_repository().list_todos()


def find_todo(todo_id: str) -> Todo | None:
    todos, _ = load_todos()
    return next((t for t in todos if t.id == todo_id), None)


def error_message(exc: Exception, action: str = "保存") -> str:
    """エラーを利用者向けのメッセージに変換する（内部情報は画面に出さない）。"""
    logger.error("スプレッドシートの%sに失敗しました", action, exc_info=exc)
    if isinstance(exc, TodoError):
        return str(exc)
    if todo_repository.is_rate_limit_error(exc):
        return "アクセスが集中しています。しばらく待ってから再度お試しください"
    return f"データの{action}に失敗しました。時間をおいて再度お試しください"


# ---------- メッセージ（成功は右下の小さな通知、エラーは赤い枠） ----------


def set_message(kind: str, text: str) -> None:
    st.session_state["message"] = {"kind": kind, "text": text}


def show_message() -> None:
    message = st.session_state.get("message")
    if not message:
        return
    if message["kind"] == "success":
        st.toast(message["text"], icon="✅")
    else:
        st.error(message["text"])
    st.session_state["message"] = None


# ---------- パネル（右から開く画面）を開く・閉じる ----------


def open_add_panel(due: date) -> None:
    """登録パネルを開く。期限の初期値は due（カレンダーで選んだ日など）。"""
    st.session_state["panel"] = {"mode": "add"}
    st.session_state["panel_errors"] = []
    st.session_state["new_title"] = ""
    st.session_state["new_content"] = ""
    st.session_state["new_due"] = due
    st.session_state["new_priority"] = DEFAULT_PRIORITY


def open_detail_panel(todo_id: str) -> None:
    st.session_state["panel"] = {"mode": "detail", "id": todo_id, "step": "view"}
    st.session_state["panel_errors"] = []


def close_panel() -> None:
    st.session_state["panel"] = None
    st.session_state["panel_errors"] = []


def set_panel_step(step: str) -> None:
    """詳細パネルの中の画面を切り替える（view=確認 / edit=編集 / delete=削除の確認）。"""
    st.session_state["panel"] = {**st.session_state["panel"], "step": step}
    st.session_state["panel_errors"] = []


def start_edit(todo: Todo) -> None:
    set_panel_step("edit")
    st.session_state["edit_title"] = todo.title
    st.session_state["edit_content"] = todo.content
    st.session_state["edit_due"] = todo.due_date
    st.session_state["edit_priority"] = todo.priority


def show_date(day: date) -> None:
    """カレンダーでその日を選び、その月を表示する。"""
    st.session_state["selected_date"] = day
    st.session_state["cal_month"] = day.replace(day=1)


def move_month(months: int) -> None:
    """表示する月を前後に動かす（-1 で前月、+1 で翌月）。"""
    st.session_state["cal_month"] = shift_month(st.session_state["cal_month"], months)


# ---------- ボタンを押したときの処理（データの変更） ----------


def handle_add() -> None:
    title = st.session_state["new_title"]
    content = st.session_state["new_content"]
    due_date = st.session_state["new_due"]
    priority = st.session_state["new_priority"]

    errors = validate_todo(title, content, due_date, priority)
    if errors:
        st.session_state["panel_errors"] = errors
        return  # パネルは開いたまま。入力値も残す

    try:
        get_repository().add_todo(title, content, due_date, priority)
    except Exception as exc:
        st.session_state["panel_errors"] = [error_message(exc)]
        return

    load_todos.clear()
    close_panel()
    show_date(due_date)  # 登録した日をカレンダーで表示する
    set_message("success", "登録しました")


def handle_save(todo_id: str) -> None:
    title = st.session_state["edit_title"]
    content = st.session_state["edit_content"]
    due_date = st.session_state["edit_due"]
    priority = st.session_state["edit_priority"]

    errors = validate_todo(title, content, due_date, priority)
    if errors:
        st.session_state["panel_errors"] = errors
        return

    try:
        get_repository().update_todo(todo_id, title, content, due_date, priority)
    except TodoNotFoundError as exc:
        load_todos.clear()
        close_panel()
        set_message("error", str(exc))
        return
    except Exception as exc:
        st.session_state["panel_errors"] = [error_message(exc)]
        return

    load_todos.clear()
    set_panel_step("view")
    set_message("success", "更新しました")


def save_completed(todo_id: str, completed: bool) -> None:
    try:
        get_repository().set_completed(todo_id, completed)
        set_message("success", "完了にしました" if completed else "未完了に戻しました")
    except Exception as exc:
        set_message("error", error_message(exc))
    load_todos.clear()  # 成功・失敗どちらでも、シートの最新の状態を表示し直す


def handle_checkbox(todo_id: str) -> None:
    """カードの完了チェックが押されたとき。"""
    save_completed(todo_id, st.session_state[f"done_{todo_id}"])


def handle_delete(todo_id: str) -> None:
    """「削除を確定」が押されたとき。"""
    try:
        get_repository().delete_todo(todo_id)
    except Exception as exc:
        load_todos.clear()
        close_panel()
        set_message("error", error_message(exc, action="削除"))
        return
    load_todos.clear()
    close_panel()
    set_message("success", "削除しました")


def keep_selection(key: str) -> None:
    """切り替えボタンをもう一度押して「選択なし」になったら、元の選択に戻す。"""
    if st.session_state[key] is None:
        st.session_state[key] = st.session_state[f"{key}_last"]
    st.session_state[f"{key}_last"] = st.session_state[key]


# ---------- 画面の部品 ----------


def segmented(label: str, options: list[str], key: str) -> str:
    """横並びの切り替えボタン。必ずどれか1つが選ばれた状態にする。"""
    st.session_state.setdefault(key, options[0])
    st.session_state.setdefault(f"{key}_last", options[0])
    st.segmented_control(
        label, options, key=key, on_change=keep_selection, args=(key,), label_visibility="collapsed"
    )
    return st.session_state[key]


def render_dashboard(todos: list[Todo]) -> None:
    counts = dashboard_counts(todos, today())
    with st.container(key="dashboard"):
        cols = st.columns(4)
        cols[0].metric("📌 今日のToDo", f"{counts['today']}件", help="今日が期限の未完了ToDo")
        cols[1].metric("⏳ 未完了", f"{counts['open']}件")
        cols[2].metric("✅ 完了", f"{counts['done']}件")
        cols[3].metric("🗓️ 今週の残り", f"{counts['this_week']}件", help="今日〜今週の土曜日が期限の未完了ToDo")


def render_card(todo: Todo, show_due_date: bool = True) -> None:
    """ToDo を1枚のカード（横幅いっぱい）で表示する。左に完了チェック、右に「詳細」ボタン。"""
    due_text, overdue = due_label(todo.due_date, today())
    with st.container(border=True, key=f"card-{priority_code(todo)}-{todo.id}"):
        # 横並びの箱。スマートフォンでも縦に崩れないよう、折り返さない（CSS の st-key-row-）
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"row-{todo.id}"):
            done_key = f"done_{todo.id}"
            st.session_state[done_key] = todo.is_completed  # 毎回シートの状態に合わせる
            st.checkbox(
                "完了",
                key=done_key,
                label_visibility="collapsed",
                on_change=handle_checkbox,
                args=(todo.id,),
                help="完了にする / 未完了に戻す",
                width="content",
            )
            st.markdown(card_text_html(todo, due_text, overdue, show_due_date), unsafe_allow_html=True, width="stretch")
            st.button("詳細", key=f"open_{todo.id}", on_click=open_detail_panel, args=(todo.id,), icon=":material/chevron_right:", width="content")


def render_calendar(todos: list[Todo]) -> None:
    month = st.session_state["cal_month"]
    selected = st.session_state["selected_date"]
    grouped = todos_by_date(todos)

    with st.container(key="calendar"):
        # 左右の幅をそろえて、年月がカレンダーの中央に来るようにする： [空き | ◀ | 年月 | ▶ | 今日]
        _, prev_col, title_col, next_col, today_col = st.columns([2, 1, 3, 1, 2], vertical_alignment="center")
        with prev_col.container(horizontal=True, horizontal_alignment="right"):
            st.button("◀", key="cal_prev", on_click=move_month, args=(-1,), help="前の月")
        title_col.markdown(f"<div class='cal-title'>{month.year}年{month.month}月</div>", unsafe_allow_html=True)
        with next_col.container(horizontal=True, horizontal_alignment="left"):
            st.button("▶", key="cal_next", on_click=move_month, args=(1,), help="次の月")
        with today_col.container(horizontal=True, horizontal_alignment="right"):
            st.button("今日", key="cal_today", on_click=show_date, args=(today(),), icon=":material/today:")

        header = st.columns(7)
        for index, label in enumerate(WEEKDAY_LABELS):
            css_class = "weekday sun" if index == 0 else "weekday sat" if index == 6 else "weekday"
            header[index].markdown(f"<div class='{css_class}'>{label}</div>", unsafe_allow_html=True)

        for week in month_weeks(month.year, month.month):
            cols = st.columns(7)
            for col, day in zip(cols, week):
                if day is None:
                    continue
                state = f"{'sel' if day == selected else 'no'}-{'td' if day == today() else 'no'}"
                with col.container(key=f"cell-{state}-{day.isoformat()}"):
                    # このボタンは CSS でマス全体に広げている（余白やラベルを押しても、その日が選ばれる）
                    st.button(
                        str(day.day),
                        key=f"day_{day.isoformat()}",
                        on_click=show_date,
                        args=(day,),
                        type="tertiary",
                    )
                    day_todos = sort_todos(grouped.get(day, []), SORT_BY_PRIORITY)
                    chips = [chip_html(t) for t in day_todos[:CHIPS_PER_DAY]]
                    if len(day_todos) > CHIPS_PER_DAY:
                        chips.append(more_chip_html(len(day_todos) - CHIPS_PER_DAY))
                    if chips:
                        st.markdown("".join(chips), unsafe_allow_html=True)


def render_selected_day(todos: list[Todo]) -> None:
    day = st.session_state["selected_date"]
    st.markdown(f"#### {day.month}月{day.day}日（{japanese_weekday(day)}）のToDo")

    day_todos = sort_todos([t for t in todos if t.due_date == day], SORT_BY_PRIORITY)
    if not day_todos:
        st.caption("この日のToDoはありません。左下の ＋ から追加できます")
    for todo in day_todos:
        render_card(todo, show_due_date=False)


def render_list(todos: list[Todo]) -> None:
    # 並び順は左端、絞り込みは右端（狭い画面では折り返す）
    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", key="list_tools"):
        sort_label = segmented("並び順", list(SORT_OPTIONS), "sort_order")
        filter_label = segmented("絞り込み", list(FILTER_OPTIONS), "status_filter")

    shown = sort_todos(filter_todos(todos, FILTER_OPTIONS[filter_label]), SORT_OPTIONS[sort_label])
    st.caption(f"{len(shown)}件を表示中（登録 {len(todos)} / {todo_repository.MAX_TODO_COUNT}件）")
    if not todos:
        st.write("ToDoはまだありません。左下の ＋ から追加できます")
    elif not shown:
        st.caption("条件に合うToDoはありません")
    for todo in shown:
        render_card(todo)


def show_panel_errors() -> None:
    for text in st.session_state.get("panel_errors", []):
        st.error(text)


def todo_form_fields(prefix: str) -> None:
    """登録・編集で共通の入力欄。"""
    st.text_input("タイトル（必須）", key=f"{prefix}_title", max_chars=TITLE_MAX_LENGTH)
    st.text_area("内容（任意）", key=f"{prefix}_content", max_chars=CONTENT_MAX_LENGTH)
    st.date_input("期限（必須）", key=f"{prefix}_due", format="YYYY/MM/DD")
    st.radio("優先度", PRIORITIES, key=f"{prefix}_priority", horizontal=True)


@st.dialog("新しいToDo", position="right", on_dismiss=close_panel)
def add_panel() -> None:
    if st.session_state.get("panel") is None:
        st.rerun()  # 登録が終わってパネルを閉じたとき
    show_panel_errors()
    with st.form("new_todo", border=False):
        todo_form_fields("new")
        st.form_submit_button("登録する", on_click=handle_add, key="add_submit", type="primary", icon=":material/check:")


@st.dialog("ToDoの詳細", position="right", on_dismiss=close_panel)
def detail_panel() -> None:
    panel = st.session_state.get("panel")
    if panel is None:
        st.rerun()  # 削除などでパネルを閉じたとき
    todo = find_todo(panel["id"])
    if todo is None:
        st.error("対象のToDoが見つかりません（削除された可能性があります）")
        return
    show_panel_errors()

    if panel["step"] == "edit":
        with st.form("edit_todo", border=False):
            todo_form_fields("edit")
            save_col, cancel_col = st.columns(2)
            save_col.form_submit_button("保存する", on_click=handle_save, args=(todo.id,), key="save_edit", type="primary")
            cancel_col.form_submit_button("キャンセル", on_click=set_panel_step, args=("view",), key="cancel_edit")
        return

    due_text, overdue = due_label(todo.due_date, today())
    st.markdown(card_text_html(todo, due_text, overdue), unsafe_allow_html=True)
    if todo.content:
        st.text(todo.content)
    else:
        st.caption("（内容なし）")
    st.divider()

    if panel["step"] == "delete":
        st.warning("本当に削除しますか？（元に戻せません）")
        confirm_col, cancel_col = st.columns(2)
        confirm_col.button("削除を確定", key="confirm_delete", on_click=handle_delete, args=(todo.id,), type="primary", icon=":material/delete:")
        cancel_col.button("やめる", key="cancel_delete", on_click=set_panel_step, args=("view",))
        return

    edit_col, done_col, delete_col = st.columns(3)
    edit_col.button("編集", key="panel_edit", on_click=start_edit, args=(todo,), icon=":material/edit:")
    if todo.is_completed:
        done_col.button("未完了に戻す", key="panel_toggle", on_click=save_completed, args=(todo.id, False), icon=":material/undo:")
    else:
        done_col.button("完了にする", key="panel_toggle", on_click=save_completed, args=(todo.id, True), icon=":material/check_circle:")
    delete_col.button("削除", key="panel_delete", on_click=set_panel_step, args=("delete",), icon=":material/delete:")


# ---------- メイン ----------


def init_state() -> None:
    st.session_state.setdefault("selected_date", today())
    st.session_state.setdefault("cal_month", today().replace(day=1))
    st.session_state.setdefault("panel", None)
    st.session_state.setdefault("panel_errors", [])
    st.session_state.setdefault("message", None)


def main() -> None:
    st.html(CSS)
    st.html(NO_TRANSLATE_SCRIPT, unsafe_allow_javascript=True)
    init_state()

    title_col, view_col = st.columns([3, 2], vertical_alignment="center")
    title_col.title("📝 ToDoリスト")
    with view_col.container(horizontal=True, horizontal_alignment="right"):
        view = segmented("表示", [VIEW_CALENDAR, VIEW_LIST], "view")
    st.caption("テスト用のアプリです。個人情報や機密情報は入力しないでください。")

    if not secrets_ready():
        st.error("設定が不足しています。管理者に連絡してください")
        st.stop()

    try:
        todos, skipped = load_todos()
    except Exception as exc:
        st.error(error_message(exc, action="読み込み"))
        st.stop()

    show_message()
    if skipped:
        st.warning(f"形式が正しくない行が{skipped}件あったため、表示していません")

    render_dashboard(todos)
    if view == VIEW_CALENDAR:
        render_calendar(todos)
        render_selected_day(todos)
        default_due = st.session_state["selected_date"]
    else:
        render_list(todos)
        default_due = today()

    # 左下の＋ボタン（カレンダー・一覧の両方で使える。カレンダーで選んだ日を期限の初期値にする）
    with st.container(key="fab"):
        st.button("＋", key="fab_add", on_click=open_add_panel, args=(default_due,), type="primary", help="ToDoを追加")

    panel = st.session_state["panel"]
    if panel and panel["mode"] == "add":
        add_panel()
    elif panel and panel["mode"] == "detail":
        detail_panel()


main()
