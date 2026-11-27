"""Simple login gate for the Streamlit app.

Username and password come from APP_USERNAME / APP_PASSWORD in .env.
If either is missing, the app shows an error instead of opening without a login.
"""
import hmac
import os

import streamlit as st

from . import config  # noqa: F401  (loads .env)


def _matches(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def require_login() -> None:
    """Stop the script run unless the user has logged in this session."""
    username = os.getenv("APP_USERNAME", "").strip()
    password = os.getenv("APP_PASSWORD", "").strip()
    # "<choose-a-...>" placeholders from .env.example are public, so they count as not set
    if not username or not password or "<" in username or "<" in password:
        st.error("Login is not configured: set APP_USERNAME and APP_PASSWORD in .env.")
        st.stop()

    if st.session_state.get("authenticated"):
        with st.sidebar:
            if st.button("Abmelden / Log out"):
                st.session_state.clear()
                st.rerun()
        return

    st.title("🩺 Get Well OCR")
    with st.form("login"):
        user = st.text_input("Benutzername / Username")
        pw = st.text_input("Passwort / Password", type="password")
        submitted = st.form_submit_button("Anmelden / Log in")
    if submitted:
        # evaluate both comparisons so timing doesn't reveal which one failed
        ok_user, ok_pw = _matches(user, username), _matches(pw, password)
        if ok_user and ok_pw:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Benutzername oder Passwort falsch / Wrong username or password.")
    st.stop()
