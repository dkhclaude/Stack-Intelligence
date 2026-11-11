import json

import httpx
import pytest

from pokewatch.telegram_setup import SetupError, TelegramSetup, set_env_values

TOKEN = "123456789:AAH" + "x" * 32


class FakeTelegram:
    def __init__(self, updates_seq):
        self.updates_seq = list(updates_seq)
        self.sent = []

    def __call__(self, req: httpx.Request):
        method = req.url.path.rsplit("/", 1)[-1]
        body = json.loads(req.content or b"{}")
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "pokewatch_test_bot"}})
        if method == "getUpdates":
            res = self.updates_seq.pop(0) if len(self.updates_seq) > 1 else self.updates_seq[0]
            return httpx.Response(200, json={"ok": True, "result": res})
        if method == "sendMessage":
            self.sent.append(body)
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(404, json={"ok": False})


def msg(chat_id, name="Dana", ctype="private"):
    return {"update_id": 1, "message": {"chat": {"id": chat_id, "type": ctype, "first_name": name}, "text": "/start"}}


def test_full_flow_waits_for_message_then_finds_chat():
    fake = FakeTelegram([[], [], [msg(4242)]])
    ts = TelegramSetup(TOKEN, transport=httpx.MockTransport(fake), sleep=lambda s: None)
    assert ts.bot_username() == "pokewatch_test_bot"
    assert ts.find_chat(wait_s=30) == ("4242", "Dana")
    ts.send_test("4242")
    assert fake.sent[0]["chat_id"] == "4242" and "connected" in fake.sent[0]["text"]


def test_ignores_group_chats():
    fake = FakeTelegram([[msg(-100, ctype="group"), msg(7)]])
    ts = TelegramSetup(TOKEN, transport=httpx.MockTransport(fake), sleep=lambda s: None)
    assert ts.find_chat()[0] == "7"


def test_times_out_with_clear_message():
    ts = TelegramSetup(TOKEN, transport=httpx.MockTransport(FakeTelegram([[]])), sleep=lambda s: None)
    with pytest.raises(SetupError, match="tap Start"):
        ts.find_chat(wait_s=6, poll_every=3)


def test_bad_token_shape_and_rejected_token():
    with pytest.raises(SetupError, match="doesn't look like a bot token"):
        TelegramSetup("hello")
    ts = TelegramSetup(TOKEN, transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"})))
    with pytest.raises(SetupError, match="rejected the token"):
        ts.bot_username()


def test_set_env_values_replaces_and_appends(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nTELEGRAM_BOT_TOKEN=\nDISCORD_WEBHOOK_URL=\n")
    set_env_values(env, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42"})
    assert env.read_text() == "# comment\nTELEGRAM_BOT_TOKEN=t\nDISCORD_WEBHOOK_URL=\nTELEGRAM_CHAT_ID=42\n"


def test_cli_end_to_end(tmp_path, monkeypatch, capsys):
    """Run the real CLI command with a fake Telegram and a temp .env."""
    from pokewatch import cli, config, telegram_setup
    fake = FakeTelegram([[msg(99, "Sam")]])
    real_init = telegram_setup.TelegramSetup.__init__
    monkeypatch.setattr(telegram_setup.TelegramSetup, "__init__",
                        lambda self, token, transport=None, sleep=None: real_init(
                            self, token, transport=httpx.MockTransport(fake), sleep=lambda s: None))
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": TOKEN)
    cli.main(["telegram-setup"])
    out = capsys.readouterr().out
    assert "@pokewatch_test_bot" in out and "Connected to Sam's chat" in out
    env = (tmp_path / ".env").read_text()
    assert f"TELEGRAM_BOT_TOKEN={TOKEN}" in env and "TELEGRAM_CHAT_ID=99" in env
    assert fake.sent
