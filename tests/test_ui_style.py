"""完了済みのToDoの色分け（優先度に関係なくグレー。未完了に戻すと優先度の色に戻る）。"""

from dataclasses import replace
from datetime import date

import pytest

from todo_repository import Todo
from ui_style import CSS, badge_html, card_text_html, chip_html, priority_code


def make(priority, done):
    return Todo("x1", "資料作成", "", date(2026, 11, 20), "2026-11-17 09:00:00", "",
                "2026-11-20 10:00:00" if done else "", priority)


@pytest.mark.parametrize("priority, code", [("高", "high"), ("中", "mid"), ("低", "low")])
def test_open_todo_uses_priority_color(priority, code):
    todo = make(priority, done=False)
    assert priority_code(todo) == code
    assert f"p-{code}" in chip_html(todo)
    assert f"p-{code}" in badge_html(todo)


@pytest.mark.parametrize("priority", ["高", "中", "低"])
def test_done_todo_is_gray_regardless_of_priority(priority):
    todo = make(priority, done=True)
    assert priority_code(todo) == "done"
    assert 'class="todo-chip p-done"' in chip_html(todo)
    assert "p-done" in badge_html(todo)
    text = card_text_html(todo, "今日", False)
    assert 'class="card-title done"' in text  # 完了のクラス（グレーの文字）
    assert '<span class="done-mark">✓</span>' in text and "✅" not in text


@pytest.mark.parametrize("priority, code", [("高", "high"), ("中", "mid"), ("低", "low")])
def test_reopened_todo_returns_to_priority_color(priority, code):
    reopened = replace(make(priority, done=True), completed_at="")
    assert priority_code(reopened) == code


def test_done_colors_are_gray():
    """完了の色はグレー（赤・緑・青のどれかに偏らない）。"""
    for name in ("done-bg", "done-fg", "done-dot"):
        value = CSS.split(f"--{name}:")[1].split(";")[0].strip().lstrip("#")
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
        assert max(r, g, b) - min(r, g, b) <= 12, name
    assert "line-through" not in CSS  # 完了済みにも取り消し線は付けない（✓ とグレーで区別する）
