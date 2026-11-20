"""カレンダー・ダッシュボード・一覧のための計算をまとめたモジュール。

Streamlit にもスプレッドシートにも依存しない、ただの関数だけを置いている。
（そのため、自動テストで簡単に確かめられる）
"""

import calendar
from collections import defaultdict
from datetime import date, timedelta

from todo_repository import Todo

# 日曜始まりのカレンダー（日本のカレンダーでよく使われる形）
WEEKDAY_LABELS = ["日", "月", "火", "水", "木", "金", "土"]
_CALENDAR = calendar.Calendar(firstweekday=calendar.SUNDAY)

# 絞り込みの種類
FILTER_ALL = "all"
FILTER_OPEN = "open"
FILTER_DONE = "done"


def month_weeks(year: int, month: int) -> list[list[date | None]]:
    """その月のカレンダーのマス目を返す。1週間 = 7マス。月の外の日は None。"""
    weeks = []
    for week in _CALENDAR.monthdatescalendar(year, month):
        weeks.append([day if day.month == month else None for day in week])
    return weeks


def shift_month(first_day: date, months: int) -> date:
    """月の1日を、months か月だけ前後に動かす（-1 で前月、+1 で翌月）。"""
    index = first_day.year * 12 + (first_day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def week_range(today: date) -> tuple[date, date]:
    """今日を含む週（日曜〜土曜）の最初と最後の日を返す。"""
    days_since_sunday = (today.weekday() + 1) % 7  # weekday(): 月=0 … 日=6
    start = today - timedelta(days=days_since_sunday)
    return start, start + timedelta(days=6)


def japanese_weekday(day: date) -> str:
    return WEEKDAY_LABELS[(day.weekday() + 1) % 7]


def due_label(due: date, today: date) -> tuple[str, bool]:
    """期限までの日数を言葉にする。戻り値: (表示する文字, 期限切れかどうか)"""
    days = (due - today).days
    if days == 0:
        return "今日", False
    if days == 1:
        return "明日", False
    if days > 1:
        return f"あと{days}日", False
    return f"{-days}日超過", True


def todos_by_date(todos: list[Todo]) -> dict[date, list[Todo]]:
    """期日ごとに Todo をまとめる（カレンダーの各マスに表示するため）。"""
    grouped: dict[date, list[Todo]] = defaultdict(list)
    for todo in todos:
        grouped[todo.due_date].append(todo)
    return grouped


def filter_todos(todos: list[Todo], status: str) -> list[Todo]:
    """未完了・完了済みで絞り込む。"""
    if status == FILTER_OPEN:
        return [t for t in todos if not t.is_completed]
    if status == FILTER_DONE:
        return [t for t in todos if t.is_completed]
    return list(todos)


def dashboard_counts(todos: list[Todo], today: date) -> dict[str, int]:
    """ダッシュボードの4つの数字を数える。

    today     : 今日が期限の未完了
    open      : 未完了（すべて）
    done      : 完了（すべて）
    this_week : 今日〜今週の土曜日が期限の未完了（期限切れは含めない）
    """
    _, week_end = week_range(today)
    open_todos = [t for t in todos if not t.is_completed]
    return {
        "today": sum(1 for t in open_todos if t.due_date == today),
        "open": len(open_todos),
        "done": len(todos) - len(open_todos),
        "this_week": sum(1 for t in open_todos if today <= t.due_date <= week_end),
    }
