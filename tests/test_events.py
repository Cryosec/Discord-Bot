"""Tests for the audit-log and join handlers in cogs/events.py (no Discord connection)."""
import asyncio
import types
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs import events

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
    monkeypatch.setattr(events, "check_jac", check)
    message = MagicMock()
    message.type = discord.MessageType.new_member
    message.author = _user(5, "newbie")
    message.author.bot = False
    asyncio.run(cog.on_message(message))
    cog.database.addNewUser.assert_called_once_with("5")
    check.assert_not_awaited()


def _raw_entry(action_type, options=None, user_id="2"):
    """Real py-cord payload of GUILD_AUDIT_LOG_ENTRY_CREATE."""
    data = {"id": "1", "guild_id": "99", "user_id": user_id, "target_id": "1",
            "action_type": action_type}
    if options:
        data["options"] = options
    return discord.raw_models.RawAuditLogEntryEvent(data)


def test_automod_timeout_is_logged(monkeypatch):
    cog, channel, _, _ = _cog()
    view = MagicMock()
    view.wait = AsyncMock()
    view.value = False
    monkeypatch.setattr(events.support, "Untimeout", lambda: view)
    options = {"auto_moderation_rule_name": "LF scam", "auto_moderation_rule_trigger_type": "1",
               "channel_id": "7"}
    asyncio.run(cog.on_raw_audit_log_entry(_raw_entry(145, options)))
    embed = channel.send.await_args.kwargs["embed"]
    assert embed.title == "User timeout issued"
    assert "AutoMod" in embed.description
    assert {f.name: f.value for f in embed.fields}["Reason"] == "AutoMod rule: LF scam"


def test_real_kick_payload_is_handled():
    cog, channel, _, _ = _cog()
    asyncio.run(cog.on_raw_audit_log_entry(_raw_entry(20)))
    assert channel.send.await_args.kwargs["embed"].title == "User Kick"


def _message(author_id=5, channel_id=None):
    message = MagicMock()
    message.type = discord.MessageType.default
    message.author = _user(author_id, "poster")
    message.author.bot = False
    message.author.roles = []
    message.webhook_id = None
    message.content = ""  # no MESSAGE_CONTENT intent
    message.channel.id = channel_id if channel_id is not None else events.config.CLAN_CHAN
    message.channel.send = AsyncMock()
    message.delete = AsyncMock()
    message.guild.get_role.return_value = MagicMock()
    message.guild.get_channel.return_value.send = AsyncMock()
    message.guild.kick = AsyncMock()
    return message


def test_jac_first_post_is_recorded_without_content():
    cog, _, _, _ = _cog()
    cog.database.getJacByID.return_value = []
    message = _message()
    asyncio.run(events.check_jac(cog, message))
    args = cog.database.addJac.call_args.args
    assert args[0] == "5"
    message.delete.assert_not_awaited()


def test_jac_second_post_is_removed_and_warned():
    cog, _, _, _ = _cog()
    cog.database.getJacByID.return_value = [{"user_id": "5", "link": "x", "date": "d"}]
    cog.database.getWarnUserByID.return_value = None
    message = _message()
    asyncio.run(events.check_jac(cog, message))
    message.delete.assert_awaited_once()
    cog.database.addWarning.assert_called_once()
    cog.database.addJac.assert_not_called()


def test_jac_kick_is_stored_once_by_the_audit_log_handler():
    cog, _, _, _ = _cog()
    cog.database.getJacByID.return_value = [{"user_id": "5", "link": "x", "date": "d"}]
    cog.database.getWarnUserByID.return_value = {"user_id": "5", "warnings": 1}
    cog.database.getWarnCount.return_value = 2
    message = _message()
    message.author.send = AsyncMock()
    asyncio.run(events.check_jac(cog, message))
    message.guild.kick.assert_awaited_once()
    # on_raw_audit_log_entry -> log_kick -> addKick stores the kick
    cog.database.addKick.assert_not_called()


def test_on_message_has_no_content_filters_left():
    for name in ("check_invites", "check_scam", "check_spam_v2", "check_blacklist",
                 "check_msg_link", "check_new_member_links", "scam_check_embed"):
        assert not hasattr(events, name), name


def test_jac_check_reads_only_the_author_rows():
    cog, _, _, _ = _cog()
    cog.database.getJacByID.return_value = []
    asyncio.run(events.check_jac(cog, _message()))
    cog.database.getJacByID.assert_called_once_with("5")
    cog.database.getJac.assert_not_called()


def test_jac_webhook_message_is_ignored():
    """A webhook author is a User without roles."""
    cog, _, _, _ = _cog()
    message = _message()
    message.webhook_id = 123
    del message.author.roles
    asyncio.run(events.check_jac(cog, message))
    cog.database.getJacByID.assert_not_called()


