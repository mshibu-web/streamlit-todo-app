"""LINE リマインド通知（要件定義書 第6版 5.7・9.4）。GitHub Actions から毎朝実行する。

処理の流れ
    ① 通知専用サービスアカウントで、スプレッドシートを「読むだけ」で開く
    ② 日本時間の今日が期限の未完了ToDoと、期限切れの未完了ToDoを選ぶ
    ③ 0件なら何もせず終わる（LINE には一切接続しない）
    ④ 1件以上なら、本人の LINE ユーザーID だけに1通送る（push message）

安全のための決まり
    - シートには一切書き込まない（読み取り専用の権限・範囲で開く）
    - 送り先は LINE_USER_ID の1人だけ。全員への一斉送信（broadcast など）の機能は使わない
    - LINE のトークンは実行のたびに発行する短期トークン（15分で無効）
    - 同じ日の通知は、再送しても1回しか届かない（X-Line-Retry-Key）
    - ログには件数だけを出す（タイトル・ID・メールアドレス・トークンは出さない）
    - DRY_RUN が有効なら、LINE には接続せず件数だけを表示する

環境変数（GitHub Actions の Secrets から渡す。リポジトリには書かない）
    NOTIFY_SERVICE_ACCOUNT_JSON  通知専用サービスアカウントの鍵（JSON の中身）
    SPREADSHEET_ID               読むスプレッドシートのID
    WORKSHEET_NAME               タブ名（省略時は todos）
    LINE_CHANNEL_ID              Messaging API チャネルのID
    LINE_CHANNEL_SECRET          Messaging API チャネルのシークレット
    LINE_USER_ID                 通知先（本人）の LINE ユーザーID
    APP_URL                      通知の最後に付けるアプリのURL（省略可）
    DRY_RUN                      "true" なら送信しない（省略時は送信しない＝安全側）
"""

import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date

from todo_repository import BASE_HEADERS, PRIORITY_RANK, Todo, TodoRepository, today_jst

logger = logging.getLogger("notify")

READONLY_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
LINE_TOKEN_URL = "https://api.line.me/oauth2/v3/token"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
MAX_ITEMS_PER_SECTION = 10  # 1つの区分に表示する最大件数（超えた分は「他N件」）
MAX_MESSAGE_LENGTH = 5000  # LINE のテキストメッセージの上限文字数
USER_ID_PATTERN = re.compile(r"^U[0-9a-f]{32}$")  # 個人の LINE ユーザーID の形（グループ等は不可）
RETRY_KEY_NAMESPACE = uuid.UUID("7d8f3a52-1c4e-4f0b-9a6e-2b5c8d9e0f13")  # この通知専用の固定値（秘密ではない）
WEEKDAYS = "月火水木金土日"


class NotifyError(Exception):
    """通知に失敗した（GitHub Actions を「失敗」にして本人にメールで知らせる）。"""


@dataclass(frozen=True)
class Targets:
    due_today: list[Todo]
    overdue: list[Todo]

    @property
    def count(self) -> int:
        return len(self.due_today) + len(self.overdue)


# ---------- ① シートを読む（読むだけ） ----------


def open_worksheet_readonly(service_account_info: dict, spreadsheet_id: str, worksheet_name: str):
    """読み取り専用の範囲で認証してシートを開く。"""
    import gspread  # テストでは使わないため、ここで読み込む

    client = gspread.service_account_from_dict(dict(service_account_info), scopes=READONLY_SCOPES)
    return client.open_by_key(spreadsheet_id).worksheet(worksheet_name)


def read_todos(worksheet) -> list[Todo]:
    """シートの全行を Todo に変換する。シートには書き込まない（見出しの追加もしない）。"""
    values = worksheet.get_all_values()
    if all(not cell.strip() for row in values for cell in row):
        return []
    header = [cell.strip() for cell in values[0]]
    if header[: len(BASE_HEADERS)] != BASE_HEADERS:
        raise NotifyError("見出し行が想定と異なります")
    todos = [TodoRepository._row_to_todo(row) for row in values[1:]]
    return [t for t in todos if t is not None]


# ---------- ② 通知するToDoを選ぶ ----------


def select_targets(todos: list[Todo], today: date) -> Targets:
    """今日が期限・期限切れの未完了ToDoを選ぶ。完了済みと、明日以降のものは選ばない。"""
    open_todos = [t for t in todos if not t.is_completed]
    due_today = sorted((t for t in open_todos if t.due_date == today), key=lambda t: PRIORITY_RANK[t.priority])
    overdue = sorted(
        (t for t in open_todos if t.due_date < today),
        key=lambda t: (t.due_date, PRIORITY_RANK[t.priority]),  # 古いものから
    )
    return Targets(due_today, overdue)


# ---------- ③ 通知の文面を作る ----------


def short_date(day: date) -> str:
    return f"{day.month}/{day.day}"


def build_message(targets: Targets, today: date, app_url: str = "") -> str:
    lines = [f"【ToDoリマインド】{short_date(today)}（{WEEKDAYS[today.weekday()]}）"]

    def section(title: str, todos: list[Todo], describe) -> None:
        if not todos:
            return
        lines.append("")
        lines.append(f"■ {title}（{len(todos)}件）")
        for todo in todos[:MAX_ITEMS_PER_SECTION]:
            lines.append(describe(todo))
        if len(todos) > MAX_ITEMS_PER_SECTION:
            lines.append(f"…他{len(todos) - MAX_ITEMS_PER_SECTION}件")

    section("今日が期限", targets.due_today, lambda t: f"[{t.priority}] {t.title}")
    section(
        "期限切れ",
        targets.overdue,
        lambda t: f"[{t.priority}] {t.title}（{short_date(t.due_date)}・{(today - t.due_date).days}日超過）",
    )
    if app_url:
        lines += ["", f"▶ ToDoアプリを開く", app_url]
    text = "\n".join(lines)
    if len(text) > MAX_MESSAGE_LENGTH:  # 念のため（タイトルは50字まで・各区分10件までなので通常は届かない）
        text = text[: MAX_MESSAGE_LENGTH - 1] + "…"
    return text


