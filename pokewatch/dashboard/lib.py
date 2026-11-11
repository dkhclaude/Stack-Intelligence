"""Shared dashboard helpers: DB access, palette, formatting, components."""

from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pokewatch.db.session import get_engine, init_db, session_scope  # noqa: E402
from pokewatch.domain import utcnow  # noqa: E402
from pokewatch.settings_store import get_runtime, get_value  # noqa: E402

# --- palette (dataviz reference instance, dark mode; validated) ---------------
SURFACE, PAGE = "#1a1a19", "#0d0d0d"
INK, INK2, MUTED, GRID, AXIS = "#f0efec", "#c3c2b7", "#898781", "#2c2c2a", "#383835"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

STATE_STYLE = {  # icon + label always accompany color
    "IN_STOCK": ("✅", "In stock", STATUS["good"]),
    "PREORDER": ("📦", "Preorder", "#3987e5"),
    "COMING_SOON": ("⏳", "Coming soon", MUTED),
    "OUT_OF_STOCK": ("⛔", "Out of stock", STATUS["critical"]),
    "UNKNOWN": ("⚠️", "Unknown (check failed)", STATUS["warning"]),
}
EVENT_STYLE = {
    "RESTOCKED": ("🔁", "Restocked"), "NOW_AVAILABLE": ("✅", "Now available"),
    "PREORDER_AVAILABLE": ("📦", "Preorder opened"), "NEW_LISTING": ("🆕", "New listing"),
    "SOLD_OUT": ("⛔", "Sold out"), "PRICE_DROP": ("💲", "Price drop"), "PRICE_INCREASE": ("📈", "Price up"),
}


def boot() -> None:
    init_db()


@st.cache_data(ttl=20, show_spinner=False)
def q(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as c:
        return pd.read_sql_query(sql, c, params=params or {})


def runtime() -> dict:
    with session_scope() as s:
        return get_runtime(s)


def setting(key: str, default=None):
    with session_scope() as s:
        return get_value(s, key, default)


def retailer_colors() -> dict[str, str]:
    """Color follows the entity: fixed by sorted retailer code, never by rank."""
    codes = q("select code from retailer_connectors order by priority_tier, code")["code"].tolist()
    return {c: SERIES[i % len(SERIES)] for i, c in enumerate(codes)}


def ago(ts) -> str:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)) or ts is pd.NaT:
        return "never"
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    secs = (utcnow() - pd.Timestamp(ts).to_pydatetime()).total_seconds()
    future, secs = secs < 0, abs(secs)
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if secs >= n or unit == "s":
            span = f"{int(secs // n)}{unit}"
            return f"in {span}" if future else f"{span} ago"


def money(v) -> str:
    return "—" if v is None or pd.isna(v) else f"${float(v):,.2f}"


def badge(state: str) -> str:
    icon, label, color = STATE_STYLE.get(state, STATE_STYLE["UNKNOWN"])
    return (f'<span class="pw-badge" style="border-color:{color};color:{INK}">'
            f'<span class="pw-dot" style="background:{color}"></span>{icon} {label}</span>')


