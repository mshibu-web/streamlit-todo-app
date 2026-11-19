"""画面の動作テスト（Streamlit の AppTest を使用。Google には接続しない）

第5版の画面（カレンダー中心・＋ボタン・右から開くパネル）に合わせたテスト。
「今日」は 2026-11-19（木）に固定している。
"""

from datetime import date
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import todo_repository
from tests.fakes import FakeWorksheet
from todo_repository import HEADERS

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
TODAY = date(2026, 11, 19)  # 木曜日


@pytest.fixture
def sheet(monkeypatch):
    fake = FakeWorksheet()
    monkeypatch.setattr(todo_repository, "open_worksheet", lambda *args, **kwargs: fake)
    monkeypatch.setattr(todo_repository, "today_jst", lambda: TODAY)
    st.cache_resource.clear()
    st.cache_data.clear()
    return fake


def make_app():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.secrets["spreadsheet"] = {"id": "dummy-id", "worksheet": "todos"}
    at.secrets["gcp_service_account"] = {"type": "service_account"}
    return at.run()


def row(todo_id, title, due, priority="中", completed_at="", created="2026-11-01 09:00:00"):
    return [todo_id, title, "", due, created, created, completed_at, priority]


def texts(elements):
    return [e.value for e in elements]


def all_markdown(at) -> str:
    return "\n".join(texts(at.markdown))


def panel_is_open(at) -> bool:
    keys = [w.key for w in at.text_input] + [b.key for b in at.button]
    return any(k in keys for k in ("new_title", "edit_title", "panel_edit", "confirm_delete"))


def open_add(at):
    return at.button(key="fab_add").click().run()


def fill_and_add(at, title, due, priority="中", content=""):
    at.text_input(key="new_title").input(title)
    at.text_area(key="new_content").input(content)
    at.date_input(key="new_due").set_value(due)
    at.radio(key="new_priority").set_value(priority)
    return at.button(key="add_submit").click().run()


def add(at, title, due, priority="中", content=""):
    return fill_and_add(open_add(at), title, due, priority, content)


def show_list(at):
    return at.button_group(key="view").set_value("📋 一覧").run()


# ---------- 初期表示 ----------

def test_初期表示はカレンダーで今月と今日が表示される(sheet):
    at = make_app()
    assert not at.exception
    assert "個人情報" in at.caption[0].value
    assert "2026年11月" in all_markdown(at)
    assert "#### 11月19日（木）のToDo" in texts(at.markdown)
    assert "この日のToDoはありません。左下の ＋ から追加できます" in texts(at.caption)
    assert at.title[0].value == "📝 ToDoリスト"
    assert "add_on_day" not in [b.key for b in at.button]  # 小さな追加ボタンは整理した（＋ボタンだけ）
    assert at.button(key="day_2026-11-19")
    assert at.button(key="fab_add")
    assert not panel_is_open(at)  # 登録フォームは常時表示しない


def test_ダッシュボードの件数(sheet):
    sheet.rows += [
        row("1", "今日・未完了", "2026-11-19"),
        row("2", "今日・完了", "2026-11-19", completed_at="2026-11-19 08:00:00"),
        row("3", "土曜・未完了", "2026-11-21"),
        row("4", "期限切れ", "2026-11-10"),
        row("5", "来週", "2026-11-23"),
    ]
    at = make_app()
    values = {m.label: m.value for m in at.metric}
    assert values == {
        "📌 今日のToDo": "1件",
        "⏳ 未完了": "4件",
        "✅ 完了": "1件",
        "🗓️ 今週の残り": "2件",  # 今日〜土曜（11/19〜11/21）の未完了
    }


# ---------- ＋ボタンと登録パネル（M1・M2・M7） ----------

def test_M1_プラスボタンで登録パネルが開き登録できる(sheet):
    at = open_add(make_app())
    assert panel_is_open(at)
    assert at.date_input(key="new_due").value == TODAY  # 期限の初期値は選んでいる日（今日）

    at = fill_and_add(at, "資料作成", date(2026, 11, 20), "高", "会議用")

    assert not at.exception
    assert texts(at.toast) == ["登録しました"]
    assert sheet.rows[1][1:4] == ["資料作成", "会議用", "2026-11-20"]
    assert sheet.rows[1][6:8] == ["", "高"]
    assert not panel_is_open(at)  # 登録したらパネルは閉じる
    assert "#### 11月20日（金）のToDo" in texts(at.markdown)  # 登録した日が選ばれる
    assert "資料作成" in all_markdown(at)


def test_日付を選んでから追加するとその日が期限の初期値になる(sheet):
    at = make_app()
    at.button(key="day_2026-11-25").click().run()
    assert "#### 11月25日（水）のToDo" in texts(at.markdown)

    at = open_add(at)  # 右下の＋ボタン
    assert panel_is_open(at)
    assert at.date_input(key="new_due").value == date(2026, 11, 25)


