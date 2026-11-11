"""Guided Telegram setup: validate the bot token, detect the chat id, save both to .env, send a test.

The only manual steps left for the user are creating the bot with @BotFather and
sending that bot one message ("hi") from their phone.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


class SetupError(Exception):
    pass


def set_env_values(env_path: Path, values: dict[str, str]) -> None:
    """Set KEY=value lines in .env, replacing existing keys and appending new ones."""
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    remaining = dict(values)
    for i, ln in enumerate(lines):
        key = ln.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    lines += [f"{k}={v}" for k, v in remaining.items()]
    env_path.write_text("\n".join(lines) + "\n")


class TelegramSetup:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        token = token.strip()
        if not TOKEN_RE.match(token):
            raise SetupError("That doesn't look like a bot token. It should look like 123456789:AAH... "
                             "(copy the whole line BotFather sent after 'Use this token').")
        self.base = f"https://api.telegram.org/bot{token}"
        self.token = token
        self.http = httpx.Client(timeout=15, transport=transport)
        self.sleep = sleep

    def _call(self, method: str, **params) -> dict:
        try:
            r = self.http.post(f"{self.base}/{method}", json=params)
        except httpx.HTTPError as e:
            raise SetupError(f"Couldn't reach Telegram ({e}). Check your internet connection.") from e
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 401:
            raise SetupError("Telegram rejected the token. Copy it again from your chat with @BotFather.")
        if not data.get("ok"):
            raise SetupError(f"Telegram error: {data.get('description') or r.status_code}")
        return data["result"]

    def bot_username(self) -> str:
        return self._call("getMe")["username"]

    def find_chat(self, wait_s: int = 120, poll_every: int = 3) -> tuple[str, str]:
        """Return (chat_id, display name) of the most recent private chat that messaged the bot."""
        waited = 0
        while True:
            updates = self._call("getUpdates", timeout=0)
            for u in reversed(updates):
                msg = u.get("message") or u.get("edited_message") or {}
                chat = msg.get("chat") or {}
                if chat.get("type") == "private" and chat.get("id") is not None:
                    name = chat.get("first_name") or chat.get("username") or "you"
                    return str(chat["id"]), name
            if waited >= wait_s:
                raise SetupError("No message received. Open your bot in Telegram, tap Start (or send 'hi'), then run this again.")
            self.sleep(poll_every)
            waited += poll_every

    def send_test(self, chat_id: str) -> None:
        self._call("sendMessage", chat_id=chat_id,
                   text="✅ PokéWatch is connected! Restock and preorder alerts will arrive here.")
