"""Get Well OCR: Streamlit front end (Plan A demo; the phone app talks to the same pipeline).

Run from the project folder:   streamlit run app.py      ->  http://localhost:8501
"""
import streamlit as st

from src.auth import require_login

st.set_page_config(page_title="Get Well OCR", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")
require_login()   # every page goes through app.py, so this gates the whole app

nav = st.navigation([
    st.Page("views/case_workspace.py", title="Fall-Arbeitsplatz", icon="🩺", default=True),
    st.Page("views/single_page.py", title="Einzelne Seite", icon="📄"),
])
nav.run()
