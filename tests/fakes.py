"""テスト用の「偽物のシート」。本物の Google スプレッドシートには接続しない。"""

import re
from types import SimpleNamespace

from todo_repository import HEADERS


def _column_index(letters: str) -> int:
    """列の記号（A, B, ... H）を 0 から始まる番号に変える。"""
    return ord(letters) - ord("A")


class FakeWorksheet:
    def __init__(self, rows=None):
        self.rows = [list(r) for r in rows] if rows is not None else [list(HEADERS)]
        self.calls = []  # (操作名, value_input_option) の記録
        self.updated_ranges = []  # update で書き込んだ範囲の記録

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_row(self, values, value_input_option=None, table_range=None):
        self.calls.append(("append", value_input_option))
        self.rows.append([str(v) for v in values])

    def update(self, values=None, range_name=None, value_input_option=None, **kwargs):
        """"A2:H2" や "G1:H1" のような1行分の範囲に書き込む。"""
        self.calls.append(("update", value_input_option))
        self.updated_ranges.append(range_name)
        start_col, row_text, end_col, end_row_text = re.match(r"([A-Z])(\d+):([A-Z])(\d+)$", range_name).groups()
        assert row_text == end_row_text, "1行分の範囲だけを想定している"
        row_number = int(row_text)
        start, end = _column_index(start_col), _column_index(end_col)
        assert len(values[0]) == end - start + 1, "範囲と値の数が合っていない"

        while len(self.rows) < row_number:
            self.rows.append([])
        row = self.rows[row_number - 1]
        while len(row) <= end:
            row.append("")
        for offset, value in enumerate(values[0]):
            row[start + offset] = str(value)

    def acell(self, label):
        self.calls.append(("acell", None))
        col_letter, row_text = re.match(r"([A-Z])(\d+)$", label).groups()
        row_index, col_index = int(row_text) - 1, _column_index(col_letter)
        value = ""
        if row_index < len(self.rows) and col_index < len(self.rows[row_index]):
            value = self.rows[row_index][col_index]
        return SimpleNamespace(value=value)

    def delete_rows(self, start_index, end_index=None):
        self.calls.append(("delete", None))
        del self.rows[start_index - 1 : (end_index or start_index)]
