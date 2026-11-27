"""Login for the PWA: same APP_USERNAME / APP_PASSWORD as the Streamlit app (src/auth.py).

After a successful login the browser gets an HttpOnly cookie with a signed, expiring token
(HMAC-SHA256, standard library only). The signing key comes from APP_SESSION_SECRET; without it a
random key is made at start-up, so a restart of the container logs everybody out.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request

from src import config  # noqa: F401  (loads .env, like src/auth.py)

COOKIE = "gwo_session"
MAX_AGE = 12 * 3600          # seconds a login stays valid
_KEY = (os.getenv("APP_SESSION_SECRET", "").strip() or secrets.token_hex(32)).encode("utf-8")


def credentials() -> tuple[str, str] | None:
    """The configured login, or None if it is missing (then nobody can log in)."""
    user = os.getenv("APP_USERNAME", "").strip()
    pw = os.getenv("APP_PASSWORD", "").strip()
    if not user or not pw or "<" in user or "<" in pw:
        return None
    return user, pw


def check_login(user: str, pw: str) -> bool:
    creds = credentials()
    if creds is None:
        return False
    # Phone keyboards capitalise the first letter and add a space after a suggestion: the user name is
    # compared without case, both without surrounding spaces (the stored values are stripped too).
    # The password stays case-sensitive.
    ok_user = hmac.compare_digest(user.strip().casefold().encode("utf-8"), creds[0].casefold().encode("utf-8"))
    ok_pw = hmac.compare_digest(pw.strip().encode("utf-8"), creds[1].encode("utf-8"))
    return ok_user and ok_pw


def mismatch_report(user: str, pw: str) -> str:
    """Why a login failed, for the server log. Lengths and yes/no only, never the typed or stored values."""
    creds = credentials()
    if creds is None:
        return "login not configured"
    u, p = user.strip(), pw.strip()
    return (f"user_ok={u.casefold() == creds[0].casefold()} user_len={len(u)}/{len(creds[0])} "
            f"pw_ok={p == creds[1]} pw_len={len(p)}/{len(creds[1])} pw_ok_ignoring_case={p.casefold() == creds[1].casefold()} "
            f"pw_non_ascii={any(ord(c) > 127 for c in p)} pw_inner_space={' ' in p}")


def _sign(payload: str) -> str:
    return hmac.new(_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_token(user: str) -> str:
    payload = base64.urlsafe_b64encode(f"{user}|{int(time.time()) + MAX_AGE}".encode("utf-8")).decode("ascii")
    return f"{payload}.{_sign(payload)}"


def read_token(token: str | None) -> str | None:
    """User name from a valid, unexpired token, else None."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        user, expires = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8").rsplit("|", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    return user if int(expires) > time.time() else None


def require_user(request: Request) -> str:
    """FastAPI dependency: 401 unless the request carries a valid session cookie."""
    user = read_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "Nicht angemeldet.")
    return user
