"""Get Well OCR: Streamlit front end (Plan A demo; the phone app talks to the same pipeline).

Run from the project folder:   streamlit run app.py      ->  http://localhost:8501
"""
import streamlit as st

from src.auth import require_login

st.set_page_config(page_title="Get Well OCR", page_icon="assets/logo.png", layout="wide",
                   initial_sidebar_state="expanded")
st.logo("assets/wordmark.svg", size="large", icon_image="assets/logo.svg")
require_login()   # every page goes through app.py, so this gates the whole app

# One screen: the case workspace. The old single-page tool (views/single_page.py) is kept in the repo
# but no longer shown; add it back here as a second st.Page if needed.
nav = st.navigation([
    st.Page("views/case_workspace.py", title="Get Well OCR", default=True),
], position="hidden")
nav.run()
