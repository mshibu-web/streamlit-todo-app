"""T15・T16：LINE リマインド通知（notify.py）のテスト。

本物の LINE・Google には接続しない（送信処理とシートは偽物に差し替える）。
"""

import json
import logging
import urllib.parse
from datetime import date
from pathlib import Path

import pytest

import notify
from notify import NotifyError, Settings, Targets, build_message, load_settings, run, select_targets
from tests.fakes import FakeWorksheet
from todo_repository import BASE_HEADERS, HEADERS, Todo

TODAY = date(2026, 11, 21)  # 土曜日
USER_ID = "U" + "0123456789abcdef" * 2
ROOT = Path(__file__).resolve().parent.parent


def todo(title, due, priority="中", done=False, todo_id=None):
    return Todo(todo_id or title, title, "本文は送らない", due, "2026-11-01 09:00:00", "",
                "2026-11-20 10:00:00" if done else "", priority)


def row(todo_id, title, due, priority="中", completed_at=""):
    return [todo_id, title, "秘密の本文", due, "2026-11-01 09:00:00", "2026-11-01 09:00:00", completed_at, priority]


def settings(**overrides):
    base = dict(service_account_info={"type": "service_account"}, spreadsheet_id="sheet-id", worksheet_name="todos",
                channel_id="1234567890", channel_secret="channel-secret-value", user_id=USER_ID,
                app_url="https://example.streamlit.app", dry_run=False)
    base.update(overrides)
    return Settings(**base)


class FakeLine:
    """偽物の LINE。送られた内容を記録する。"""

    def __init__(self, push_status=200, token_status=200):
        self.calls = []
        self.push_status = push_status
        self.token_status = token_status

    def __call__(self, url, data, headers):
        self.calls.append((url, data, headers))
        if url == notify.LINE_TOKEN_URL:
            return self.token_status, json.dumps({"access_token": "short-lived-token", "expires_in": 900}).encode()
        if url == notify.LINE_PUSH_URL:
            return self.push_status, b"{}"
        raise AssertionError(f"想定外の送り先: {url}")

    @property
    def pushes(self):
        return [c for c in self.calls if c[0] == notify.LINE_PUSH_URL]


def sheet_with(*rows):
    return FakeWorksheet([HEADERS, *rows])


def opener(sheet):
    def open_sheet(info, spreadsheet_id, worksheet_name):
        open_sheet.args = (spreadsheet_id, worksheet_name)
        return sheet
    return open_sheet


# ---------- T15：通知の対象 ----------


def test_今日が期限と期限切れの未完了だけが選ばれる():
    todos = [
        todo("今日・未完了", TODAY),
        todo("今日・完了", TODAY, done=True),
        todo("昨日・未完了", date(2026, 11, 20)),
        todo("昨日・完了", date(2026, 11, 20), done=True),
        todo("明日・未完了", date(2026, 11, 22)),
    ]
    targets = select_targets(todos, TODAY)
    assert [t.title for t in targets.due_today] == ["今日・未完了"]
    assert [t.title for t in targets.overdue] == ["昨日・未完了"]


def test_今日の分は優先度順_期限切れは古い順で同じ日なら優先度順():
    todos = [
        todo("今日・低", TODAY, "低"), todo("今日・高", TODAY, "高"), todo("今日・中", TODAY, "中"),
        todo("3日前・低", date(2026, 11, 18), "低"), todo("10日前", date(2026, 11, 11), "中"),
        todo("3日前・高", date(2026, 11, 18), "高"),
    ]
    targets = select_targets(todos, TODAY)
    assert [t.title for t in targets.due_today] == ["今日・高", "今日・中", "今日・低"]
    assert [t.title for t in targets.overdue] == ["10日前", "3日前・高", "3日前・低"]


def test_対象が0件なら送信しない_LINEに接続もしない():
    sheet = sheet_with(row("a", "明日", "2026-11-22"), row("b", "完了", "2026-11-21", completed_at="x"))
    line = FakeLine()
    assert run(settings(), TODAY, open_sheet=opener(sheet), post=line) == "no_targets"
    assert line.calls == []


# ---------- 通知の文面 ----------


def test_文面にタイトル_期限_優先度_アプリのリンクが入り_本文は入らない():
    targets = select_targets(
        [todo("資料作成", TODAY, "高"), todo("買い物", TODAY, "中"), todo("請求書", date(2026, 11, 10), "高")], TODAY
    )
    text = build_message(targets, TODAY, "https://example.streamlit.app")
    assert text == (
        "【ToDoリマインド】11/21（土）\n"
        "\n"
        "■ 今日が期限（2件）\n"
        "[高] 資料作成\n"
        "[中] 買い物\n"
        "\n"
        "■ 期限切れ（1件）\n"
        "[高] 請求書（11/10・11日超過）\n"
        "\n"
        "▶ ToDoアプリを開く\n"
        "https://example.streamlit.app"
    )
    assert "本文は送らない" not in text


