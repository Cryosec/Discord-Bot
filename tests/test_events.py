"""Tests for the audit-log and join handlers in cogs/events.py (no Discord connection)."""
import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import discord

# cogs.database needs the mariadb driver and a live DB: replace it with a stub.
_db_stub = types.ModuleType("cogs.database")
_db_stub.Database = lambda bot: MagicMock()
sys.modules.setdefault("cogs.database", _db_stub)

from cogs import events  # noqa: E402

TS = "2026-10-29T18:00:00+00:00"


def _user(uid, name):
    user = MagicMock()
    user.id = uid
    user.name = name
    user.discriminator = "0"
    user.__str__ = lambda self: name
    return user


def _cog():
    bot = MagicMock()
    target, author = _user(1, "target"), _user(2, "mod")
    bot.get_user.side_effect = {1: target, 2: author}.get
    channel = MagicMock()
    channel.send = AsyncMock()
    guild = MagicMock()
    guild.get_channel.return_value = channel
    member = MagicMock()
    member.remove_timeout = AsyncMock()
    guild.fetch_member = AsyncMock(return_value=member)
    bot.get_guild.return_value = guild
    cog = events.Events(bot)
    cog.database = MagicMock()
    return cog, channel, guild, member


def _payload(action, changes=None, reason="because"):
    return types.SimpleNamespace(
        action_type=action, guild_id=99, user_id=2, target_id=1,
        reason=reason, changes=changes,
    )


def test_kick_is_logged_and_stored():
    cog, channel, _, _ = _cog()
    asyncio.run(cog.on_raw_audit_log_entry(_payload(discord.AuditLogAction.kick)))
    embed = channel.send.await_args.kwargs["embed"]
    assert embed.title == "User Kick"
    assert "kicked from the server by mod" in embed.description
    cog.database.addKick.assert_called_once_with("1", "target", "because")


def test_timeout_is_logged_with_undo_button(monkeypatch):
    cog, channel, _, member = _cog()
    view = MagicMock()
    view.wait = AsyncMock()
    view.value = True
    monkeypatch.setattr(events.support, "Untimeout", lambda: view)
    changes = [{"key": "communication_disabled_until", "new_value": TS}]
    asyncio.run(cog.on_raw_audit_log_entry(
        _payload(discord.AuditLogAction.member_update, changes)))
    kwargs = channel.send.await_args.kwargs
    assert kwargs["embed"].title == "User timeout issued"
    assert kwargs["view"] is view
    member.remove_timeout.assert_awaited_once()


def test_timeout_removed_is_logged():
    cog, channel, _, _ = _cog()
    changes = [{"key": "communication_disabled_until", "old_value": TS, "new_value": None}]
    asyncio.run(cog.on_raw_audit_log_entry(
        _payload(discord.AuditLogAction.member_update, changes)))
    assert channel.send.await_args.kwargs["embed"].title == "User timeout removed"


def test_unrelated_entries_are_ignored():
    cog, channel, _, _ = _cog()
    changes = [{"key": "nick", "old_value": "a", "new_value": "b"}]
    asyncio.run(cog.on_raw_audit_log_entry(
        _payload(discord.AuditLogAction.member_update, changes)))
    asyncio.run(cog.on_raw_audit_log_entry(_payload(discord.AuditLogAction.channel_create)))
    channel.send.assert_not_awaited()
    cog.database.addKick.assert_not_called()


def test_join_message_adds_member_and_skips_filters(monkeypatch):
    cog, _, _, _ = _cog()
    check = AsyncMock()
    monkeypatch.setattr(events, "check_invites", check)
    message = MagicMock()
    message.type = discord.MessageType.new_member
    message.author = _user(5, "newbie")
    message.author.bot = False
    asyncio.run(cog.on_message(message))
    cog.database.addNewUser.assert_called_once_with("5")
    check.assert_not_awaited()