def test_一覧表示でもプラスボタンが使え期限の初期値は今日(sheet):
    at = show_list(make_app())
    at = open_add(at)
    assert panel_is_open(at)
    assert at.date_input(key="new_due").value == TODAY
    at = fill_and_add(at, "一覧から追加", date(2026, 11, 30))
    assert sheet.rows[1][1] == "一覧から追加"
    assert "一覧から追加" in all_markdown(at)  # 一覧のまま、追加したものが表示される


def test_M2_タイトル空欄ならパネルにエラーが出て登録されない(sheet):
    at = fill_and_add(open_add(make_app()), "", TODAY, content="メモだけ")
    assert "タイトルを入力してください" in texts(at.error)
    assert len(sheet.rows) == 1
    assert panel_is_open(at)  # パネルは開いたまま
    assert at.text_area(key="new_content").value == "メモだけ"  # 入力値は残る


def test_M7_件数上限ならエラー表示で登録されない(sheet):
    sheet.rows += [row(str(i), f"t{i}", "2026-01-01") for i in range(200)]
    at = add(make_app(), "201件目", TODAY)
    assert "登録件数の上限（200件）に達しているため、登録できません" in texts(at.error)
    assert len(sheet.rows) == 201


def test_別の月の日付で登録するとその月が表示される(sheet):
    at = add(make_app(), "年明け", date(2027, 1, 5))
    assert "2027年1月" in all_markdown(at)
    assert "#### 1月5日（火）のToDo" in texts(at.markdown)


# ---------- カレンダー ----------

def test_前月_翌月_今日へ移動できる(sheet):
    at = make_app()
    at.button(key="cal_next").click().run()
    assert "2026年12月" in all_markdown(at)
    at.button(key="cal_prev").click().run()
    at.button(key="cal_prev").click().run()
    assert "2026年10月" in all_markdown(at)
    at.button(key="cal_today").click().run()
    assert "2026年11月" in all_markdown(at)
    assert "#### 11月19日（木）のToDo" in texts(at.markdown)


def test_カレンダーの日付に優先度の色ラベルが表示される(sheet):
    sheet.rows += [
        row("1", "高いもの", "2026-11-20", "高"),
        row("2", "低いもの", "2026-11-20", "低"),
        row("3", "完了したもの", "2026-11-20", "高", completed_at="2026-11-19 08:00:00"),
    ]
    at = make_app()
    md = all_markdown(at)
    assert 'class="todo-chip p-high"' in md and "高いもの" in md
    assert 'class="todo-chip p-low"' in md
    assert 'class="todo-chip p-done"' in md and "✓ 完了したもの" in md


def test_1日に4件以上あると他N件と表示される(sheet):
    sheet.rows += [row(str(i), f"t{i}", "2026-11-20") for i in range(5)]
    at = make_app()
    assert "他2件" in all_markdown(at)


def test_タイトルのHTMLは文字として表示される(sheet):
    sheet.rows += [row("1", "<b>太字</b><script>x</script>", "2026-11-19")]
    md = all_markdown(make_app())
    assert "&lt;b&gt;太字&lt;/b&gt;&lt;script&gt;" in md
    assert "<script>" not in md


# ---------- 一覧 ----------

def test_一覧に切り替えるとカードで表示され並べ替えと絞り込みができる(sheet):
    sheet.rows += [
        row("1", "低・早い", "2026-11-20", "低"),
        row("2", "高・遅い", "2026-12-01", "高"),
        row("3", "完了済み", "2026-11-25", "中", completed_at="2026-11-19 08:00:00"),
    ]
    at = show_list(make_app())
    assert not at.exception
    assert "2026年11月" not in all_markdown(at)  # カレンダーは表示しない

    def order():
        md = all_markdown(at)
        return sorted(["低・早い", "高・遅い", "完了済み"], key=lambda t: md.find(t) if t in md else 10**9)

    assert order() == ["低・早い", "完了済み", "高・遅い"]  # 期日順

    at.button_group(key="sort_order").set_value("優先度順").run()
    assert order()[:2] == ["高・遅い", "完了済み"]

    at.button_group(key="status_filter").set_value("未完了").run()
    md = all_markdown(at)
    assert "完了済み" not in md and "低・早い" in md

    at.button_group(key="status_filter").set_value("完了済み").run()
    md = all_markdown(at)
    assert "完了済み" in md and "低・早い" not in md


def test_一覧で期限の残り日数と超過が分かる(sheet):
    sheet.rows += [row("1", "明日のもの", "2026-11-20"), row("2", "遅れているもの", "2026-11-17")]
    md = all_markdown(show_list(make_app()))
    assert '<span class="due">明日</span>' in md
    assert '<span class="due overdue">2日超過</span>' in md