def test_片方だけのときは空の区分を出さない_リンクは省略できる():
    text = build_message(Targets([], [todo("古い", date(2026, 11, 20), "低")]), TODAY)
    assert "今日が期限" not in text
    assert "[低] 古い（11/20・1日超過）" in text
    assert "ToDoアプリを開く" not in text


def test_各区分は10件まで表示し_残りは他N件にまとめる():
    many = [todo(f"件{i:02d}", TODAY) for i in range(13)]
    text = build_message(Targets(many, []), TODAY)
    assert "■ 今日が期限（13件）" in text
    assert "件09" in text and "件10" not in text
    assert "…他3件" in text
    assert len(text) <= notify.MAX_MESSAGE_LENGTH


# ---------- T16：送信（本物の LINE には送らない） ----------


def test_本人1人だけに_短期トークンで1通だけ送る():
    sheet = sheet_with(row("a", "資料作成", "2026-11-21", "高"))
    line = FakeLine()
    assert run(settings(), TODAY, open_sheet=opener(sheet), post=line) == "sent"

    token_call, push_call = line.calls  # トークン発行 → 送信 の2回だけ
    assert token_call[0] == "https://api.line.me/oauth2/v3/token"  # 短期トークン（15分）の発行
    form = urllib.parse.parse_qs(token_call[1].decode())
    assert form == {"grant_type": ["client_credentials"], "client_id": ["1234567890"],
                    "client_secret": ["channel-secret-value"]}

    assert push_call[0] == "https://api.line.me/v2/bot/message/push"  # 1人あてのプッシュだけ
    body = json.loads(push_call[1])
    assert body["to"] == USER_ID
    assert len(body["messages"]) == 1 and "[高] 資料作成" in body["messages"][0]["text"]
    assert push_call[2]["Authorization"] == "Bearer short-lived-token"
    assert push_call[2]["X-Line-Retry-Key"] == notify.retry_key_for(TODAY)


def test_一斉送信などの機能は使っていない():
    source = (ROOT / "notify.py").read_text(encoding="utf-8")
    for api in ("broadcast", "multicast", "narrowcast"):
        assert f"/message/{api}" not in source


def test_同じ日の再送キーは同じで_別の日は違う():
    assert notify.retry_key_for(TODAY) == notify.retry_key_for(date(2026, 11, 21))
    assert notify.retry_key_for(TODAY) != notify.retry_key_for(date(2026, 11, 22))


def test_同じ日に送信済みならエラーにせず二重に送らない():
    sheet = sheet_with(row("a", "資料作成", "2026-11-21"))
    line = FakeLine(push_status=409)
    assert run(settings(), TODAY, open_sheet=opener(sheet), post=line) == "already_sent"
    assert len(line.pushes) == 1


@pytest.mark.parametrize("status, word", [(429, "上限"), (400, "HTTP 400"), (500, "HTTP 500")])
def test_送信に失敗したらエラーにする(status, word):
    sheet = sheet_with(row("a", "資料作成", "2026-11-21"))
    with pytest.raises(NotifyError, match=word):
        run(settings(), TODAY, open_sheet=opener(sheet), post=FakeLine(push_status=status))


def test_トークンを発行できなければ送信しない():
    sheet = sheet_with(row("a", "資料作成", "2026-11-21"))
    line = FakeLine(token_status=400)
    with pytest.raises(NotifyError, match="トークン"):
        run(settings(), TODAY, open_sheet=opener(sheet), post=line)
    assert line.pushes == []


def test_確認のみ_DRY_RUN_ではLINEに接続しない():
    sheet = sheet_with(row("a", "資料作成", "2026-11-21"))
    line = FakeLine()
    assert run(settings(dry_run=True), TODAY, open_sheet=opener(sheet), post=line) == "dry_run"
    assert line.calls == []


# ---------- シートは読むだけ ----------


def test_シートには書き込まない():
    sheet = sheet_with(row("a", "資料作成", "2026-11-21"))
    before = [list(r) for r in sheet.rows]
    run(settings(), TODAY, open_sheet=opener(sheet), post=FakeLine())
    assert sheet.rows == before
    assert sheet.calls == []  # append・update・delete はどれも呼ばれていない


def test_見出しが6列だけの古いシートも読める_見出しを書き足さない():
    sheet = FakeWorksheet([BASE_HEADERS, ["a", "古い形式", "", "2026-11-21", "", ""]])
    line = FakeLine()
    assert run(settings(), TODAY, open_sheet=opener(sheet), post=line) == "sent"
    assert sheet.calls == [] and sheet.rows[0] == BASE_HEADERS
    assert "[中] 古い形式" in json.loads(line.pushes[0][1])["messages"][0]["text"]


def test_空のシートなら何もしない():
    assert run(settings(), TODAY, open_sheet=opener(FakeWorksheet([[]])), post=FakeLine()) == "no_targets"


