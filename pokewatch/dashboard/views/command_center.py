from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import lib
from lib import EVENT_STYLE, STATUS, ago, kpi, q

lib.header("Command Center", "Live state of every monitored retailer, at a glance.")
now = lib.utcnow()
day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

products = q("select count(*) n from products")["n"].iloc[0]
listings = q("select current_state, last_confirmed_state, first_seen_at from retailer_listings where active")
in_stock = int((listings["current_state"] == "IN_STOCK").sum()) if len(listings) else 0
preorder = int((listings["current_state"] == "PREORDER").sum()) if len(listings) else 0
new24 = int((pd.to_datetime(listings["first_seen_at"]) >= now - timedelta(hours=24)).sum()) if len(listings) else 0
restocks_today = q("select count(*) n from listing_events where event_type in ('RESTOCKED','NOW_AVAILABLE') and occurred_at >= :d",
                   {"d": day_start})["n"].iloc[0]
conns = q("select * from retailer_connectors")
active = conns[(conns["configured"] == 1) & (conns["enabled"] == 1) & (conns["support_level"] == "supported")]
last_ok = q("select max(finished_at) t from monitoring_jobs where status in ('ok','partial') and connector is not null and connector != 'releases'")["t"].iloc[0]
hb = lib.setting("worker_heartbeat")
hb_age = (now - pd.Timestamp(hb["ts"]).to_pydatetime()).total_seconds() if hb else None
open_circuits = int((conns["circuit_state"] == "open").sum())
if hb_age is None or hb_age > 240:
    health, health_sub = "🔴 Down", "worker heartbeat missing" if hb_age is None else f"last heartbeat {ago(hb['ts'])}"
elif open_circuits:
    health, health_sub = "🟠 Degraded", f"{open_circuits} connector circuit(s) open"
else:
    health, health_sub = "🟢 Healthy", f"heartbeat {ago(hb['ts'])}"

c = st.columns(4)
kpi(c[0], "Products tracked", f"{products:,}", f"{len(listings):,} retailer listings")
kpi(c[1], "In stock now", in_stock, f"+ {preorder} on preorder")
kpi(c[2], "New listings (24h)", new24)
kpi(c[3], "Restocks today", int(restocks_today), "incl. first-time availability")
st.write("")
c = st.columns(4)
kpi(c[0], "Active connectors", f"{len(active)} / {len(conns)}", "live-capable / registered")
kpi(c[1], "Last successful scan", ago(last_ok))
kpi(c[2], "Monitoring health", health, health_sub)
alerts24 = q("select count(*) n from alerts where created_at >= :d and status != 'suppressed'", {"d": now - timedelta(hours=24)})["n"].iloc[0]
kpi(c[3], "Alerts (24h)", int(alerts24))

st.write("")
left, right = st.columns([3, 2])
with left:
    st.markdown("#### Restocks per day · last 14 days")
    ev = q("select occurred_at from listing_events where event_type in ('RESTOCKED','NOW_AVAILABLE') and occurred_at >= :d",
           {"d": now - timedelta(days=14)})
    days = pd.date_range((now - timedelta(days=13)).date(), now.date(), freq="D")
    counts = pd.to_datetime(ev["occurred_at"]).dt.normalize().value_counts() if len(ev) else pd.Series(dtype=int)
    y = [int(counts.get(d, 0)) for d in days]
    fig = go.Figure(go.Bar(x=days, y=y, marker_color=lib.SERIES[0], marker_line_width=0,
                           hovertemplate="%{x|%b %d}: %{y} restocks<extra></extra>"))
    fig.update_traces(marker_cornerradius=4)
    lib.plotly_layout(fig, 280).update_layout(bargap=0.35, showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
with right:
    st.markdown("#### Latest alerts")
    al = q("""select a.created_at, a.event_type, a.status, l.title, l.url, r.name retailer from alerts a
              join retailer_listings l on l.id=a.listing_id left join retailer_connectors r on r.code=l.retailer
              where a.status != 'suppressed' order by a.created_at desc limit 7""")
    if al.empty:
        st.info("No alerts yet. They appear here as soon as a qualifying change is observed.")
    for _, a in al.iterrows():
        icon, label = EVENT_STYLE.get(a["event_type"], ("•", a["event_type"]))
        st.markdown(f"{icon} **{label}** · [{a['title'][:60]}]({a['url']})  \n"
                    f"<span style='color:{lib.MUTED};font-size:.8rem'>{a['retailer']} · {ago(a['created_at'])} · {a['status']}</span>",
                    unsafe_allow_html=True)

st.markdown("#### Retailer connectors")
cols = st.columns(4)
for i, (_, r) in enumerate(conns.sort_values(["priority_tier", "code"]).iterrows()):
    if r["support_level"] == "supported" and r["configured"] and r["enabled"]:
        icon, color = ("🟢", STATUS["good"]) if r["circuit_state"] == "closed" else ("🟠", STATUS["serious"])
        state = "Monitoring" if r["circuit_state"] == "closed" else f"Paused ({r['circuit_state']})"
    elif r["support_level"] in ("needs_credentials",) or (r["support_level"] == "supported" and not r["configured"]):
        icon, color, state = "🔑", STATUS["warning"], "Needs API key"
    elif r["support_level"] == "needs_approval":
        icon, color, state = "📝", lib.MUTED, "Needs partner approval"
    else:
        icon, color, state = "🚫", lib.MUTED, "Unsupported (no permitted access)"
    live = " · live-verified" if r["verified_live"] else ""
    cols[i % 4].markdown(
        f"<div class='pw-kpi' style='margin-bottom:10px;border-left:4px solid {color}'>"
        f"<div class='lbl'>P{r['priority_tier']}</div><div style='font-weight:700;color:{lib.INK}'>{icon} {r['name']}</div>"
        f"<div class='sub'>{state}{live}<br>last ok: {ago(r['last_success_at'])}</div></div>", unsafe_allow_html=True)
