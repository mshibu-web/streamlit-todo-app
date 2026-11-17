"""Google スプレッドシートとの読み書きだけを担当するモジュール。

シートの構成（要件定義書 6章）
    1行目   : 見出し行  id, title, content, due_date, created_at, updated_at
    2行目以降: Todo データ（1行 = 1件）
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import gspread
from gspread.utils import ValueInputOption

from validators import MAX_TODO_COUNT, clean_text

logger = logging.getLogger(__name__)

HEADERS = ["id", "title", "content", "due_date", "created_at", "updated_at"]

# スプレッドシートの読み書きだけを許可する（Google ドライブ全体へのアクセスは要求しない）
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

JST = timezone(timedelta(hours=9), "JST")
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 入力値をそのまま文字列として保存する（"=1+1" などが数式として実行されないようにする）
RAW = ValueInputOption.raw


class TodoError(Exception):
    """利用者に表示してよいメッセージを持つエラーの基本クラス。"""


class SheetFormatError(TodoError):
    def __init__(self) -> None:
        super().__init__("データ形式が正しくありません。管理者に連絡してください")


class TodoNotFoundError(TodoError):
    def __init__(self) -> None:
        super().__init__("対象のTodoが見つかりません（削除された可能性があります）")


class TodoLimitError(TodoError):
    def __init__(self, max_count: int) -> None:
        super().__init__(f"登録件数の上限（{max_count}件）に達しているため、登録できません")


@dataclass(frozen=True)
class Todo:
    id: str
    title: str
    content: str
    due_date: date
    created_at: str
    updated_at: str

    def to_row(self) -> list[str]:
        """スプレッドシートの1行分の値に変換する。"""
        return [
            self.id,
            self.title,
            self.content,
            self.due_date.strftime(DATE_FORMAT),
            self.created_at,
            self.updated_at,
        ]


def today_jst() -> date:
    """日本時間の今日の日付（公開サーバーは米国にあるため、日本時間に合わせる）。"""
    return datetime.now(JST).date()


def now_jst_text() -> str:
    return datetime.now(JST).strftime(DATETIME_FORMAT)


def open_worksheet(service_account_info: dict, spreadsheet_id: str, worksheet_name: str):
    """サービスアカウントで認証し、対象のシート（タブ）を開く。"""
    client = gspread.service_account_from_dict(dict(service_account_info), scopes=SCOPES)
    return client.open_by_key(spreadsheet_id).worksheet(worksheet_name)


def is_rate_limit_error(exc: Exception) -> bool:
    """Google API の回数制限（HTTP 429）によるエラーかどうか。"""
    if not isinstance(exc, gspread.exceptions.APIError):
        return False
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


class TodoRepository:
    """Todo をスプレッドシートに保存・取得するクラス。"""

    def __init__(self, worksheet, max_count: int = MAX_TODO_COUNT, retry_wait_seconds: float = 2.0) -> None:
        self.worksheet = worksheet
        self.max_count = max_count
        self.retry_wait_seconds = retry_wait_seconds

    # ---------- 内部で使う処理 ----------

    def _call(self, func, *args, **kwargs):
        """Google API を呼び出す。回数制限に当たった場合は少し待って1回だけ再試行する。"""
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as exc:
            if not is_rate_limit_error(exc):
                raise
            logger.warning("Google API の回数制限に達したため再試行します")
            time.sleep(self.retry_wait_seconds)
            return func(*args, **kwargs)

    def _read_data_rows(self) -> list[list[str]]:
        """見出し行を確認し、2行目以降のデータを返す。"""
        values = self._call(self.worksheet.get_all_values)

        # まったく空のシートなら、見出し行を書き込んで使える状態にする
        # （本物の API は空のシートでも [] ではなく [[]] を返すことがあるため、中身で判定する）
        if all(not cell.strip() for row in values for cell in row):
            self._call(self.worksheet.update, values=[HEADERS], range_name="A1:F1", value_input_option=RAW)
            return []

        header = [cell.strip() for cell in values[0][: len(HEADERS)]]
        if header != HEADERS:
            logger.error("見出し行が想定と異なります: %s", values[0])
            raise SheetFormatError()

        return values[1:]

    @staticmethod
    def _row_to_todo(row: list[str]) -> Todo | None:
        """1行分の値を Todo に変換する。形式が正しくない行は None を返す。"""
        cells = (list(row) + [""] * len(HEADERS))[: len(HEADERS)]
        todo_id, title, content, due_text, created_at, updated_at = (cell.strip() for cell in cells)
        if not todo_id or not title:
            return None
        try:
            due_date = datetime.strptime(due_text, DATE_FORMAT).date()
        except ValueError:
            return None
        return Todo(todo_id, title, content, due_date, created_at, updated_at)

    @staticmethod
    def _is_blank(row: list[str]) -> bool:
        return all(not cell.strip() for cell in row)

    # ---------- 外から使う処理 ----------

    def list_todos(self) -> tuple[list[Todo], int]:
        """Todo の一覧を期日の昇順で返す（Q12）。

        戻り値: (Todo の一覧, 形式が正しくなく読み飛ばした行の数)
        """
        todos: list[Todo] = []
        skipped = 0
        for row in self._read_data_rows():
            if self._is_blank(row):
                continue
            todo = self._row_to_todo(row)
            if todo is None:
                skipped += 1
                continue
            todos.append(todo)

        # 期日が近い順。同じ期日なら登録が古い順
        todos.sort(key=lambda t: (t.due_date, t.created_at))
        return todos, skipped

    def add_todo(self, title: str, content: str, due_date: date) -> Todo:
        """Todo を1件追加する。"""
        rows = self._read_data_rows()
        count = sum(1 for row in rows if not self._is_blank(row))
        if count >= self.max_count:
            raise TodoLimitError(self.max_count)

        now = now_jst_text()
        todo = Todo(
            id=uuid.uuid4().hex,
            title=clean_text(title),
            content=clean_text(content),
            due_date=due_date,
            created_at=now,
            updated_at=now,
        )
        self._call(self.worksheet.append_row, todo.to_row(), value_input_option=RAW, table_range="A1")
        return todo

    def update_todo(self, todo_id: str, title: str, content: str, due_date: date) -> Todo:
        """ID で指定した Todo の内容を上書きする（ID と作成日時は変えない）。"""
        rows = self._read_data_rows()
        for index, row in enumerate(rows):
            if row and row[0].strip() == todo_id:
                row_number = index + 2  # 1行目は見出し行のため +2
                created_at = row[4] if len(row) > 4 else ""
                todo = Todo(
                    id=todo_id,
                    title=clean_text(title),
                    content=clean_text(content),
                    due_date=due_date,
                    created_at=created_at,
                    updated_at=now_jst_text(),
                )
                self._call(
                    self.worksheet.update,
                    values=[todo.to_row()],
                    range_name=f"A{row_number}:F{row_number}",
                    value_input_option=RAW,
                )
                return todo
        raise TodoNotFoundError()