def test_見出しが違うシートは読まずにエラー():
    sheet = FakeWorksheet([["名前", "メモ"], ["x", "y"]])
    with pytest.raises(NotifyError, match="見出し"):
        run(settings(), TODAY, open_sheet=opener(sheet), post=FakeLine())


def test_読み取り専用の範囲で認証する():
    assert notify.READONLY_SCOPES == ["https://www.googleapis.com/auth/spreadsheets.readonly"]


# ---------- ログに件数以外を出さない ----------


def test_ログには件数だけが出て_タイトルや秘密の値は出ない(caplog):
    sheet = sheet_with(row("id-secret-123", "秘密のタイトル", "2026-11-21"), row("b", "古い件", "2026-11-01"))
    with caplog.at_level(logging.DEBUG):
        run(settings(), TODAY, open_sheet=opener(sheet), post=FakeLine())
    log = caplog.text
    assert "今日が期限 1件、期限切れ 1件" in log
    for secret in ("秘密のタイトル", "古い件", "id-secret-123", "秘密の本文", USER_ID, "channel-secret-value",
                   "short-lived-token", "sheet-id"):
        assert secret not in log


def test_想定外のエラーでも中身は出さず失敗として終わる(monkeypatch, caplog):
    monkeypatch.setattr(notify, "load_settings", lambda: (_ for _ in ()).throw(RuntimeError("秘密の詳細")))
    assert notify.main() == 1
    assert "秘密の詳細" not in caplog.text and "RuntimeError" in caplog.text


# ---------- 設定（環境変数） ----------


def env(**overrides):
    base = {"NOTIFY_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}', "SPREADSHEET_ID": "sheet-id",
            "LINE_CHANNEL_ID": "1234567890", "LINE_CHANNEL_SECRET": "s", "LINE_USER_ID": USER_ID,
            "APP_URL": "https://example.streamlit.app", "DRY_RUN": "false"}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def test_DRY_RUNを指定しなければ送信しない側になる():
    assert load_settings(env(DRY_RUN=None)).dry_run is True
    assert load_settings(env(DRY_RUN="False")).dry_run is False
    assert load_settings(env(DRY_RUN="yes")).dry_run is True  # false 以外はすべて「送らない」


@pytest.mark.parametrize("missing", ["NOTIFY_SERVICE_ACCOUNT_JSON", "SPREADSHEET_ID", "LINE_CHANNEL_ID",
                                     "LINE_CHANNEL_SECRET", "LINE_USER_ID"])
def test_送信に必要な設定が欠けていればエラー(missing):
    with pytest.raises(NotifyError, match=missing):
        load_settings(env(**{missing: ""}))


def test_確認のみならLINEの設定はなくてもよい():
    s = load_settings(env(DRY_RUN="true", LINE_CHANNEL_ID=None, LINE_CHANNEL_SECRET=None, LINE_USER_ID=None))
    assert s.dry_run and s.channel_id == ""


@pytest.mark.parametrize("bad", ["C0123456789abcdef0123456789abcdef", "R" + "0" * 32, "U123", "Uxyz" + "0" * 29])
def test_個人のユーザーID以外には送らない(bad):
    with pytest.raises(NotifyError, match="LINE_USER_ID"):
        load_settings(env(LINE_USER_ID=bad))


def test_アプリのURLはhttpsだけ():
    with pytest.raises(NotifyError, match="APP_URL"):
        load_settings(env(APP_URL="http://example.com"))
    assert load_settings(env(APP_URL=None)).app_url == ""


# ---------- 定期実行の設定（.github/workflows/notify.yml） ----------


WORKFLOW = (ROOT / ".github" / "workflows" / "notify.yml").read_text(encoding="utf-8")


def test_毎朝7時_日本時間_に動く():
    assert 'cron: "0 22 * * *"' in WORKFLOW  # UTC 22:00 = 日本時間 7:00


def test_動くきっかけは定期実行と手動実行だけ():
    on_block = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    triggers = [line.strip().rstrip(":").split(":")[0] for line in on_block.splitlines()
                if line.startswith("  ") and not line.startswith("   ")]
    assert triggers == ["schedule", "workflow_dispatch"]
    for risky in ("pull_request", "push:", "issue", "workflow_run", "repository_dispatch"):
        assert risky not in on_block


def test_権限は読むだけ_二重実行を防ぐ_秘密の値は書いていない():
    assert "permissions:\n  contents: read" in WORKFLOW
    assert "concurrency:" in WORKFLOW
    assert "github.repository == 'mshibu-web/streamlit-todo-app'" in WORKFLOW
    for name in ("NOTIFY_SERVICE_ACCOUNT_JSON", "SPREADSHEET_ID", "LINE_CHANNEL_ID", "LINE_CHANNEL_SECRET", "LINE_USER_ID"):
        assert f"${{{{ secrets.{name} }}}}" in WORKFLOW


def test_手動実行は既定で送信しない():
    assert "default: false" in WORKFLOW
    assert "DRY_RUN: ${{ (github.event_name == 'schedule' || inputs.send) && 'false' || 'true' }}" in WORKFLOW
