from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import lib
from lib import EVENT_STYLE, q

lib.header("Restock History", "Every confirmed stock change, in order. Failed checks are never counted as stock-outs.")

c = st.columns([2, 3, 3])
days = c[0].selectbox("Window", [1, 3, 7, 14, 30, 90], index=2, format_func=lambda d: f"Last {d} days")
ev = q("""select e.occurred_at, e.event_type, e.from_state, e.to_state, l.title, l.url, r.name retailer, l.retailer code
          from listing_events e join retailer_listings l on l.id=e.listing_id
          left join retailer_connectors r on r.code=l.retailer
          where e.event_type in ('RESTOCKED','NOW_AVAILABLE','PREORDER_AVAILABLE','SOLD_OUT') and e.occurred_at >= :d
          order by e.occurred_at desc""", {"d": lib.utcnow() - timedelta(days=days)})
retailers = c[1].multiselect("Retailer", sorted(ev["retailer"].dropna().unique()))
text = c[2].text_input("Product contains")
if retailers:
    ev = ev[ev["retailer"].isin(retailers)]
if text:
    ev = ev[ev["title"].str.lower().str.contains(text.lower(), regex=False)]
if ev.empty:
    st.info("No stock changes in this window.")
    st.stop()

ev["occurred_at"] = pd.to_datetime(ev["occurred_at"])
# 3 groups max (validated all-pairs palette) + distinct marker symbols as secondary encoding
GROUPS = {"Back in stock": (["RESTOCKED"], lib.SERIES[2], "triangle-up"),
          "Became available": (["NOW_AVAILABLE", "PREORDER_AVAILABLE"], lib.SERIES[0], "circle"),
          "Sold out": (["SOLD_OUT"], lib.SERIES[1], "x")}
ev["short"] = ev["title"].str.replace(r"^Pok[ée]mon( TCG)?[:\s-]*", "", regex=True).str.slice(0, 48) + " · " + ev["retailer"].fillna("")
fig = go.Figure()
for name, (types, color, symbol) in GROUPS.items():
    g = ev[ev["event_type"].isin(types)]
    fig.add_trace(go.Scatter(x=g["occurred_at"], y=g["short"], mode="markers", name=name,
                             marker=dict(color=color, size=11, symbol=symbol, line=dict(color=lib.SURFACE, width=2)),
                             customdata=g[["event_type", "from_state"]],
                             hovertemplate="%{y}<br>%{x|%b %d %H:%M} UTC<br>%{customdata[0]} (was %{customdata[1]})<extra></extra>"))
h = max(320, 28 * ev["short"].nunique() + 80)
lib.plotly_layout(fig, h)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.markdown("#### Timeline")
tbl = ev.assign(event=ev["event_type"].map(lambda e: " ".join(EVENT_STYLE.get(e, ("", e)))))
st.dataframe(tbl[["occurred_at", "event", "title", "retailer", "from_state", "to_state", "url"]], hide_index=True,
             use_container_width=True, column_config={
                 "occurred_at": st.column_config.DatetimeColumn("When (UTC)", format="MMM D, HH:mm"),
                 "event": "Event", "title": "Product", "retailer": "Retailer", "from_state": "From", "to_state": "To",
                 "url": st.column_config.LinkColumn("Link", display_text="open ↗")})
