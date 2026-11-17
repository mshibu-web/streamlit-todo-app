"""T2〜T6：スプレッドシートとの読み書き処理のテスト（偽物のシートを使用）"""

from datetime import date

import gspread
import pytest

from tests.fakes import FakeWorksheet
from todo_repository import (
    HEADERS,
    RAW,
    SheetFormatError,
    TodoLimitError,
    TodoNotFoundError,
    TodoRepository,
)


def make_repo(rows=None, max_count=200):
    sheet = FakeWorksheet(rows)
    return TodoRepository(sheet, max_count=max_count, retry_wait_seconds=0), sheet


# ---------- T2：登録 ----------

def test_登録すると正しい列順で1行追加される():
    repo, sheet = make_repo()
    todo = repo.add_todo("  資料作成  ", "会議用", date(2026, 11, 20))

    assert len(sheet.rows) == 2
    row = sheet.rows[1]
    assert row[0] == todo.id and len(todo.id) == 32
    assert row[1:4] == ["資料作成", "会議用", "2026-11-20"]  # 前後の空白は取り除く
    assert row[4] == row[5] != ""  # 作成日時 = 更新日時


@pytest.mark.parametrize("empty_rows", [[], [[]], [["", "", ""]]])
def test_空のシートなら見出し行を自動で書き込む(empty_rows):
    # 本物の Google API は空のシートで [[]] を返すことがある
    repo, sheet = make_repo(rows=empty_rows)
    repo.add_todo("t", "", date(2026, 1, 1))
    assert sheet.rows[0] == HEADERS
    assert len(sheet.rows) == 2


def test_見出し行が空でもデータ行があれば書き込まない():
    repo, sheet = make_repo(rows=[["", ""], ["x", "y"]])
    with pytest.raises(SheetFormatError):
        repo.list_todos()
    assert sheet.calls == []


def test_件数上限に達したら登録できない():
    repo, sheet = make_repo(max_count=2)
    repo.add_todo("1", "", date(2026, 1, 1))
    repo.add_todo("2", "", date(2026, 1, 1))
    with pytest.raises(TodoLimitError):
        repo.add_todo("3", "", date(2026, 1, 1))
    assert len(sheet.rows) == 3


def test_見出し行が違うシートには書き込まない():
    repo, sheet = make_repo(rows=[["名前", "メモ"]])
    with pytest.raises(SheetFormatError):
        repo.add_todo("t", "", date(2026, 1, 1))
    assert sheet.calls == []


# ---------- T3・T4：編集 ----------

def test_編集すると指定した行だけが更新される():
    repo, sheet = make_repo()
    a = repo.add_todo("A", "a", date(2026, 1, 1))
    b = repo.add_todo("B", "b", date(2026, 1, 2))
    row_a_before = list(sheet.rows[1])

    repo.update_todo(b.id, "B改", "b改", date(2026, 2, 2))

    assert sheet.rows[1] == row_a_before  # 他の行は変わらない
    row_b = sheet.rows[2]
    assert row_b[0] == b.id  # ID は変わらない
    assert row_b[1:4] == ["B改", "b改", "2026-02-02"]
    assert row_b[4] == b.created_at  # 作成日時は変わらない
    assert a.id != b.id


def test_存在しないIDなら書き込まない():
    repo, sheet = make_repo()
    repo.add_todo("A", "", date(2026, 1, 1))
    calls_before = list(sheet.calls)
    with pytest.raises(TodoNotFoundError):
        repo.update_todo("no-such-id", "x", "", date(2026, 1, 1))
    assert sheet.calls == calls_before


# ---------- T5：一覧 ----------

def test_一覧は期日の昇順で並ぶ():
    repo, _ = make_repo()
    repo.add_todo("遅い", "", date(2026, 12, 31))
    repo.add_todo("早い", "", date(2026, 1, 1))
    repo.add_todo("中間", "", date(2026, 6, 1))
    todos, skipped = repo.list_todos()
    assert [t.title for t in todos] == ["早い", "中間", "遅い"]
    assert skipped == 0


def test_同じ期日なら登録が古い順():
    rows = [
        HEADERS,
        ["2", "後", "", "2026-01-01", "2026-01-01 10:00:00", ""],
        ["1", "先", "", "2026-01-01", "2026-01-01 09:00:00", ""],
    ]
    repo, _ = make_repo(rows)
    todos, _ = repo.list_todos()
    assert [t.title for t in todos] == ["先", "後"]


def test_0件なら空の一覧():
    repo, _ = make_repo()
    assert repo.list_todos() == ([], 0)


def test_形式が正しくない行は読み飛ばす():
    rows = [
        HEADERS,
        ["1", "正しい", "", "2026-01-01", "", ""],
        ["2", "日付が変", "", "2026/13/45", "", ""],
        ["", "IDなし", "", "2026-01-01", "", ""],
        ["", "", "", "", "", ""],  # 空行は数えない
        ["3", "列が足りない", "", "2026-01-02"],
    ]
    repo, _ = make_repo(rows)
    todos, skipped = repo.list_todos()
    assert [t.title for t in todos] == ["正しい", "列が足りない"]
    assert skipped == 2


# ---------- T6：数式対策 ----------

def test_数式のような入力も文字列のまま保存される():
    repo, sheet = make_repo()
    todo = repo.add_todo("=1+1", '=IMPORTXML("http://example.com","//a")', date(2026, 1, 1))
    assert sheet.rows[1][1:3] == ["=1+1", '=IMPORTXML("http://example.com","//a")']

    repo.update_todo(todo.id, "+SUM(A1)", "@x", date(2026, 1, 1))
    assert sheet.rows[1][1:3] == ["+SUM(A1)", "@x"]

    assert all(option == RAW for _, option in sheet.calls)  # すべて RAW で書き込んでいる


# ---------- エラー処理：回数制限 ----------

class FakeResponse:
    status_code = 429

    def json(self):
        return {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}


def test_回数制限に当たったら1回だけ再試行する():
    repo, sheet = make_repo()
    original = sheet.get_all_values
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise gspread.exceptions.APIError(FakeResponse())
        return original()

    sheet.get_all_values = flaky
    assert repo.list_todos() == ([], 0)
    assert attempts["n"] == 2


def test_回数制限が続いたらエラーになる():
    repo, sheet = make_repo()

    def always_429():
        raise gspread.exceptions.APIError(FakeResponse())

    sheet.get_all_values = always_429
    with pytest.raises(gspread.exceptions.APIError):
        repo.list_todos()
