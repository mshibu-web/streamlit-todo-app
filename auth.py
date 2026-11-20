"""ログインと許可リストの判定（要件定義書 5.8・8.2）。

Streamlit に依存しない、ただの関数だけを置いている（自動テストで確かめやすくするため）。

- Googleログイン：「この人は誰か」を Google に確かめてもらう（Streamlit の st.login が担当）
- 許可リスト   ：「この人はこのアプリを使ってよいか」をアプリが判断する（このモジュール）

安全のため、迷ったら「使わせない」側に倒す。
  - 許可リストが未設定・空 → 誰も使えない
  - Google がメールアドレスを確認ずみ（email_verified）でない → 使えない
"""

from collections.abc import Iterable, Mapping
from typing import Any

# Google のログイン設定（OpenID Connect）の場所。Google 公式の固定のURL
GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

# [auth] に必ず必要な項目（Streamlit のログイン機能が使う）
REQUIRED_AUTH_KEYS = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")


def normalize_email(email: Any) -> str:
    """メールアドレスを比べやすい形にする（前後の空白を取り、小文字にする）。"""
    return email.strip().lower() if isinstance(email, str) else ""


def allowed_email_set(raw: Any) -> frozenset[str]:
    """Secrets の allowed_emails を、比べやすいメールアドレスの集合にする。

    文字列1つだけが書かれていても受け付ける。空や不正な値は無視する。
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Iterable):
        return frozenset()
    return frozenset(e for e in (normalize_email(item) for item in raw) if "@" in e)


def is_email_verified(value: Any) -> bool:
    """Google が「このメールアドレスは本人のもの」と確認ずみか。

    本来は True / False だが、文字列 "true" で届く場合にも備える。
    """
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() == "true"


def is_allowed(user: Mapping[str, Any], allowed_emails: Iterable[str]) -> bool:
    """ログインした人が、このアプリを使ってよいか。

    user           : st.user の中身（is_logged_in, email, email_verified など）
    allowed_emails : allowed_email_set() で作った集合
    """
    if user.get("is_logged_in") is not True:
        return False
    if not is_email_verified(user.get("email_verified")):
        return False
    email = normalize_email(user.get("email"))
    return bool(email) and email in set(allowed_emails)


def auth_settings_ready(auth_section: Any) -> bool:
    """[auth] の設定がそろっているか（値が空の項目があれば False）。"""
    if not isinstance(auth_section, Mapping):
        return False
    return all(isinstance(auth_section.get(key), str) and auth_section.get(key).strip() for key in REQUIRED_AUTH_KEYS)