# ---------- 完了チェック ----------

def test_カードの完了チェックで見た目とシートが変わる(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]
    at = make_app()

    at.checkbox(key="done_a1").check().run()
    assert not at.exception
    assert sheet.rows[1][6] != ""  # G列に完了日時
    assert at.checkbox(key="done_a1").value is True
    assert "✓</span><span class=\"title-text\">資料作成" in all_markdown(at)  # 完了の印はグレーの ✓（緑の ✅ は使わない）
    assert "✅ 資料作成" not in all_markdown(at)
    assert "card-title done" in all_markdown(at)

    at.checkbox(key="done_a1").uncheck().run()
    assert sheet.rows[1][6] == ""
    assert at.checkbox(key="done_a1").value is False


def test_古いシートの既存データは消えずに未完了として表示される(sheet):
    original = ["a1", "既存", "", "2026-11-19", "2026-11-17 10:00:00", "2026-11-17 10:00:00"]
    sheet.rows = [HEADERS[:6], list(original)]
    at = make_app()
    assert not at.exception
    assert at.checkbox(key="done_a1").value is False
    assert "既存" in all_markdown(at)
    assert sheet.rows[0] == HEADERS  # 見出しだけ追加
    assert sheet.rows[1] == original  # データは変わらない


# ---------- 詳細パネル：編集（M3・M4） ----------

def test_M3_詳細パネルで編集して保存できる(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19", "低")]
    at = make_app()
    at.button(key="open_a1").click().run()
    assert panel_is_open(at)

    at.button(key="panel_edit").click().run()
    assert at.text_input(key="edit_title").value == "資料作成"  # 現在値が入っている
    assert at.radio(key="edit_priority").value == "低"

    at.text_input(key="edit_title").input("資料作成（改）")
    at.radio(key="edit_priority").set_value("高")
    at.date_input(key="edit_due").set_value(date(2026, 11, 25))
    at.button(key="save_edit").click().run()

    assert not at.exception
    assert texts(at.toast) == ["更新しました"]
    assert sheet.rows[1][0] == "a1"
    assert sheet.rows[1][1:4] == ["資料作成（改）", "", "2026-11-25"]
    assert sheet.rows[1][7] == "高"


def test_M4_編集をキャンセルすると何も変わらない(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]
    before = [list(r) for r in sheet.rows]
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_edit").click().run()
    at.text_input(key="edit_title").input("変更したけどやめる")
    at.button(key="cancel_edit").click().run()
    assert sheet.rows == before
    assert at.button(key="panel_edit")  # 確認の画面に戻る


def test_編集でタイトルを空にするとエラーで保存されない(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_edit").click().run()
    at.text_input(key="edit_title").input("")
    at.button(key="save_edit").click().run()
    assert "タイトルを入力してください" in texts(at.error)
    assert sheet.rows[1][1] == "資料作成"


def test_詳細パネルで完了にできる(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_toggle").click().run()
    assert sheet.rows[1][6] != ""
    assert at.button(key="panel_toggle").label == "未完了に戻す"


# ---------- 詳細パネル：削除 ----------

def test_削除を押しただけでは消えず確認が出る(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_delete").click().run()
    assert len(sheet.rows) == 2  # まだ消えていない
    assert "本当に削除しますか？（元に戻せません）" in texts(at.warning)


def test_やめるを押すと何も変わらない(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]
    before = [list(r) for r in sheet.rows]
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_delete").click().run()
    at.button(key="cancel_delete").click().run()
    assert sheet.rows == before
    assert not at.warning
    assert at.button(key="panel_delete")


def test_削除を確定するとシートから消えパネルが閉じる(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19"), row("a2", "買い物", "2026-11-19")]
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_delete").click().run()
    at.button(key="confirm_delete").click().run()

    assert not at.exception
    assert texts(at.toast) == ["削除しました"]
    assert [r[0] for r in sheet.rows[1:]] == ["a2"]
    assert not panel_is_open(at)
    assert "資料作成" not in all_markdown(at)


def test_削除に失敗しても内部情報は表示しない(sheet):
    sheet.rows += [row("a1", "資料作成", "2026-11-19")]

    def broken(*args, **kwargs):
        raise RuntimeError("secret-detail-should-not-be-shown")

    sheet.delete_rows = broken
    at = make_app()
    at.button(key="open_a1").click().run()
    at.button(key="panel_delete").click().run()
    at.button(key="confirm_delete").click().run()
    assert texts(at.error) == ["データの削除に失敗しました。時間をおいて再度お試しください"]
    assert len(sheet.rows) == 2


# ---------- エラー処理 ----------

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
