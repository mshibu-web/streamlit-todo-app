"""T1：入力チェックのテスト"""

from datetime import date

from validators import CONTENT_MAX_LENGTH, TITLE_MAX_LENGTH, validate_todo

DUE = date(2026, 11, 20)


def test_正しい入力ならエラーなし():
    assert validate_todo("資料作成", "会議用", DUE) == []


def test_内容は空欄でもよい():
    assert validate_todo("資料作成", "", DUE) == []
    assert validate_todo("資料作成", None, DUE) == []


def test_タイトル空欄はエラー():
    assert validate_todo("", "", DUE) == ["タイトルを入力してください"]


def test_タイトルが空白だけならエラー():
    assert validate_todo("　 \t", "", DUE) == ["タイトルを入力してください"]


def test_タイトルは上限ちょうどならOK_1文字超えるとエラー():
    assert validate_todo("あ" * TITLE_MAX_LENGTH, "", DUE) == []
    assert validate_todo("あ" * (TITLE_MAX_LENGTH + 1), "", DUE) == ["タイトルは50文字以内で入力してください"]


def test_内容は上限ちょうどならOK_1文字超えるとエラー():
    assert validate_todo("t", "あ" * CONTENT_MAX_LENGTH, DUE) == []
    assert validate_todo("t", "あ" * (CONTENT_MAX_LENGTH + 1), DUE) == ["内容は500文字以内で入力してください"]


def test_期日未入力はエラー():
    assert validate_todo("t", "", None) == ["期日を選択してください"]


def test_過去日も登録できる():
    assert validate_todo("t", "", date(2000, 1, 1)) == []


def test_複数のエラーをまとめて返す():
    assert validate_todo("", "あ" * 501, None) == [
        "タイトルを入力してください",
        "内容は500文字以内で入力してください",
        "期日を選択してください",
    ]
