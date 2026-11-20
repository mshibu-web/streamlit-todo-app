"""Google スプレッドシートとの読み書きだけを担当するモジュール。

シートの構成（要件定義書 6章）
    1行目   : 見出し行  id, title, content, due_date, created_at, updated_at, completed_at, priority
    2行目以降: Todo データ（1行 = 1件）

第3版までのシートは A〜F 列（6列）だけ。G・H 列の見出しが空なら、見出しだけを自動で書き足す
（2行目以降のデータには触れない。要件定義書 6.3）。
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import gspread
from gspread.utils import ValueInputOption

from validators import DEFAULT_PRIORITY, MAX_TODO_COUNT, PRIORITIES, clean_text, normalize_priority

logger = logging.getLogger(__name__)

# 第3版からある列（A〜F）と、第4版で追加した列（G・H）
BASE_HEADERS = ["id", "title", "content", "due_date", "created_at", "updated_at"]
EXTRA_HEADERS = ["completed_at", "priority"]
HEADERS = BASE_HEADERS + EXTRA_HEADERS
LAST_COLUMN = "H"  # HEADERS の最後の列

# スプレッドシートの読み書きだけを許可する（Google ドライブ全体へのアクセスは要求しない）
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

JST = timezone(timedelta(hours=9), "JST")
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 入力値をそのまま文字列として保存する（"=1+1" などが数式として実行されないようにする）
RAW = ValueInputOption.raw

# 並び順（要件定義書 5.3）
SORT_BY_DUE = "due"
SORT_BY_PRIORITY = "priority"
PRIORITY_RANK = {name: rank for rank, name in enumerate(PRIORITIES)}  # 高=0, 中=1, 低=2


class TodoError(Exception):
    """利用者に表示してよいメッセージを持つエラーの基本クラス。"""


class SheetFormatError(TodoError):
    def __init__(self) -> None:
        super().__init__("データ形式が正しくありません。管理者に連絡してください")


class TodoNotFoundError(TodoError):
    def __init__(self) -> None:
        super().__init__("対象のToDoが見つかりません（削除された可能性があります）")


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
    completed_at: str = ""  # 空欄なら未完了
    priority: str = DEFAULT_PRIORITY

    @property
    def is_completed(self) -> bool:
        return bool(self.completed_at)

    def to_row(self) -> list[str]:
        """スプレッドシートの1行分の値に変換する。"""
        return [
            self.id,
            self.title,
            self.content,
            self.due_date.strftime(DATE_FORMAT),
            self.created_at,
            self.updated_at,
            self.completed_at,
            self.priority,
        ]


def today_jst() -> date:
    """日本時間の今日の日付（公開サーバーは米国にあるため、日本時間に合わせる）。"""
    return datetime.now(JST).date()


def now_jst_text() -> str:
    return datetime.now(JST).strftime(DATETIME_FORMAT)


def sort_todos(todos: list[Todo], order: str = SORT_BY_DUE) -> list[Todo]:
    """Todo を並べ替えた新しいリストを返す（要件定義書 5.3）。

    期日順  : 期日 → 優先度 → 登録が古い順
    優先度順: 優先度 → 期日 → 登録が古い順
    """
    if order == SORT_BY_PRIORITY:
        key = lambda t: (PRIORITY_RANK[t.priority], t.due_date, t.created_at)  # noqa: E731
    else:
        key = lambda t: (t.due_date, PRIORITY_RANK[t.priority], t.created_at)  # noqa: E731
    return sorted(todos, key=key)


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
            self._call(
                self.worksheet.update,
                values=[HEADERS],
                range_name=f"A1:{LAST_COLUMN}1",
                value_input_option=RAW,
            )
            return []

        header = [cell.strip() for cell in values[0]] + [""] * len(HEADERS)

        # A〜F 列は第3版と完全に同じでなければ、データを守るため何もしない
        if header[: len(BASE_HEADERS)] != BASE_HEADERS:
            logger.error("見出し行が想定と異なります")
            raise SheetFormatError()

        # G・H 列：空欄なら見出しを書き足す。違う値が入っていたら何もしない
        extra = header[len(BASE_HEADERS) : len(HEADERS)]
        if extra != EXTRA_HEADERS:
            if any(cell and cell != expected for cell, expected in zip(extra, EXTRA_HEADERS)):
                logger.error("見出し行（G・H列）が想定と異なります")
                raise SheetFormatError()
            # 1行目の G1:H1 だけを書き込む（データの行には触れない）
            self._call(
                self.worksheet.update,
                values=[EXTRA_HEADERS],
                range_name=f"G1:{LAST_COLUMN}1",
                value_input_option=RAW,
            )
            logger.info("見出し行に completed_at・priority を追加しました")

        return values[1:]

    @staticmethod
    def _row_to_todo(row: list[str]) -> Todo | None:
        """1行分の値を Todo に変換する。形式が正しくない行は None を返す。"""
        cells = (list(row) + [""] * len(HEADERS))[: len(HEADERS)]
        todo_id, title, content, due_text, created_at, updated_at, completed_at, priority = (
            cell.strip() for cell in cells
        )
        if not todo_id or not title:
            return None
        try:
            due_date = datetime.strptime(due_text, DATE_FORMAT).date()
        except ValueError:
            return None
        return Todo(
            todo_id,
            title,
            content,
            due_date,
            created_at,
            updated_at,
            completed_at,
            normalize_priority(priority),
        )

    @staticmethod
    def _is_blank(row: list[str]) -> bool:
        return all(not cell.strip() for cell in row)

    def _find_row(self, todo_id: str) -> tuple[int, Todo]:
        """ID で行を探し、(シート上の行番号, その行の Todo) を返す。見つからなければエラー。"""
        for index, row in enumerate(self._read_data_rows()):
            if row and row[0].strip() == todo_id:
                todo = self._row_to_todo(row)
                if todo is None:
                    break  # 形式が正しくない行は操作しない
                return index + 2, todo  # 1行目は見出し行のため +2
        raise TodoNotFoundError()

    # ---------- 外から使う処理 ----------

    def list_todos(self, order: str = SORT_BY_DUE) -> tuple[list[Todo], int]:
        """Todo の一覧を返す（並び順は sort_todos を参照）。

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
        return sort_todos(todos, order), skipped

    def add_todo(self, title: str, content: str, due_date: date, priority: str = DEFAULT_PRIORITY) -> Todo:
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
            completed_at="",
            priority=normalize_priority(priority),
        )
        self._call(self.worksheet.append_row, todo.to_row(), value_input_option=RAW, table_range="A1")
        return todo

    def update_todo(
        self,
        todo_id: str,
        title: str,
        content: str,
        due_date: date,
        priority: str = DEFAULT_PRIORITY,
    ) -> Todo:
        """ID で指定した Todo の内容を上書きする（ID・作成日時・完了日時は変えない）。"""
        row_number, current = self._find_row(todo_id)
        todo = Todo(
            id=todo_id,
            title=clean_text(title),
            content=clean_text(content),
            due_date=due_date,
            created_at=current.created_at,
            updated_at=now_jst_text(),
            completed_at=current.completed_at,
            priority=normalize_priority(priority),
        )
        self._call(
            self.worksheet.update,
            values=[todo.to_row()],
            range_name=f"A{row_number}:{LAST_COLUMN}{row_number}",
            value_input_option=RAW,
        )
        return todo

    def set_completed(self, todo_id: str, completed: bool) -> None:
        """完了・未完了を切り替える。更新日時（F列）と完了日時（G列）だけを書き換える。"""
        row_number, _ = self._find_row(todo_id)
        now = now_jst_text()
        self._call(
            self.worksheet.update,
            values=[[now, now if completed else ""]],
            range_name=f"F{row_number}:G{row_number}",
            value_input_option=RAW,
        )

    def delete_todo(self, todo_id: str) -> None:
        """ID で指定した Todo の行を削除する。

        削除の直前に、その行の ID をもう一度読み直して確かめる。
        読んでから削除するまでの間に行がずれていたら、別の行を消さないよう何もしない。
        """
        row_number, _ = self._find_row(todo_id)
        cell = self._call(self.worksheet.acell, f"A{row_number}")
        if (cell.value or "").strip() != todo_id:
            logger.warning("削除の直前に行の位置が変わっていたため、削除を中止しました")
            raise TodoNotFoundError()
        self._call(self.worksheet.delete_rows, row_number)