def test_kick_without_reason_stores_a_default_reason():
    cog, channel, _, _ = _cog()
    asyncio.run(cog.on_raw_audit_log_entry(_payload(discord.AuditLogAction.kick, reason=None)))
    cog.database.addKick.assert_called_once_with("1", "target", "Kick: No reason specified")
    fields = {f.name: f.value for f in channel.send.await_args.kwargs["embed"].fields}
    assert fields["Reason"] == "Kick: No reason specified"


def test_logs_work_with_the_default_bot_avatar():
    """bot.user.avatar is None without a custom avatar: use display_avatar."""
    cog, channel, _, _ = _cog()
    cog.bot.user.avatar = None
    cog.bot.user.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    asyncio.run(cog.on_raw_audit_log_entry(_payload(discord.AuditLogAction.kick)))
    changes = [{"key": "communication_disabled_until", "old_value": TS, "new_value": None}]
    asyncio.run(cog.on_raw_audit_log_entry(
        _payload(discord.AuditLogAction.member_update, changes)))
    for call in channel.send.await_args_list:
        assert call.kwargs["embed"].author.icon_url == cog.bot.user.display_avatar.url


def _audit_entries(*entries):
    async def gen(limit=100, **kwargs):
        for entry in entries[:limit]:
            yield entry
    return gen


def _ban_setup(monkeypatch, reason, entries):
    cog, channel, guild, _ = _cog()
    target = _user(1, "target")
    guild.fetch_ban = AsyncMock(return_value=MagicMock(reason=reason))
    guild.audit_logs = _audit_entries(*entries)
    guild.unban = AsyncMock()
    view = MagicMock()
    view.wait = AsyncMock()
    view.value = True
    view.inter.edit_original_message = AsyncMock()
    monkeypatch.setattr(events.support, "Unban", lambda: view)
    asyncio.run(cog.on_member_ban(guild, target))
    return cog, channel


def test_unban_button_removes_the_stored_ban_reason(monkeypatch):
    """delBan must get the text that addBan stored, also without a ban reason."""
    cog, _ = _ban_setup(monkeypatch, None, [])
    stored = cog.database.addBan.call_args.args[2]
    assert stored == "Ban: No reason Specified"
    cog.database.delBan.assert_called_once_with("1", stored)


def test_ban_author_is_found_among_recent_entries(monkeypatch):
    """Another ban can be the newest audit log entry."""
    other = MagicMock(target=MagicMock(id=9), user="someone else")
    ours = MagicMock(target=MagicMock(id=1), user="mod")
    _, channel = _ban_setup(monkeypatch, "spam", [other, ours])
    assert channel.send.await_args.kwargs["embed"].description.endswith("by mod.")


def _bot_timeout(cog, reason):
    """Audit entry of a timeout whose author is the bot itself (user id 2)."""
    cog.bot.user.id = 2
    changes = [{"key": "communication_disabled_until", "new_value": TS}]
    return _payload(discord.AuditLogAction.member_update, changes, reason=reason)


def test_bot_review_timeout_is_not_logged_twice(monkeypatch):
    cog, channel, _, _ = _cog()
    monkeypatch.setattr(events.config, "HONEYPOT_REASON", "Honeypot hit", raising=False)
    for reason in (events.support.AUTOMOD_REVIEW_REASON, "Honeypot hit"):
        asyncio.run(cog.on_raw_audit_log_entry(_bot_timeout(cog, reason)))
    channel.send.assert_not_awaited()


def test_bot_timeout_command_keeps_its_embed(monkeypatch):
    cog, channel, _, _ = _cog()
    view = MagicMock()
    view.wait = AsyncMock()
    view.value = False
    monkeypatch.setattr(events.support, "Untimeout", lambda: view)
    asyncio.run(cog.on_raw_audit_log_entry(_bot_timeout(cog, "spamming")))
    asyncio.run(cog.on_raw_audit_log_entry(_bot_timeout(cog, None)))
    assert channel.send.await_count == 2


def test_mod_timeout_with_a_review_reason_keeps_its_embed(monkeypatch):
    cog, channel, _, _ = _cog()
    cog.bot.user.id = 999  # the author (id 2) is a mod, not the bot
    view = MagicMock()
    view.wait = AsyncMock()
    view.value = False
    monkeypatch.setattr(events.support, "Untimeout", lambda: view)
    changes = [{"key": "communication_disabled_until", "new_value": TS}]
    asyncio.run(cog.on_raw_audit_log_entry(_payload(
        discord.AuditLogAction.member_update, changes,
        reason=events.support.AUTOMOD_REVIEW_REASON)))
    channel.send.assert_awaited_once()
