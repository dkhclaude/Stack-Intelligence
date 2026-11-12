"""Alert payload + channel formatting. Uses observed data only — no placeholders."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..domain import EventType, StockState

HEADLINES = {
    EventType.RESTOCKED: "🚨 POKÉWATCH RESTOCK ALERT",
    EventType.NOW_AVAILABLE: "✅ POKÉWATCH NOW AVAILABLE",
    EventType.PREORDER_AVAILABLE: "📦 POKÉWATCH PREORDER LIVE",
    EventType.NEW_LISTING: "🆕 POKÉWATCH NEW LISTING",
    EventType.PRICE_DROP: "💲 POKÉWATCH PRICE DROP",
}
COLORS = {  # Discord embed colors
    EventType.RESTOCKED: 0xE53935, EventType.NOW_AVAILABLE: 0x43A047, EventType.PREORDER_AVAILABLE: 0x1E88E5,
    EventType.NEW_LISTING: 0xFDD835, EventType.PRICE_DROP: 0x8E24AA,
}
REQUIRED = ("product", "retailer", "status", "url", "last_verified", "event_type")


class IncompleteAlert(ValueError):
    pass


def status_label(state: str, ship: bool | None, pickup: bool | None, marketplace: bool) -> str:
    s = StockState(state)
    if s == StockState.IN_STOCK:
        if ship and pickup:
            label = "IN STOCK — SHIPPING & PICKUP"
        elif ship:
            label = "IN STOCK — SHIPPING"
        elif pickup:
            label = "IN STOCK — PICKUP ONLY"
        else:
            label = "IN STOCK"
    elif s == StockState.PREORDER:
        label = "PREORDER AVAILABLE"
    elif s == StockState.COMING_SOON:
        label = "COMING SOON"
    elif s == StockState.OUT_OF_STOCK:
        label = "OUT OF STOCK"
    else:
        label = "UNKNOWN"
    return label + (" (third-party seller)" if marketplace else "")


def fmt_price(p: Decimal | str | None) -> str:
    return f"${Decimal(str(p)):,.2f}" if p not in (None, "") else "Not shown by retailer"


def validate(payload: dict) -> None:
    missing = [k for k in REQUIRED if not payload.get(k)]
    if missing:
        raise IncompleteAlert(f"alert missing observed fields: {missing}")
    for v in payload.values():
        if isinstance(v, str) and ("XX.XX" in v or "[timestamp]" in v or "PLACEHOLDER" in v.upper()):
            raise IncompleteAlert("placeholder value in alert payload")


def text_body(p: dict) -> str:
    lines = [HEADLINES.get(EventType(p["event_type"]), "POKÉWATCH ALERT"), "",
             f"Product: {p['product']}", f"Retailer: {p['retailer']}", f"Status: {p['status']}",
             f"Price: {fmt_price(p.get('price'))}"]
    if p.get("previous_price"):
        lines.append(f"Previous: {fmt_price(p['previous_price'])}")
    if p.get("category"):
        lines.append(f"Type: {p['category']}")
    if p.get("price_flag"):
        lines.append(f"Note: {p['price_flag']}")
    lines += [f"Why: {'; '.join(p.get('reasons') or [])}", f"Confidence: {p.get('confidence', '—')}",
              f"Last Verified: {p['last_verified']} UTC", "", p["url"]]
    return "\n".join(lines)


def telegram_html(p: dict) -> str:
    from html import escape
    head = HEADLINES.get(EventType(p["event_type"]), "POKÉWATCH ALERT")
    rows = [f"<b>{escape(head)}</b>", "", f"<b>{escape(p['product'])}</b>",
            f"🏬 {escape(p['retailer'])}", f"📊 {escape(p['status'])}", f"💵 {escape(fmt_price(p.get('price')))}"]
    if p.get("previous_price"):
        rows[-1] += f" (was {escape(fmt_price(p['previous_price']))})"
    if p.get("price_flag"):
        rows.append(f"⚠️ {escape(p['price_flag'])}")
    rows += [f"ℹ️ {escape('; '.join(p.get('reasons') or []))}",
             f"🕒 Verified {escape(p['last_verified'])} UTC · conf {escape(str(p.get('confidence', '—')))}",
             "", f'<a href="{escape(p["url"], quote=True)}">Open retailer page →</a>']
    return "\n".join(rows)


def discord_payload(p: dict) -> dict:
    et = EventType(p["event_type"])
    fields = [
        {"name": "Retailer", "value": p["retailer"], "inline": True},
        {"name": "Status", "value": p["status"], "inline": True},
        {"name": "Price", "value": fmt_price(p.get("price")) + (f" (was {fmt_price(p['previous_price'])})" if p.get("previous_price") else ""), "inline": True},
    ]
    if p.get("category"):
        fields.append({"name": "Type", "value": p["category"], "inline": True})
    fields.append({"name": "Confidence", "value": str(p.get("confidence", "—")), "inline": True})
    if p.get("price_flag"):
        fields.append({"name": "Price note", "value": p["price_flag"], "inline": False})
    fields.append({"name": "Why", "value": "; ".join(p.get("reasons") or []) or "—", "inline": False})
    embed = {
        "title": p["product"][:256], "url": p["url"], "color": COLORS.get(et, 0x607D8B),
        "description": f"**{HEADLINES.get(et, 'ALERT')}**", "fields": fields,
        "footer": {"text": f"Last verified {p['last_verified']} UTC · PokéWatch"},
        "timestamp": datetime.fromisoformat(p["last_verified_iso"]).isoformat() + "Z" if p.get("last_verified_iso") else None,
    }
    if p.get("image_url"):
        embed["thumbnail"] = {"url": p["image_url"]}
    return {"username": "PokéWatch", "embeds": [{k: v for k, v in embed.items() if v is not None}]}
