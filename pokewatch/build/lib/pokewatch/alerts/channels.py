"""Notification channels: Discord webhook, Telegram Bot API, optional SMTP email."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from ..config import Settings
from .formatting import discord_payload, telegram_html, text_body


class ChannelError(Exception):
    pass


class Channel:
    name = "base"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.http = httpx.Client(timeout=15, transport=transport)

    def configured(self) -> bool:
        raise NotImplementedError

    def send(self, payload: dict) -> str:
        raise NotImplementedError

    def _post(self, url: str, **kw) -> httpx.Response:
        for attempt in range(3):
            try:
                r = self.http.post(url, **kw)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise ChannelError(f"network error: {e}") from e
                continue
            if r.status_code == 429 and attempt < 2:
                import time
                try:
                    wait = float(r.headers.get("Retry-After") or r.json().get("retry_after") or 2)
                except ValueError:
                    wait = 2
                time.sleep(min(wait, 10))
                continue
            return r
        return r


class DiscordChannel(Channel):
    name = "discord"

    def configured(self) -> bool:
        return bool(self.settings.discord_webhook_url)

    def send(self, payload: dict) -> str:
        r = self._post(self.settings.discord_webhook_url, json=discord_payload(payload))
        if r.status_code not in (200, 204):
            raise ChannelError(f"Discord HTTP {r.status_code}: {r.text[:200]}")
        return "sent"


class TelegramChannel(Channel):
    name = "telegram"

    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send(self, payload: dict) -> str:
        base = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"
        html = telegram_html(payload)
        if payload.get("image_url") and len(html) <= 1024:
            r = self._post(f"{base}/sendPhoto", json={"chat_id": self.settings.telegram_chat_id,
                                                      "photo": payload["image_url"], "caption": html, "parse_mode": "HTML"})
            if r.status_code == 200 and r.json().get("ok"):
                return "sent"
            # image rejected (hotlink/size) -> fall back to text
        r = self._post(f"{base}/sendMessage", json={"chat_id": self.settings.telegram_chat_id, "text": html,
                                                    "parse_mode": "HTML", "disable_web_page_preview": False})
        if r.status_code != 200 or not r.json().get("ok"):
            raise ChannelError(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
        return "sent"


class EmailChannel(Channel):
    name = "email"

    def configured(self) -> bool:
        s = self.settings
        return bool(s.smtp_host and s.alert_email_to)

    def send(self, payload: dict) -> str:
        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = f"[PokéWatch] {payload['status']}: {payload['product'][:120]}"
        msg["From"] = s.smtp_user or "pokewatch@localhost"
        msg["To"] = s.alert_email_to
        msg.set_content(text_body(payload))
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password or "")
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            raise ChannelError(f"SMTP error: {e}") from e
        return "sent"


def build_channels(settings: Settings, transport=None) -> dict[str, Channel]:
    return {c.name: c for c in (DiscordChannel(settings, transport), TelegramChannel(settings, transport),
                                EmailChannel(settings, transport))}


def send_test(settings: Settings, channel: str, transport=None) -> str:
    """Send an explicit test message (contains no product/inventory data)."""
    text = "PokéWatch test message — this channel is configured correctly. No product data in this message."
    ch = build_channels(settings, transport)[channel]
    if not ch.configured():
        raise ChannelError(f"{channel} is not configured (check .env)")
    if channel == "discord":
        r = ch._post(settings.discord_webhook_url, json={"username": "PokéWatch", "content": text})
        if r.status_code not in (200, 204):
            raise ChannelError(f"Discord HTTP {r.status_code}: {r.text[:200]}")
    elif channel == "telegram":
        r = ch._post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                     json={"chat_id": settings.telegram_chat_id, "text": text})
        if r.status_code != 200:
            raise ChannelError(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
    else:
        ch.send({"product": "Test message", "status": "TEST", "retailer": "—", "url": "—",
                 "last_verified": "—", "event_type": "NEW_LISTING", "reasons": [text]})
    return "sent"
