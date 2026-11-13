"""FinSight AI - Streamlit user interface (multi-page).

Run from the project root, with the API already running in another terminal:
    streamlit run frontend/app.py

The UI only talks to the FastAPI backend (frontend/api_client.py). All AI and data work happens there.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))   # so "frontend" imports work under `streamlit run`

import streamlit as st  # noqa: E402

from frontend import embedded_api  # noqa: E402

# Live demo only (Streamlit Community Cloud): settings first, because the modules below read them on import
_LIVE = embedded_api.deploy_settings()
if _LIVE:
    embedded_api.apply_settings(_LIVE)
    try:      # the Gemini key is pasted into Streamlit Cloud's "Secrets" box; the backend reads env vars
        for _key, _value in st.secrets.items():
            if isinstance(_value, str):
                os.environ.setdefault(_key, _value)
    except Exception:  # no secrets configured: the app still runs (saved answers + exact figures)
        pass

from frontend import ui  # noqa: E402
from frontend.logos import finsight_mark, finsight_wordmark_svg  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO, MARK = ASSETS / "finsight_logo.svg", ASSETS / "finsight_mark.svg"


def ensure_logo_files() -> None:
    """The logos are generated from code (frontend/logos.py), so they can never go missing."""
    ASSETS.mkdir(exist_ok=True)
    if not LOGO.exists():
        LOGO.write_text(finsight_wordmark_svg(), encoding="utf-8")
    if not MARK.exists():
        MARK.write_text(finsight_mark(48), encoding="utf-8")


def init_state() -> None:
    defaults = {"messages": {"sec": [], "upload": []}, "ask_pending": None, "upload_pending": None,
                "uploader_key": 0, "selected_docs": set(), "upload_error": None, "dash_ticker": "AAPL"}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_resource(show_spinner="Starting FinSight (loading the search index and the AI model)…")
def start_embedded_api() -> bool:
    """Live demo: one backend for all visitors, started once per server process."""
    return embedded_api.start_api()


ensure_logo_files()
st.set_page_config(page_title="FinSight AI", page_icon=str(MARK), layout="wide")
if _LIVE:
    start_embedded_api()
ui.apply_theme()
init_state()
st.logo(str(LOGO), size="large", icon_image=str(MARK))

pages = [
    st.Page("views/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("views/ask.py", title="Ask AI", icon=":material/forum:"),
    st.Page("views/upload.py", title="Upload & Analyze", icon=":material/upload_file:"),
    st.Page("views/compare.py", title="Compare", icon=":material/compare_arrows:"),
    st.Page("views/dashboard.py", title="Company Dashboard", icon=":material/monitoring:"),
    st.Page("views/how_it_works.py", title="How it works", icon=":material/account_tree:"),
    st.Page("views/monitoring.py", title="Monitoring", icon=":material/insights:"),
]
page = st.navigation(pages)

if ui.sidebar_status() is None:
    st.title("FinSight AI")
    st.error("The FinSight API is not running. In another terminal run  "
             "`uvicorn backend.main:app --port 8000`  (or `run_demo.ps1`), then refresh this page.")
    st.stop()

page.run()
