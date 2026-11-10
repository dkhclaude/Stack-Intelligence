from datetime import timedelta

import pandas as pd
import streamlit as st

import lib
from lib import ago, q

lib.header("Agent Activity", "What the worker is doing, what failed, and what runs next.")
rt = lib.runtime()
now = lib.utcnow()

lst = q("select priority, current_state, last_confirmed_state, release_date from retailer_listings where active and watch")
c = st.columns(4)
lib.kpi(c[0], "Priority watchlist", int((lst["priority"] >= 2).sum()), f"every {rt['intervals_s']['priority_check'] // 60} min")
up = lst[(lst["priority"] < 2) & lst["last_confirmed_state"].isin(["PREORDER", "COMING_SOON"])]
lib.kpi(c[1], "Upcoming / preorder", len(up), f"every {rt['intervals_s']['upcoming_check'] // 60} min")
lib.kpi(c[2], "Discovery queries", len(rt["discovery_queries"]), f"every {rt['intervals_s']['discovery'] // 60} min")
lib.kpi(c[3], "Full catalog refresh", len(lst), f"every {rt['intervals_s']['catalog_refresh'] // 3600} h")

st.markdown("#### Next scheduled checks")
jobs = q("select job_name, max(started_at) last from monitoring_jobs where status != 'skipped' group by job_name")
rows = []
for name, iv in rt["intervals_s"].items():
    if name == "health":
        continue
    last = jobs.loc[jobs["job_name"] == name, "last"]
    last = pd.to_datetime(last.iloc[0]).to_pydatetime() if len(last) and pd.notna(last.iloc[0]) else None
    nxt = (last + timedelta(seconds=iv)) if last else None
    rows.append({"Job": name, "Interval": f"{iv // 60} min" if iv < 3600 else f"{iv / 3600:g} h",
                 "Last run": ago(last), "Next (approx., ± jitter)": ("due now" if nxt and nxt <= now else ago(nxt)) if nxt else "on worker start"})
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

st.markdown("#### Connector health")
conns = q("select * from retailer_connectors order by priority_tier, code")
conns["Circuit"] = conns["circuit_state"].map({"closed": "🟢 closed", "open": "🔴 open", "half_open": "🟠 half-open"})
conns["Live-verified"] = conns["verified_live"].map({1: "✅ yes", 0: "— not yet", True: "✅ yes", False: "— not yet"})
conns["Last OK"] = conns["last_success_at"].map(ago)
conns["Last error"] = conns["last_error_at"].map(ago) + " · " + conns["last_error"].fillna("").str.slice(0, 80)
st.dataframe(conns[["name", "priority_tier", "support_level", "configured", "enabled", "Circuit", "Live-verified",
                    "Last OK", "requests_today", "Last error", "status_note"]], hide_index=True, use_container_width=True,
             column_config={"name": "Connector", "priority_tier": "Tier", "support_level": "Support",
                            "requests_today": "Requests today", "status_note": st.column_config.TextColumn("Notes", width="large")})

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### Recent scans")
    j = q("select started_at, job_name, connector, status, items_checked, items_failed, new_listings, events_created, alerts_created, error "
          "from monitoring_jobs order by started_at desc limit 60")
    j["status"] = j["status"].map(lambda s: {"ok": "✅ ok", "partial": "🟠 partial", "failed": "🔴 failed",
                                             "skipped": "⏭ skipped", "running": "⏳ running", "abandoned": "⚠️ abandoned"}.get(s, s))
    st.dataframe(j, hide_index=True, use_container_width=True, height=380,
                 column_config={"started_at": st.column_config.DatetimeColumn("Started (UTC)", format="MMM D HH:mm:ss")})
with c2:
    st.markdown("#### Failed scans")
    f = q("select started_at, job_name, connector, error from monitoring_jobs where status in ('failed','abandoned') "
          "order by started_at desc limit 40")
    if f.empty:
        st.success("No failed scans recorded.")
    else:
        st.dataframe(f, hide_index=True, use_container_width=True, height=380)

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### Products discovered (latest)")
    d = q("select l.first_seen_at, l.title, r.name retailer, l.category, l.tcg_confidence from retailer_listings l "
          "left join retailer_connectors r on r.code=l.retailer order by l.first_seen_at desc limit 25")
    st.dataframe(d, hide_index=True, use_container_width=True, column_config={
        "tcg_confidence": st.column_config.ProgressColumn("TCG conf.", min_value=0, max_value=1, format="%.2f")})
with c2:
    st.markdown("#### Alerts generated")
    a = q("select a.created_at, a.event_type, a.status, a.suppressed_reason, l.title from alerts a "
          "join retailer_listings l on l.id=a.listing_id order by a.created_at desc limit 25")
    st.dataframe(a, hide_index=True, use_container_width=True)

with st.expander("System events log"):
    st.dataframe(q("select created_at, level, component, event, message from system_events order by created_at desc limit 200"),
                 hide_index=True, use_container_width=True)