CSS = f"""
<style>
.block-container {{padding-top: 3.2rem; max-width: 1400px;}}
.pw-kpi {{background:{SURFACE}; border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:14px 16px; height:100%;}}
.pw-kpi .lbl {{color:{MUTED}; font-size:.78rem; text-transform:uppercase; letter-spacing:.06em;}}
.pw-kpi .val {{color:{INK}; font-size:2rem; font-weight:700; line-height:1.15; margin-top:4px;}}
.pw-kpi .sub {{color:{INK2}; font-size:.8rem; margin-top:2px;}}
.pw-card {{background:{SURFACE}; border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:12px; margin-bottom:14px; height:100%;}}
.pw-card img {{width:100%; aspect-ratio:1/1; object-fit:contain; background:#fff; border-radius:10px;}}
.pw-card .ttl {{color:{INK}; font-weight:600; font-size:.92rem; line-height:1.25; margin:8px 0 4px; min-height:2.4em;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;}}
.pw-card .meta {{color:{INK2}; font-size:.8rem;}}
.pw-card .price {{color:{INK}; font-size:1.25rem; font-weight:700;}}
.pw-card .flag {{color:{STATUS['serious']}; font-size:.75rem;}}
.pw-card a.go {{display:block; text-align:center; margin-top:8px; padding:6px; border-radius:8px; background:#fde047;
  color:#0b0b0b !important; font-weight:700; text-decoration:none; font-size:.85rem;}}
.pw-badge {{display:inline-flex; align-items:center; gap:6px; border:1px solid; border-radius:999px; padding:2px 10px; font-size:.78rem;}}
.pw-dot {{width:8px; height:8px; border-radius:50%; display:inline-block;}}
.pw-demo {{background:{STATUS['warning']}; color:#0b0b0b; padding:8px 14px; border-radius:10px; font-weight:700; margin-bottom:12px;}}
.pw-cal {{display:grid; grid-template-columns:repeat(7, minmax(0,1fr)); gap:6px;}}
.pw-cal .dow {{color:{MUTED}; font-size:.75rem; text-align:center;}}
.pw-cal .day {{background:{SURFACE}; border-radius:10px; min-height:92px; padding:6px; border:1px solid rgba(255,255,255,.06);}}
.pw-cal .day.out {{opacity:.35;}}
.pw-cal .day.today {{border-color:#fde047;}}
.pw-cal .num {{color:{INK2}; font-size:.75rem;}}
.pw-chip {{display:block; font-size:.72rem; border-radius:6px; padding:2px 6px; margin-top:4px; color:{INK}; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap;}}
.pw-chip.confirmed {{background:rgba(57,135,229,.30); border:1px solid #3987e5;}}
.pw-chip.rumored {{background:transparent; border:1px dashed {MUTED};}}
button[data-testid^="stBaseButton-primary"], button[data-testid^="stBaseButton-primary"] p,
span[data-baseweb="tag"], span[data-baseweb="tag"] span {{color:#0b0b0b !important;}}
@media (max-width: 700px) {{ .pw-cal {{grid-template-columns:repeat(2, minmax(0,1fr));}} .pw-cal .dow {{display:none;}} }}
</style>
"""


def header(title: str, subtitle: str = "") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if setting("demo_mode", False):
        st.markdown('<div class="pw-demo">⚠️ DEMO DATABASE — simulated retailers and inventory. Nothing here is real stock.</div>',
                    unsafe_allow_html=True)
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def kpi(col, label: str, value, sub: str = "") -> None:
    col.markdown(f'<div class="pw-kpi"><div class="lbl">{html.escape(label)}</div>'
                 f'<div class="val">{html.escape(str(value))}</div><div class="sub">{html.escape(sub)}</div></div>',
                 unsafe_allow_html=True)


def product_card(row) -> str:
    img = row.get("image_url") or ""
    img_html = (f'<img src="{html.escape(img, quote=True)}" loading="lazy" alt="" '
                f'onerror="this.style.visibility=\'hidden\'">') if img else \
        '<div style="aspect-ratio:1/1;border-radius:10px;background:#2c2c2a;display:flex;align-items:center;justify-content:center;color:#898781">no image</div>'
    flag = f'<div class="flag">⚠ {html.escape(row["price_flag"])}</div>' if row.get("price_flag") else ""
    fulfil = []
    if row.get("ship_available") == 1:
        fulfil.append("🚚 ship")
    if row.get("pickup_available") == 1:
        fulfil.append("🏬 pickup")
    return (f'<div class="pw-card">{img_html}<div class="ttl" title="{html.escape(row["title"], quote=True)}">'
            f'{html.escape(row["title"])}</div>'
            f'<div class="meta">{html.escape(row["retailer_name"])} · {html.escape(row.get("category") or "")}</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">'
            f'<span class="price">{money(row.get("current_price"))}</span>{badge(row["current_state"])}</div>{flag}'
            f'<div class="meta" style="margin-top:4px">{" · ".join(fulfil)} {"· " if fulfil else ""}checked {ago(row.get("last_checked_at"))}</div>'
            f'<a class="go" href="{html.escape(row["url"], quote=True)}" target="_blank" rel="noopener">Open at retailer →</a></div>')


def plotly_layout(fig, height=320):
    fig.update_layout(template="plotly_dark", paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, height=height,
                      font=dict(color=INK2, size=12), margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)"),
                      hoverlabel=dict(bgcolor=PAGE, font_color=INK))
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    return fig
