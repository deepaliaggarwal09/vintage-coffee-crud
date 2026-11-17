"""
Vintage Coffee & Beverages Ltd - Business Management System
MKT322 Advanced Business Analytics | Academic Task 2
Run with:  streamlit run streamlit_app.py
"""
import streamlit as st

st.set_page_config(page_title="Vintage Coffee — Business Manager", page_icon="☕", layout="wide")

from app import db  # noqa: E402
from app.views import about, analysis, dashboard, manage  # noqa: E402

PAGES = {
    "📊 Dashboard": dashboard.render,
    "🗂️ Manage records": manage.render,
    "🧮 SQL analysis": analysis.render,
    "ℹ️ About": about.render,
}

with st.sidebar:
    st.markdown("## ☕ Vintage Coffee")
    st.caption("Business Management System")
    page = st.radio("Navigate", list(PAGES), label_visibility="collapsed")
    st.divider()

# ---- make sure the database is reachable before drawing anything -------------
try:
    db.check_connection()
    with st.sidebar:
        st.success("MySQL connected", icon="🟢")
        if st.button("🔄 Refresh data", width="stretch"):
            st.rerun()
        st.caption("MKT322 · Academic Task 2")
except db.DBConfigError as exc:
    st.error(str(exc), icon="🔧")
    st.stop()
except Exception as exc:  # noqa: BLE001
    db.reset_engine()
    st.error(f"Could not connect to the database. {db.friendly_error(exc)}", icon="🔌")
    with st.expander("Technical details"):
        st.code(str(exc))
    st.stop()

# ---- render the chosen page; never show a raw traceback ----------------------
try:
    PAGES[page]()
except Exception as exc:  # noqa: BLE001
    st.error(db.friendly_error(exc), icon="⚠️")
    with st.expander("Technical details"):
        st.exception(exc)
