import calendar
import html
from datetime import date

import pandas as pd
import streamlit as st

import lib
from lib import q

lib.header("Upcoming Releases", "Solid chips = confirmed with a source. Dashed = rumored / unconfirmed date.")

df = q("select * from release_calendar order by release_date")
if df.empty:
    st.info("No releases yet. The 6-hour catalog refresh pulls official set dates; add sealed products in config/releases.yaml.")
    st.stop()
df["release_date"] = pd.to_datetime(df["release_date"]).dt.date
today = lib.utcnow().date()

c = st.columns([2, 2, 3])
cur = pd.Period(today, freq="M")
month_opts = [cur + i for i in range(-2, 7)]
month = c[0].selectbox("Month", month_opts, index=2, format_func=lambda p: p.strftime("%B %Y"))
show = c[1].multiselect("Show", ["confirmed", "rumored"], default=["confirmed", "rumored"])
v = df[df["status"].isin(show)]

y, m = month.year, month.month
cal = calendar.Calendar(firstweekday=6)
cells = ["".join(f'<div class="dow">{d}</div>' for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])]
for d in cal.itermonthdates(y, m):
    items = v[v["release_date"] == d]
    chips = "".join(
        f'<a class="pw-chip {r.status}" href="{html.escape(r.source_url or "#", quote=True)}" target="_blank" '
        f'title="{html.escape(r.name)} — {r.status}, date {r.date_confidence}">{"✔ " if r.status == "confirmed" else "? "}{html.escape(r.name)}</a>'
        for r in items.itertuples())
    cls = "day" + (" out" if d.month != m else "") + (" today" if d == today else "")
    cells.append(f'<div class="{cls}"><div class="num">{d.day}</div>{chips}</div>')
st.markdown(f'<div class="pw-cal">{"".join(cells)}</div>', unsafe_allow_html=True)

st.markdown("#### Next 120 days")
up = v[(v["release_date"].notna()) & (v["release_date"] >= today) &
       (v["release_date"] <= today + pd.Timedelta(days=120))].copy()
undated = v[v["release_date"].isna()]
if up.empty and undated.empty:
    st.caption("Nothing scheduled in this window from current sources.")
else:
    up["in"] = up["release_date"].map(lambda d: f"{(d - today).days} days")
    table = pd.concat([up, undated])[["release_date", "in", "name", "product_type", "status", "date_confidence", "source_name", "source_url"]]
    st.dataframe(table, hide_index=True, use_container_width=True, column_config={
        "release_date": st.column_config.DateColumn("Date"), "in": "In", "name": "Release",
        "product_type": "Type", "status": "Status", "date_confidence": "Date confidence", "source_name": "Source",
        "source_url": st.column_config.LinkColumn("Source link", display_text="open ↗")})

st.markdown("#### Recently released")
past = v[(v["release_date"].notna()) & (v["release_date"] < today)].sort_values("release_date", ascending=False).head(10)
st.dataframe(past[["release_date", "name", "series", "status", "source_url"]], hide_index=True, use_container_width=True,
             column_config={"source_url": st.column_config.LinkColumn("Source", display_text="open ↗")})
