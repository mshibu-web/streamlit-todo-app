"""テスト用の「偽物のシート」。本物の Google スプレッドシートには接続しない。"""

import re

from todo_repository import HEADERS


class FakeWorksheet:
    def __init__(self, rows=None):
        self.rows = [list(r) for r in rows] if rows is not None else [list(HEADERS)]
        self.calls = []  # (操作名, value_input_option) の記録

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_row(self, values, value_input_option=None, table_range=None):
        self.calls.append(("append", value_input_option))
        self.rows.append([str(v) for v in values])

    def update(self, values=None, range_name=None, value_input_option=None, **kwargs):
        self.calls.append(("update", value_input_option))
        row_number = int(re.match(r"A(\d+):F\1$", range_name).group(1))
        while len(self.rows) < row_number:
            self.rows.append([""] * len(HEADERS))
        self.rows[row_number - 1] = [str(v) for v in values[0]]
