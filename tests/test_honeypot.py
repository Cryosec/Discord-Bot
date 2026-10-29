"""Tests for the manual review and the purge in cogs/honeypot.py (no Discord connection)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from cogs import honeypot


def _review_message():
    message = MagicMock()
    message.content = "SECRET-CONTENT"
    message.channel.mention = "#trap"
    message.author.mention = "@spammer"
    message.author.joined_at.strftime.return_value = "joined"
    message.author.created_at.strftime.return_value = "created"
    message.author.ban = AsyncMock()
    message.author.remove_timeout = AsyncMock()
    log_channel = MagicMock()
    review = MagicMock()
    review.edit = AsyncMock()
    log_channel.send = AsyncMock(return_value=review)
    message.guild.get_channel.return_value = log_channel
    return message, log_channel, review


def _patch_view(monkeypatch, value):
    class FakeView:
        def __init__(self):
            self.value = value
            self.user = "mod"

        async def wait(self):
            return True

    monkeypatch.setattr(honeypot, "HoneypotReview", FakeView)


def test_review_embed_has_no_message_field(monkeypatch):
    _patch_view(monkeypatch, False)
    message, log_channel, review = _review_message()
    asyncio.run(honeypot.honeypot_review_embed(MagicMock(), message, {"general": 2}))

    first = log_channel.send.await_args.kwargs["embed"]
    done = review.edit.await_args.kwargs["embed"]
    for embed in (first, done):
        assert "Message" not in [f.name for f in embed.fields]
        assert "SECRET-CONTENT" not in str(embed.to_dict())
    assert [f.name for f in first.fields][:2] == ["Channel", "Author"]
    assert "Deleted messages" in [f.name for f in first.fields]
    assert [f.name for f in done.fields] == ["Author", "Result"]


def test_purge_logs_count_not_content(monkeypatch):
    monkeypatch.setattr(honeypot.config, "HONEYPOT_PURGE_SECONDS", 60, raising=False)
    monkeypatch.setattr(honeypot.config, "HONEYPOT_PURGE_LIMIT", 10, raising=False)
    msg = MagicMock()
    msg.content = "SECRET-CONTENT"
    channel = MagicMock()
    channel.name = "general"
    channel.permissions_for.return_value = MagicMock(
        manage_messages=True, read_message_history=True)
    channel.purge = AsyncMock(return_value=[msg, msg])
    guild = MagicMock()
    guild.text_channels = [channel]
    guild.threads = []
    member = MagicMock()
    member.id = 5
    log = MagicMock()
    monkeypatch.setattr(honeypot, "log", log)

    result = asyncio.run(honeypot.purge_user_messages(guild, member))

    assert result == {"general": 2}
    logged = str(log.info.call_args_list)
    assert "SECRET-CONTENT" not in logged
    assert "2" in logged
