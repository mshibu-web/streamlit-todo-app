"""T12：許可リストの判定（Streamlit を使わない）。"""

import pytest

from auth import allowed_email_set, auth_settings_ready, is_allowed, is_email_verified

OWNER = "owner@example.com"


def user(email=OWNER, verified=True, logged_in=True):
    return {"is_logged_in": logged_in, "email": email, "email_verified": verified}


def test_許可リストのメールだけが通る():
    allowed = allowed_email_set([OWNER])
    assert is_allowed(user(), allowed)
    assert not is_allowed(user("someone@example.com"), allowed)


@pytest.mark.parametrize("email", ["Owner@Example.com", "OWNER@EXAMPLE.COM", "  owner@example.com "])
def test_大文字小文字や前後の空白は区別しない(email):
    assert is_allowed(user(email), allowed_email_set([OWNER]))
    assert is_allowed(user(), allowed_email_set([email]))


@pytest.mark.parametrize("verified", [False, None, "false", "", 1])
def test_メールアドレスが確認ずみでなければ通らない(verified):
    assert not is_allowed(user(verified=verified), allowed_email_set([OWNER]))


def test_確認ずみは真偽値と文字列trueの両方を受け付ける():
    assert is_email_verified(True)
    assert is_email_verified("true")
    assert is_email_verified("True")


@pytest.mark.parametrize("raw", [None, [], "", [""], ["not-an-email"], 123, {}])
def test_許可リストが空や未設定や不正なら誰も通らない(raw):
    allowed = allowed_email_set(raw)
    assert allowed == frozenset() or "@" not in "".join(allowed)
    assert not is_allowed(user(), allowed)


def test_許可リストに文字列1つだけが書かれていても使える():
    assert is_allowed(user(), allowed_email_set(OWNER))


@pytest.mark.parametrize(
    "info",
    [
        {"email": OWNER, "email_verified": True},  # is_logged_in が無い
        user(logged_in=False),
        user(logged_in="true"),  # 真偽値の True 以外は認めない
        user(email=None),
        user(email=""),
    ],
)
def test_ログインしていない状態やメールが無い場合は通らない(info):
    assert not is_allowed(info, allowed_email_set([OWNER]))


FULL_AUTH = {
    "redirect_uri": "http://localhost:8501/oauth2callback",
    "cookie_secret": "x",
    "client_id": "x",
    "client_secret": "x",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


def test_ログイン設定がそろっていれば準備完了():
    assert auth_settings_ready(FULL_AUTH)


@pytest.mark.parametrize("missing", list(FULL_AUTH))
def test_ログイン設定が1つでも欠けたり空なら準備未完了(missing):
    without = {k: v for k, v in FULL_AUTH.items() if k != missing}
    blank = {**FULL_AUTH, missing: "  "}
    assert not auth_settings_ready(without)
    assert not auth_settings_ready(blank)
    assert not auth_settings_ready(None)
