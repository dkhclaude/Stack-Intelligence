from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import select

import lib
from pokewatch.config import get_settings
from pokewatch.db.models import AlertRule, Product, RetailerConnector, RetailerListing
from pokewatch.settings_store import save_runtime_override

lib.header("Settings", "Changes are saved to the database; the worker picks them up within ~2 minutes. "
           "Secrets (API keys, tokens) live only in the .env file.")
rt = lib.runtime()
env = get_settings()

tab_mon, tab_ret, tab_alert, tab_prod, tab_notif = st.tabs(
    ["⏱ Monitoring", "🏬 Retailers", "🔔 Alert rules", "⭐ Products & prices", "📨 Channels & store"])

with tab_mon:
    with st.form("intervals"):
        st.markdown("Target intervals (subject to each retailer's rate limits and minimum interval).")
        c = st.columns(4)
        iv = rt["intervals_s"]
        pc = c[0].number_input("Priority watchlist (min)", 2, 120, iv["priority_check"] // 60)
        uc = c[1].number_input("Upcoming releases (min)", 5, 240, iv["upcoming_check"] // 60)
        dc = c[2].number_input("Discovery (min)", 10, 720, iv["discovery"] // 60)
        cr = c[3].number_input("Catalog refresh (h)", 1, 48, iv["catalog_refresh"] // 3600)
        jit = st.slider("Random jitter (s)", 0, 300, int(rt["jitter_s"]))
        qs = st.text_area("Discovery search queries (one per line)", "\n".join(rt["discovery_queries"]), height=140)
        if st.form_submit_button("Save monitoring settings", type="primary"):
            with lib.session_scope() as s:
                save_runtime_override(s, {"intervals_s": {"priority_check": pc * 60, "upcoming_check": uc * 60,
                                                          "discovery": dc * 60, "catalog_refresh": cr * 3600},
                                          "jitter_s": jit,
                                          "discovery_queries": [x.strip() for x in qs.splitlines() if x.strip()]})
            st.success("Saved.")

with tab_ret:
    with lib.session_scope() as s:
        conns = s.scalars(select(RetailerConnector).order_by(RetailerConnector.priority_tier, RetailerConnector.code)).all()
        df = pd.DataFrame([{"code": c.code, "Retailer": c.name, "Support": c.support_level, "Configured": c.configured,
                            "Enabled": c.enabled,
                            "Requests / min": rt["connectors"].get(c.code, rt["connectors"].get("shopify" if c.code.startswith("shopify_") else c.code, {})).get("requests_per_minute"),
                            "Min interval (s)": rt["connectors"].get(c.code, rt["connectors"].get("shopify" if c.code.startswith("shopify_") else c.code, {})).get("min_interval_s"),
                            "Notes": c.status_note} for c in conns])
    ed = st.data_editor(df, hide_index=True, use_container_width=True, disabled=["code", "Retailer", "Support", "Configured", "Notes"],
                        column_config={"code": None, "Notes": st.column_config.TextColumn(width="large")})
    if st.button("Save retailer settings", type="primary"):
        over = {}
        with lib.session_scope() as s:
            for r in ed.itertuples():
                s.get(RetailerConnector, r.code).enabled = bool(r.Enabled)
                if pd.notna(r._6) or pd.notna(r._7):
                    over[r.code] = {k: int(v) for k, v in (("requests_per_minute", r._6), ("min_interval_s", r._7)) if pd.notna(v)}
            save_runtime_override(s, {"connectors": over})
        st.success("Saved.")
    st.caption("Unsupported retailers cannot be enabled for automated checks — see docs/FEASIBILITY.md for alternatives.")

with tab_alert:
    a = rt["alerts"]
    with st.form("alertcfg"):
        c = st.columns(4)
        cd = c[0].number_input("Cooldown (min)", 1, 1440, int(a["cooldown_minutes"]))
        drop = c[1].number_input("Min price drop %", 1.0, 90.0, float(a["min_price_drop_pct"]))
        req = c[2].toggle("Price drops only when available", bool(a["price_drop_requires_availability"]))
        conf = c[3].slider("Min TCG confidence", 0.3, 1.0, float(a["min_tcg_confidence"]))
        chans = st.multiselect("Default channels", ["discord", "telegram", "email"], a["channels"])
        if st.form_submit_button("Save alert settings", type="primary"):
            with lib.session_scope() as s:
                save_runtime_override(s, {"alerts": {"cooldown_minutes": cd, "min_price_drop_pct": drop,
                                                     "price_drop_requires_availability": req, "min_tcg_confidence": conf,
                                                     "channels": chans}})
            st.success("Saved.")
    st.markdown("**Rules** — an event alerts if any enabled rule matches. Empty list = any. Lists are comma-separated.")
    with lib.session_scope() as s:
        rules = s.scalars(select(AlertRule).order_by(AlertRule.id)).all()
        rdf = pd.DataFrame([{"id": r.id, "Enabled": r.enabled, "Name": r.name, "Events": ",".join(r.event_types or []),
                             "Retailers": ",".join(r.retailers or []), "Categories": ",".join(r.categories or []),
                             "Keywords": ",".join(r.keywords or []), "Min priority": r.min_priority,
                             "Max price": float(r.max_price) if r.max_price is not None else None,
                             "3rd-party sellers": r.include_marketplace, "Channels": ",".join(r.channels or [])} for r in rules])
    red = st.data_editor(rdf, hide_index=True, use_container_width=True, num_rows="dynamic", column_config={"id": None})
    st.caption("Events: NEW_LISTING, PREORDER_AVAILABLE, NOW_AVAILABLE, RESTOCKED, PRICE_DROP · Retailers use codes (bestbuy, shopify_…)")
    if st.button("Save rules", type="primary"):
        split = lambda v: [x.strip() for x in str(v or "").split(",") if x.strip()]  # noqa: E731
        with lib.session_scope() as s:
            keep = set()
            for r in red.to_dict("records"):
                if not r.get("Name"):
                    continue
                rule = s.get(AlertRule, int(r["id"])) if pd.notna(r.get("id")) else None
                if rule is None:
                    rule = AlertRule(name=r["Name"])
                    s.add(rule)
                rule.name, rule.enabled = r["Name"], bool(r["Enabled"])
                rule.event_types, rule.retailers = split(r["Events"]), split(r["Retailers"])
                rule.categories, rule.keywords, rule.channels = split(r["Categories"]), split(r["Keywords"]), split(r["Channels"])
                rule.min_priority = int(r["Min priority"] or 0)
                rule.max_price = Decimal(str(r["Max price"])) if pd.notna(r.get("Max price")) else None
                rule.include_marketplace = bool(r["3rd-party sellers"])
                s.flush()
                keep.add(rule.id)
            for rule in s.scalars(select(AlertRule)):
                if rule.id not in keep:
                    s.delete(rule)
        st.success("Rules saved.")

with tab_prod:
    st.markdown("**Priority**: 3 = top (checked every priority interval) · 2 = priority · 1 = normal · 0 = ignore. "
                "**MSRP** is only used for price flags when a source is entered.")
    with lib.session_scope() as s:
        prods = s.scalars(select(Product).order_by(Product.priority.desc(), Product.name)).all()
        pdf = pd.DataFrame([{"id": p.id, "Priority": p.priority, "Product": p.name, "Category": p.category,
                             "Set": p.set_name, "MSRP": float(p.msrp) if p.msrp is not None else None,
                             "MSRP source": p.msrp_source, "Needs review": p.needs_review} for p in prods])
    if pdf.empty:
        st.info("No products yet.")
    else:
        ped = st.data_editor(pdf, hide_index=True, use_container_width=True, disabled=["id", "Product", "Category", "Set"],
                             column_config={"id": None, "Priority": st.column_config.SelectboxColumn(options=[0, 1, 2, 3])})
        if st.button("Save products", type="primary"):
            with lib.session_scope() as s:
                for r in ped.to_dict("records"):
                    p = s.get(Product, int(r["id"]))
                    p.priority = int(r["Priority"])
                    p.needs_review = bool(r["Needs review"])
                    src = (r.get("MSRP source") or "").strip() or None
                    if pd.notna(r.get("MSRP")) and src:
                        p.msrp, p.msrp_source, p.msrp_verified_at = Decimal(str(r["MSRP"])), src, lib.utcnow()
                    elif pd.isna(r.get("MSRP")):
                        p.msrp, p.msrp_source = None, None
                    for l in s.scalars(select(RetailerListing).where(RetailerListing.product_id == p.id)):
                        l.priority = p.priority
                        l.watch = p.priority > 0
            st.success("Saved. MSRP values without a source were ignored.")

with tab_notif:
    st.markdown("**Notification channels** (configure in `.env`, then test with `pokewatch test-alert <channel>`)")
    for name, ok in [("Discord webhook", bool(env.discord_webhook_url)),
                     ("Telegram bot", bool(env.telegram_bot_token and env.telegram_chat_id)),
                     ("Email (SMTP)", bool(env.smtp_host and env.alert_email_to))]:
        st.markdown(f"{'✅' if ok else '⚪'} {name} — {'configured' if ok else 'not configured'}")
    if env.alerts_dry_run:
        st.warning("ALERTS_DRY_RUN is on: alerts are recorded but not sent.")
    st.markdown("**Local store preference**")
    with st.form("local"):
        z = st.text_input("ZIP code for in-store pickup checks (Best Buy)", rt["local_store"].get("zip") or env.local_zip or "")
        lp = st.toggle("Check local store pickup for in-stock priority items (1 extra request per item)",
                       bool(rt["connectors"]["bestbuy"].get("local_pickup_check", False)))
        if st.form_submit_button("Save", type="primary"):
            with lib.session_scope() as s:
                save_runtime_override(s, {"local_store": {"zip": z.strip() or None},
                                          "connectors": {"bestbuy": {"local_pickup_check": lp}}})
            st.success("Saved.")
