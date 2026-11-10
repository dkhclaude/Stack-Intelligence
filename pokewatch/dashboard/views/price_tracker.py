import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import lib
from lib import money, q

lib.header("Price Tracker", "Observed prices over time per retailer. MSRP is shown only when verified with a source.")

prods = q("""select p.id, p.name, p.category, p.msrp, p.msrp_source, count(l.id) n from products p
             join retailer_listings l on l.product_id=p.id group by p.id, p.name, p.category, p.msrp, p.msrp_source
             order by count(l.id) desc, p.name""")
if prods.empty:
    st.info("No price data yet.")
    st.stop()
label = {r.id: f"{r.name}  ({r.n} retailer{'s' if r.n > 1 else ''})" for r in prods.itertuples()}
pid = st.selectbox("Product", list(label), format_func=label.get)
p = prods[prods["id"] == pid].iloc[0]

hist = q("""select h.observed_at, h.price, h.retailer, r.name retailer_name, h.is_marketplace from price_history h
            left join retailer_connectors r on r.code=h.retailer where h.product_id=:p order by h.observed_at""", {"p": int(pid)})
listings = q("""select l.retailer, r.name retailer_name, l.current_price, l.previous_price, l.lowest_price, l.highest_price,
                l.current_state, l.is_marketplace, l.seller_name, l.price_flag, l.last_success_at, l.url
                from retailer_listings l left join retailer_connectors r on r.code=l.retailer where l.product_id=:p""",
             {"p": int(pid)})
colors = lib.retailer_colors()

c = st.columns(4)
cur = listings["current_price"].dropna().astype(float)
lib.kpi(c[0], "Best current price", money(cur.min()) if len(cur) else "—",
        listings.loc[listings["current_price"].astype(float).idxmin(), "retailer_name"] if len(cur) else "")
lib.kpi(c[1], "Lowest ever observed", money(listings["lowest_price"].dropna().astype(float).min()))
lib.kpi(c[2], "Highest observed", money(listings["highest_price"].dropna().astype(float).max()))
lib.kpi(c[3], "Verified MSRP", money(p["msrp"]) if p["msrp_source"] else "not verified",
        (p["msrp_source"] or "add in Settings with a source")[:40])

st.markdown("#### Price history")
if hist.empty:
    st.caption("No price observations yet.")
else:
    hist["observed_at"] = pd.to_datetime(hist["observed_at"])
    now = pd.Timestamp(lib.utcnow())
    fig = go.Figure()
    for code, g in hist.groupby("retailer"):
        # extend each line to "now" with its last known price so the step reads correctly
        g = pd.concat([g, g.tail(1).assign(observed_at=now)])
        fig.add_trace(go.Scatter(x=g["observed_at"], y=g["price"].astype(float), name=g["retailer_name"].iloc[0],
                                 mode="lines", line=dict(color=colors.get(code, lib.SERIES[0]), width=2, shape="hv"),
                                 hovertemplate="%{fullData.name}: $%{y:.2f}<br>%{x|%b %d %H:%M}<extra></extra>"))
    if p["msrp_source"] and p["msrp"]:
        fig.add_hline(y=float(p["msrp"]), line=dict(color=lib.MUTED, dash="dot", width=1),
                      annotation_text="MSRP (verified)", annotation_font_color=lib.INK2)
    lib.plotly_layout(fig, 340).update_layout(hovermode="x unified", yaxis_tickprefix="$")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.markdown("#### Retailer comparison")
cmp_ = listings.sort_values("current_price")
if len(cmp_.dropna(subset=["current_price"])):
    fig = go.Figure(go.Bar(
        y=cmp_["retailer_name"], x=cmp_["current_price"].astype(float), orientation="h",
        marker_color=[colors.get(c, lib.SERIES[0]) for c in cmp_["retailer"]], marker_cornerradius=4,
        text=[money(x) for x in cmp_["current_price"]], textposition="outside", textfont_color=lib.INK,
        hovertemplate="%{y}: $%{x:.2f}<extra></extra>"))
    lib.plotly_layout(fig, 60 + 46 * len(cmp_)).update_layout(showlegend=False, xaxis_tickprefix="$", bargap=0.4)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
tbl = listings.assign(status=listings["current_state"].map(lambda s: " ".join(lib.STATE_STYLE.get(s, ("", s))[:2])),
                      seller=listings.apply(lambda r: (r["seller_name"] or "") + (" (3rd-party)" if r["is_marketplace"] == 1 else ""), axis=1))
st.dataframe(tbl[["retailer_name", "status", "current_price", "previous_price", "lowest_price", "highest_price", "seller",
                  "price_flag", "last_success_at", "url"]], hide_index=True, use_container_width=True, column_config={
    "retailer_name": "Retailer", "status": "Status",
    **{k: st.column_config.NumberColumn(k.replace("_", " ").title(), format="$%.2f")
       for k in ["current_price", "previous_price", "lowest_price", "highest_price"]},
    "seller": "Seller", "price_flag": "Note", "last_success_at": st.column_config.DatetimeColumn("Verified (UTC)", format="MMM D HH:mm"),
    "url": st.column_config.LinkColumn("Link", display_text="open ↗")})
