import streamlit as st

import lib
from lib import STATE_STYLE, q

lib.header("Live Product Feed", "Every Pokémon TCG listing we monitor. Buttons open the retailer's own page.")

df = q("""select l.*, r.name retailer_name from retailer_listings l
          left join retailer_connectors r on r.code = l.retailer where l.active order by l.last_checked_at desc""")
if df.empty:
    st.info("No listings yet. Configure a connector (Settings) and run discovery.")
    st.stop()

f = st.columns([2, 2, 2, 2, 3])
retailers = f[0].multiselect("Retailer", sorted(df["retailer_name"].dropna().unique()))
cats = f[1].multiselect("Category", sorted(df["category"].dropna().unique()))
states = f[2].multiselect("Availability", list(STATE_STYLE), format_func=lambda s: f"{STATE_STYLE[s][0]} {STATE_STYLE[s][1]}",
                          default=[])
prices = df["current_price"].dropna().astype(float)
hi = float(prices.max()) if len(prices) else 500.0
top = float(max(10, round(hi + 1)))
pr = f[3].slider("Price", 0.0, top, (0.0, top))
text = f[4].text_input("Search", placeholder="e.g. Prismatic ETB")

o = st.columns([2, 2, 6])
sort = o[0].selectbox("Sort", ["Recently checked", "Price ↑", "Price ↓", "Newest listing", "Priority"])
hide_mkt = o[1].toggle("Hide 3rd-party sellers", value=True)

v = df.copy()
if retailers:
    v = v[v["retailer_name"].isin(retailers)]
if cats:
    v = v[v["category"].isin(cats)]
if states:
    v = v[v["current_state"].isin(states)]
v = v[(v["current_price"].isna()) | (v["current_price"].astype(float).between(*pr))]
if text:
    for w in text.lower().split():
        v = v[v["title"].str.lower().str.contains(w, regex=False)]
if hide_mkt:
    v = v[v["is_marketplace"] != 1]
v = {"Price ↑": v.sort_values("current_price"), "Price ↓": v.sort_values("current_price", ascending=False),
     "Newest listing": v.sort_values("first_seen_at", ascending=False),
     "Priority": v.sort_values(["priority", "current_state"], ascending=[False, True])}.get(sort, v)

counts = v["current_state"].value_counts()
st.caption(" · ".join(f"{STATE_STYLE[s][0]} {STATE_STYLE[s][1]}: **{counts.get(s, 0)}**" for s in STATE_STYLE) +
           f" · showing {len(v)} of {len(df)}")

rows = v.head(120).to_dict("records")
per_row = 4
for i in range(0, len(rows), per_row):
    cols = st.columns(per_row)
    for col, r in zip(cols, rows[i:i + per_row]):
        col.markdown(lib.product_card(r), unsafe_allow_html=True)
if len(v) > 120:
    st.caption("Showing first 120 — narrow the filters to see more.")
