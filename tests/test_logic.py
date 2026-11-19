"""T17・T18：カレンダー・ダッシュボードの計算のテスト（Streamlit を使わない）"""

from datetime import date

from todo_logic import (
    FILTER_ALL,
    FILTER_DONE,
    FILTER_OPEN,
    dashboard_counts,
    due_label,
    filter_todos,
    japanese_weekday,
    month_weeks,
    shift_month,
    todos_by_date,
    week_range,
)
from todo_repository import Todo


def todo(title, due, done=False):
    return Todo(title, title, "", due, "2026-11-01 09:00:00", "", "2026-11-19 08:00:00" if done else "", "中")


# ---------- T17：カレンダーの計算 ----------

def test_2026年11月のマス目は日曜始まり():
    weeks = month_weeks(2026, 11)
    assert weeks[0][0] == date(2026, 11, 1)  # 11/1 は日曜日
    assert all(len(w) == 7 for w in weeks)
    days = [d for w in weeks for d in w if d]
    assert days[0] == date(2026, 11, 1) and days[-1] == date(2026, 11, 30) and len(days) == 30


def test_月の外の日はNone():
    weeks = month_weeks(2026, 12)  # 12/1 は火曜日
    assert weeks[0][:2] == [None, None]
    assert weeks[0][2] == date(2026, 12, 1)


def test_前月と翌月_年をまたぐ():
    assert shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert shift_month(date(2026, 11, 1), 0) == date(2026, 11, 1)


def test_今週は日曜から土曜():
    assert week_range(date(2026, 11, 19)) == (date(2026, 11, 15), date(2026, 11, 21))  # 木曜
    assert week_range(date(2026, 11, 15)) == (date(2026, 11, 15), date(2026, 11, 21))  # 日曜
    assert week_range(date(2026, 11, 21)) == (date(2026, 11, 15), date(2026, 11, 21))  # 土曜


def test_曜日():
    assert japanese_weekday(date(2026, 11, 19)) == "木"
    assert japanese_weekday(date(2026, 11, 15)) == "日"


def test_期限の表示():
    today = date(2026, 11, 19)
    assert due_label(date(2026, 11, 19), today) == ("今日", False)
    assert due_label(date(2026, 11, 20), today) == ("明日", False)
    assert due_label(date(2026, 11, 24), today) == ("あと5日", False)
    assert due_label(date(2026, 11, 18), today) == ("1日超過", True)


def test_日付ごとにまとめる():
    a, b, c = todo("a", date(2026, 11, 19)), todo("b", date(2026, 11, 19)), todo("c", date(2026, 11, 20))
    grouped = todos_by_date([a, b, c])
    assert grouped[date(2026, 11, 19)] == [a, b]
    assert grouped[date(2026, 11, 20)] == [c]


def test_絞り込み():
    open_todo, done_todo = todo("open", date(2026, 11, 19)), todo("done", date(2026, 11, 19), done=True)
    todos = [open_todo, done_todo]
    assert filter_todos(todos, FILTER_ALL) == todos
    assert filter_todos(todos, FILTER_OPEN) == [open_todo]
    assert filter_todos(todos, FILTER_DONE) == [done_todo]


# ---------- T18：ダッシュボード ----------

def test_ダッシュボードの数え方():
    today = date(2026, 11, 19)
    todos = [
        todo("今日", today),
        todo("今日・完了", today, done=True),
        todo("土曜", date(2026, 11, 21)),
        todo("日曜（来週）", date(2026, 11, 22)),
        todo("期限切れ", date(2026, 11, 1)),
    ]
    assert dashboard_counts(todos, today) == {"today": 1, "open": 4, "done": 1, "this_week": 2}


def test_0件のダッシュボード():
    assert dashboard_counts([], date(2026, 11, 19)) == {"today": 0, "open": 0, "done": 0, "this_week": 0}
