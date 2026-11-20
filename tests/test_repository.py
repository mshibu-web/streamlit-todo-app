"""T2〜T6：スプレッドシートとの読み書き処理のテスト（偽物のシートを使用）"""

from datetime import date

import gspread
import pytest

from tests.fakes import FakeWorksheet
from todo_repository import (
    HEADERS,
    RAW,
    SORT_BY_DUE,
    SORT_BY_PRIORITY,
    SheetFormatError,
    TodoLimitError,
    TodoNotFoundError,
    TodoRepository,
    sort_todos,
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


# =====================================================================
# 第4版（課題2）で追加したテスト
# =====================================================================

OLD_HEADERS = ["id", "title", "content", "due_date", "created_at", "updated_at"]  # 第3版のシート


def old_sheet_rows():
    """第3版（6列）の形のシート。既存データが2件入っている。"""
    return [
        list(OLD_HEADERS),
        ["a1", "既存1", "メモ", "2026-11-20", "2026-11-17 10:00:00", "2026-11-17 10:00:00"],
        ["a2", "既存2", "", "2026-11-21", "2026-11-17 11:00:00", "2026-11-17 11:00:00"],
    ]


# ---------- T7：列の追加（既存データを消さない） ----------

def test_T7_古いシートを読むと見出しG1H1だけが追加され既存の行は変わらない():
    repo, sheet = make_repo(old_sheet_rows())
    data_before = [list(r) for r in sheet.rows[1:]]

    todos, skipped = repo.list_todos()

    assert sheet.rows[0] == HEADERS  # 見出しに completed_at・priority が付いた
    assert sheet.rows[1:] == data_before  # 既存の行は1文字も変わらない
    assert sheet.updated_ranges == ["G1:H1"]  # 書き込んだのは見出しの2マスだけ
    assert skipped == 0
    assert [(t.title, t.is_completed, t.priority) for t in todos] == [("既存1", False, "中"), ("既存2", False, "中")]


def test_T7_見出しがそろっていれば何も書き込まない():
    repo, sheet = make_repo()
    repo.list_todos()
    assert sheet.calls == []


def test_T7_G列H列に違う見出しがあればデータを守るため止まる():
    rows = old_sheet_rows()
    rows[0] = rows[0] + ["メモ欄", ""]
    repo, sheet = make_repo(rows)
    with pytest.raises(SheetFormatError):
        repo.list_todos()
    assert sheet.calls == []


def test_T7_古いシートに登録しても既存の行は残る():
    repo, sheet = make_repo(old_sheet_rows())
    repo.add_todo("新規", "", date(2026, 12, 1), "高")
    assert [r[0] for r in sheet.rows[1:3]] == ["a1", "a2"]
    assert len(sheet.rows) == 4
    assert sheet.rows[3][6:8] == ["", "高"]


# ---------- T8：削除 ----------

def test_T8_削除すると指定した行だけが消える():
    repo, sheet = make_repo()
    a = repo.add_todo("A", "", date(2026, 1, 1))
    b = repo.add_todo("B", "", date(2026, 1, 2))
    c = repo.add_todo("C", "", date(2026, 1, 3))

    repo.delete_todo(b.id)

    assert [r[0] for r in sheet.rows[1:]] == [a.id, c.id]


def test_T8_存在しないIDなら何も削除しない():
    repo, sheet = make_repo()
    repo.add_todo("A", "", date(2026, 1, 1))
    rows_before = [list(r) for r in sheet.rows]
    with pytest.raises(TodoNotFoundError):
        repo.delete_todo("no-such-id")
    assert sheet.rows == rows_before
    assert ("delete", None) not in sheet.calls


def test_T8_削除の直前に行がずれていたら削除しない():
    repo, sheet = make_repo()
    repo.add_todo("A", "", date(2026, 1, 1))
    b = repo.add_todo("B", "", date(2026, 1, 2))

    # 一覧を読んだ「後」、削除する「前」に、別の操作で行がずれた状況を再現する
    original_acell = sheet.acell

    def shifted_acell(label):
        sheet.rows.insert(1, ["zz", "割り込み", "", "2026-01-01", "", "", "", "中"])
        return original_acell(label)

    sheet.acell = shifted_acell
    with pytest.raises(TodoNotFoundError):
        repo.delete_todo(b.id)
    assert ("delete", None) not in sheet.calls
    assert b.id in [r[0] for r in sheet.rows]


# ---------- T9：完了・未完了 ----------

def test_T9_完了にするとF列とG列だけが変わる():
    repo, sheet = make_repo()
    todo = repo.add_todo("A", "メモ", date(2026, 1, 1), "高")
    before = list(sheet.rows[1])

    repo.set_completed(todo.id, True)

    after = sheet.rows[1]
    assert sheet.updated_ranges[-1] == "F2:G2"
    assert after[:5] == before[:5]  # ID・タイトル・内容・期日・作成日時は変わらない
    assert after[7] == "高"  # 優先度も変わらない
    assert after[6] != ""  # 完了日時が入った
    todos, _ = repo.list_todos()
    assert todos[0].is_completed


def test_T9_未完了に戻すと完了日時が空になる():
    repo, sheet = make_repo()
    todo = repo.add_todo("A", "", date(2026, 1, 1))
    repo.set_completed(todo.id, True)
    repo.set_completed(todo.id, False)
    assert sheet.rows[1][6] == ""
    assert not repo.list_todos()[0][0].is_completed


def test_T9_存在しないIDなら完了にしない():
    repo, sheet = make_repo()
    repo.add_todo("A", "", date(2026, 1, 1))
    calls_before = list(sheet.calls)
    with pytest.raises(TodoNotFoundError):
        repo.set_completed("no-such-id", True)
    assert sheet.calls == calls_before


def test_T9_編集しても完了状態は変わらない():
    repo, sheet = make_repo()
    todo = repo.add_todo("A", "", date(2026, 1, 1))
    repo.set_completed(todo.id, True)
    completed_at = sheet.rows[1][6]

    repo.update_todo(todo.id, "A改", "", date(2026, 1, 5), "低")

    assert sheet.rows[1][1] == "A改"
    assert sheet.rows[1][6] == completed_at
    assert sheet.rows[1][7] == "低"


# ---------- T10：優先度 ----------

def test_T10_優先度を保存して読み込める():
    repo, sheet = make_repo()
    repo.add_todo("A", "", date(2026, 1, 1), "低")
    assert sheet.rows[1][7] == "低"
    assert repo.list_todos()[0][0].priority == "低"


@pytest.mark.parametrize("value", ["", "最高", "high", "  "])
def test_T10_不正な優先度は中として扱う(value):
    rows = [HEADERS, ["1", "A", "", "2026-01-01", "", "", "", value]]
    repo, _ = make_repo(rows)
    todos, skipped = repo.list_todos()
    assert todos[0].priority == "中"
    assert skipped == 0


# ---------- T11：並べ替え ----------

def sample_for_sort():
    # (ID, タイトル, 期日, 作成日時, 優先度)
    data = [
        ("1", "低・早い", "2026-01-01", "2026-01-01 09:00:00", "低"),
        ("2", "高・遅い", "2026-03-01", "2026-01-01 09:00:00", "高"),
        ("3", "高・早い", "2026-01-01", "2026-01-01 10:00:00", "高"),
        ("4", "中・早い・新", "2026-01-01", "2026-01-01 12:00:00", "中"),
        ("5", "中・早い・古", "2026-01-01", "2026-01-01 08:00:00", "中"),
    ]
    rows = [HEADERS] + [[i, t, "", d, c, c, "", p] for i, t, d, c, p in data]
    return make_repo(rows)[0]


def test_T11_期日順は期日_優先度_登録の古い順():
    repo = sample_for_sort()
    todos, _ = repo.list_todos(SORT_BY_DUE)
    assert [t.title for t in todos] == ["高・早い", "中・早い・古", "中・早い・新", "低・早い", "高・遅い"]


def test_T11_優先度順は優先度_期日_登録の古い順():
    repo = sample_for_sort()
    todos, _ = repo.list_todos(SORT_BY_PRIORITY)
    assert [t.title for t in todos] == ["高・早い", "高・遅い", "中・早い・古", "中・早い・新", "低・早い"]


def test_T11_sort_todosは元のリストを変えない():
    repo = sample_for_sort()
    todos, _ = repo.list_todos(SORT_BY_DUE)
    titles_before = [t.title for t in todos]
    sort_todos(todos, SORT_BY_PRIORITY)
    assert [t.title for t in todos] == titles_before
