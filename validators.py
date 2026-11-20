"""入力チェックを行うモジュール。

Streamlit や Google スプレッドシートには依存しない、ただの関数だけを置いています。
そのため、自動テストで簡単に動作確認できます。
"""

from datetime import date

# 入力の上限（要件定義書 7.1 / Q5）
TITLE_MAX_LENGTH = 50
CONTENT_MAX_LENGTH = 500
MAX_TODO_COUNT = 200

# 優先度（要件定義書 5.6）。高い順に並べている
PRIORITIES = ("高", "中", "低")
DEFAULT_PRIORITY = "中"


def clean_text(text: str | None) -> str:
    """前後の空白を取り除いた文字列を返す（None は空文字にする）。"""
    return (text or "").strip()


def normalize_priority(value: str | None) -> str:
    """シートから読んだ優先度を整える。空欄や「高・中・低」以外の値は「中」として扱う。"""
    value = clean_text(value)
    return value if value in PRIORITIES else DEFAULT_PRIORITY


def validate_todo(
    title: str | None,
    content: str | None,
    due_date: date | None,
    priority: str | None = DEFAULT_PRIORITY,
) -> list[str]:
    """Todo の入力内容をチェックし、エラーメッセージの一覧を返す。

    問題がなければ空のリストを返す。
    """
    errors: list[str] = []

    title = clean_text(title)
    content = clean_text(content)

    # タイトル：必須・50文字以内
    if not title:
        errors.append("タイトルを入力してください")
    elif len(title) > TITLE_MAX_LENGTH:
        errors.append(f"タイトルは{TITLE_MAX_LENGTH}文字以内で入力してください")

    # 内容：任意・500文字以内
    if len(content) > CONTENT_MAX_LENGTH:
        errors.append(f"内容は{CONTENT_MAX_LENGTH}文字以内で入力してください")

    # 期日：必須（過去日も許可する / Q6）
    if due_date is None:
        errors.append("期日を選択してください")
    elif not isinstance(due_date, date):
        errors.append("期日の形式が正しくありません")

    # 優先度：高・中・低のどれか
    if priority not in PRIORITIES:
        errors.append("優先度を選択してください")

    return errors
