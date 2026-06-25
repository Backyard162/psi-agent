from __future__ import annotations

import pytest

from psi_agent.channel.telegram import ChannelTelegram


def test_channel_telegram_defaults():
    ct = ChannelTelegram(session_socket="/tmp/chan.sock")
    assert ct.session_socket == "/tmp/chan.sock"
    assert ct.bot_token == ""
    assert ct.interval == 1.0
    assert ct.allowed_user_ids is None
    assert ct.verbose is False


def test_channel_telegram_with_whitelist():
    ct = ChannelTelegram(
        session_socket="/tmp/chan.sock",
        bot_token="abc",
        interval=0.5,
        allowed_user_ids=[123, 456],
        verbose=True,
    )
    assert ct.bot_token == "abc"
    assert ct.interval == 0.5
    assert ct.allowed_user_ids == [123, 456]
    assert ct.verbose is True


@pytest.mark.anyio
async def test_run_raises_on_missing_token():
    ct = ChannelTelegram(session_socket="/tmp/chan.sock")
    with pytest.raises(ValueError, match="No Telegram bot token"):
        await ct.run()