# ---------- ④ LINE に送る ----------


def http_post(url: str, data: bytes, headers: dict) -> tuple[int, bytes]:
    """POST して (ステータス, 本文) を返す。テストではこの関数を差し替える。"""
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def issue_short_lived_token(channel_id: str, channel_secret: str, post=http_post) -> str:
    """短期のチャネルアクセストークン（15分で無効）を発行する。"""
    body = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": channel_id, "client_secret": channel_secret}
    ).encode()
    status, payload = post(LINE_TOKEN_URL, body, {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        raise NotifyError(f"LINE のトークン発行に失敗しました（HTTP {status}）")
    token = json.loads(payload).get("access_token", "")
    if not token:
        raise NotifyError("LINE のトークンを受け取れませんでした")
    return token


def retry_key_for(today: date) -> str:
    """その日の通知に固定の再送キー。同じ日に何度送っても、LINE は1回しか届けない（24時間有効）。"""
    return str(uuid.uuid5(RETRY_KEY_NAMESPACE, f"todo-reminder-{today.isoformat()}"))


def push_to_user(token: str, user_id: str, text: str, retry_key: str, post=http_post) -> bool:
    """本人1人だけに送る。送った（または同じ日の通知を送り済み）なら True。"""
    body = json.dumps({"to": user_id, "messages": [{"type": "text", "text": text}]}, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Authorization": f"Bearer {token}",
        "X-Line-Retry-Key": retry_key,
    }
    status, _ = post(LINE_PUSH_URL, body, headers)
    if status == 200:
        return True
    if status == 409:  # 同じ再送キーで受付済み（今日の分はもう送ってある）
        logger.info("今日の通知は送信済みのため、もう一度は送りませんでした")
        return False
    if status == 429:
        raise NotifyError("LINE の送信上限（無料プランの月200通など）に達しているため送れませんでした（HTTP 429）")
    raise NotifyError(f"LINE への送信に失敗しました（HTTP {status}）")


# ---------- 全体の流れ ----------


@dataclass(frozen=True)
class Settings:
    service_account_info: dict
    spreadsheet_id: str
    worksheet_name: str
    channel_id: str
    channel_secret: str
    user_id: str
    app_url: str
    dry_run: bool


def load_settings(env=os.environ) -> Settings:
    dry_run = env.get("DRY_RUN", "true").strip().lower() != "false"  # 明示的に false のときだけ送る
    required = ["NOTIFY_SERVICE_ACCOUNT_JSON", "SPREADSHEET_ID"]
    if not dry_run:
        required += ["LINE_CHANNEL_ID", "LINE_CHANNEL_SECRET", "LINE_USER_ID"]
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise NotifyError(f"設定が不足しています: {', '.join(missing)}")
    try:
        service_account_info = json.loads(env["NOTIFY_SERVICE_ACCOUNT_JSON"])
    except json.JSONDecodeError:
        raise NotifyError("NOTIFY_SERVICE_ACCOUNT_JSON の形式が正しくありません") from None
    user_id = env.get("LINE_USER_ID", "").strip()
    if not dry_run and not USER_ID_PATTERN.match(user_id):
        raise NotifyError("LINE_USER_ID の形式が正しくありません（個人のユーザーIDだけに送れます）")
    app_url = env.get("APP_URL", "").strip()
    if app_url and not app_url.startswith("https://"):
        raise NotifyError("APP_URL は https:// で始まる必要があります")
    return Settings(
        service_account_info=service_account_info,
        spreadsheet_id=env["SPREADSHEET_ID"].strip(),
        worksheet_name=env.get("WORKSHEET_NAME", "").strip() or "todos",
        channel_id=env.get("LINE_CHANNEL_ID", "").strip(),
        channel_secret=env.get("LINE_CHANNEL_SECRET", "").strip(),
        user_id=user_id,
        app_url=app_url,
        dry_run=dry_run,
    )


def run(settings: Settings, today: date, open_sheet=open_worksheet_readonly, post=http_post) -> str:
    """通知を1回行い、結果（"dry_run" / "no_targets" / "sent" / "already_sent"）を返す。"""
    worksheet = open_sheet(settings.service_account_info, settings.spreadsheet_id, settings.worksheet_name)
    targets = select_targets(read_todos(worksheet), today)
    logger.info("通知対象：今日が期限 %d件、期限切れ %d件", len(targets.due_today), len(targets.overdue))

    if targets.count == 0:
        logger.info("通知対象がないため、送信しませんでした")
        return "no_targets"
    text = build_message(targets, today, settings.app_url)
    if settings.dry_run:
        logger.info("確認のみ（DRY_RUN）のため、送信しませんでした（文面 %d文字）", len(text))
        return "dry_run"

    token = issue_short_lived_token(settings.channel_id, settings.channel_secret, post=post)
    sent = push_to_user(token, settings.user_id, text, retry_key_for(today), post=post)
    if sent:
        logger.info("LINE に1通送信しました")
        return "sent"
    return "already_sent"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run(load_settings(), today_jst())
    except NotifyError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # 想定外のエラー：中身（個人情報を含む可能性）は出さず、種類だけを出す
        logger.error("想定外のエラーで通知を中止しました（%s）", type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
