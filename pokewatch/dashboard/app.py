"""PokéWatch dashboard. Run: streamlit run dashboard/app.py

The dashboard only reads/writes the database; monitoring runs in the separate
worker process (`pokewatch worker`), so closing this page never stops checks.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import streamlit as st  # noqa: E402

import lib  # noqa: E402

st.set_page_config(page_title="PokéWatch", page_icon="⚡", layout="wide")
lib.boot()

V = Path(__file__).parent / "views"
pages = [
    st.Page(V / "command_center.py", title="Command Center", icon="🛰️", default=True),
    st.Page(V / "live_feed.py", title="Live Product Feed", icon="🃏"),
    st.Page(V / "releases.py", title="Upcoming Releases", icon="📅"),
    st.Page(V / "restock_history.py", title="Restock History", icon="🔁"),
    st.Page(V / "price_tracker.py", title="Price Tracker", icon="💲"),
    st.Page(V / "agent_activity.py", title="Agent Activity", icon="🤖"),
    st.Page(V / "settings.py", title="Settings", icon="⚙️"),
]
st.navigation(pages).run()
