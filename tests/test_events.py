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
    bot.is_ready.return_value = False
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


def test_timeout_is_logged_with_persistent_undo_button():
    cog, channel, _, member = _cog()
    changes = [{"key": "communication_disabled_until", "new_value": TS}]
    asyncio.run(asyncio.wait_for(cog.on_raw_audit_log_entry(
        _payload(discord.AuditLogAction.member_update, changes)), 1))  # returns: no wait()
    kwargs = channel.send.await_args.kwargs
    fields = {f.name: f.value for f in kwargs["embed"].fields}
    assert kwargs["embed"].title == "User timeout issued"
    assert isinstance(kwargs["view"], events.UntimeoutView)
    assert fields["User ID"] == "1"
    assert fields["Timeout until"] == TS
    member.remove_timeout.assert_not_awaited()  # only the button does it


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
    options = {"auto_moderation_rule_name": "LF scam", "auto_moderation_rule_trigger_type": "1",
               "channel_id": "7"}
    asyncio.run(cog.on_raw_audit_log_entry(_raw_entry(145, options)))
    embed = channel.send.await_args.kwargs["embed"]
    assert embed.title == "User timeout issued"
    assert "AutoMod" in embed.description
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Reason"] == "AutoMod rule: LF scam"
    # No audit changes for the AutoMod TIMEOUT action: no end in the embed
    assert fields["User ID"] == "1"
    assert "Timeout until" not in fields
    assert isinstance(channel.send.await_args.kwargs["view"], events.UntimeoutView)


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
    asyncio.run(asyncio.wait_for(cog.on_member_ban(guild, target), 1))  # returns: no wait()
    return cog, channel, guild


def test_ban_embed_shows_the_stored_reason_and_the_user_id(monkeypatch):
    """Without a reason the embed shows the text addBan stored, not None."""
    cog, channel, _ = _ban_setup(monkeypatch, None, [])
    stored = cog.database.addBan.call_args.args[2]
    assert stored == "Ban: No reason Specified"
    kwargs = channel.send.await_args.kwargs
    fields = {f.name: f.value for f in kwargs["embed"].fields}
    assert fields["Reason"] == stored
    assert fields["User ID"] == "1"
    assert isinstance(kwargs["view"], events.UnbanView)


def test_ban_author_is_found_among_recent_entries(monkeypatch):
    """Another ban can be the newest audit log entry."""
    other = MagicMock(target=MagicMock(id=9), user="someone else")
    ours = MagicMock(target=MagicMock(id=1), user="mod")
    _, channel, _ = _ban_setup(monkeypatch, "spam", [other, ours])
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
    asyncio.run(cog.on_raw_audit_log_entry(_bot_timeout(cog, "spamming")))
    asyncio.run(cog.on_raw_audit_log_entry(_bot_timeout(cog, None)))
    assert channel.send.await_count == 2


def test_mod_timeout_with_a_review_reason_keeps_its_embed(monkeypatch):
    cog, channel, _, _ = _cog()
    cog.bot.user.id = 999  # the author (id 2) is a mod, not the bot
    changes = [{"key": "communication_disabled_until", "new_value": TS}]
    asyncio.run(cog.on_raw_audit_log_entry(_payload(
        discord.AuditLogAction.member_update, changes,
        reason=events.support.AUTOMOD_REVIEW_REASON)))
    channel.send.assert_awaited_once()


# --- Persistent buttons -------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402


def _http_error(cls, text="x"):
    return cls(MagicMock(status=400), text)


def _ban_embed(reason="spam", user_id=1):
    embed = discord.Embed(title="User Ban", description="banned")
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="User ID", value=str(user_id))
    return embed


def _timeout_embed(until=None, user_id=1):
    embed = discord.Embed(title="User timeout issued", description="timed out")
    embed.add_field(name="User ID", value=str(user_id))
    if until is not None:
        embed.add_field(name="Timeout until", value=until)
    return embed


def _ban_env(make_press, ban_reason="spam", embed_reason="spam"):
    cog, _, guild, _ = _cog()
    guild.fetch_ban = AsyncMock(return_value=MagicMock(reason=ban_reason))

    async def unban(*args, **kwargs):
        await asyncio.sleep(0)  # yield, so concurrent presses really interleave

    guild.unban = AsyncMock(side_effect=unban)
    press = make_press.build(guild, _ban_embed(embed_reason))
    return cog, guild, press


def test_views_are_persistent_with_fixed_custom_ids():
    async def run():
        cog, _, _, _ = _cog()
        unban, undo = events.UnbanView(cog), events.UntimeoutView(cog)
        assert unban.is_persistent() and undo.is_persistent()
        assert [i.custom_id for i in unban.children] == ["lf:unban"]
        assert [i.custom_id for i in undo.children] == ["lf:untimeout"]
    asyncio.run(run())


def test_views_are_registered_on_ready_and_on_load_when_ready():
    async def run():
        cog, _, _, _ = _cog()
        cog.bot.add_view.assert_not_called()
        await cog.on_ready()
        assert {type(c.args[0]) for c in cog.bot.add_view.call_args_list} == {
            events.UnbanView, events.UntimeoutView}
        assert all(len(c.args) == 1 for c in cog.bot.add_view.call_args_list)  # no message_id
        late = MagicMock()
        late.is_ready.return_value = True  # cogwatch reload while the bot runs
        events.Events(late)
        assert late.add_view.call_count == 2
    asyncio.run(run())


def test_unban_button_unbans_edits_and_removes_the_db_ban(make_press):
    cog, guild, press = _ban_env(make_press)
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction)
    assert guild.unban.await_args.args[0].id == 1
    cog.database.delBan.assert_called_once_with("1", "spam")
    kwargs = press.message.edit.await_args.kwargs
    assert kwargs["view"] is None
    assert kwargs["embed"].title == "User ban - canceled"
    assert "mod#1" in kwargs["embed"].description
    press.interaction.response.defer.assert_awaited_once()
    assert make_press.answers(press.interaction) == ["Unbanned."]
    assert press.message.id not in cog.review_locks  # lock dropped


def test_unban_without_a_reason_gives_delban_the_stored_text(make_press):
    cog, guild, press = _ban_env(make_press, ban_reason=None,
                                 embed_reason="Ban: No reason Specified")
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction)
    cog.database.delBan.assert_called_once_with("1", "Ban: No reason Specified")


def test_non_mod_cannot_press_unban(make_press):
    cog, guild, press = _ban_env(make_press)
    other = make_press.build(guild, _ban_embed(), mod=False)
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", other.interaction)
    guild.unban.assert_not_awaited()
    cog.database.delBan.assert_not_called()
    other.interaction.response.defer.assert_not_awaited()
    assert "moderators" in make_press.answers(other.interaction)[0]
    assert other.interaction.response.send_message.await_args.kwargs["ephemeral"] is True


def test_unban_pressed_twice_acts_once(make_press):
    cog, guild, press = _ban_env(make_press)
    second = make_press.build(guild, _ban_embed())
    second.interaction.channel.fetch_message = press.interaction.channel.fetch_message
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction, second.interaction)
    guild.unban.assert_awaited_once()
    cog.database.delBan.assert_called_once()
    assert make_press.answers(second.interaction) == ["This review was already handled."]


def test_old_unban_after_a_newer_ban_with_another_reason_does_nothing(make_press):
    cog, guild, press = _ban_env(make_press, ban_reason="newer ban", embed_reason="old ban")
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction)
    guild.unban.assert_not_awaited()
    cog.database.delBan.assert_not_called()
    press.message.edit.assert_not_awaited()
    assert "newer ban" in make_press.answers(press.interaction)[0]


def test_unban_when_not_banned_any_more_changes_nothing(make_press):
    cog, guild, press = _ban_env(make_press)
    guild.fetch_ban.side_effect = _http_error(discord.NotFound)
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction)
    guild.unban.assert_not_awaited()
    cog.database.delBan.assert_not_called()
    assert "not banned" in make_press.answers(press.interaction)[0]


def test_unban_notfound_from_the_unban_call_changes_nothing(make_press):
    cog, guild, press = _ban_env(make_press)
    guild.unban.side_effect = _http_error(discord.NotFound)
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction)
    cog.database.delBan.assert_not_called()
    press.message.edit.assert_not_awaited()


def test_failed_unban_keeps_the_buttons(make_press):
    cog, guild, press = _ban_env(make_press)
    guild.unban.side_effect = _http_error(discord.Forbidden, "missing perms")
    make_press.click(lambda: events.UnbanView(cog), "lf:unban", press.interaction)
    cog.database.delBan.assert_not_called()
    press.message.edit.assert_not_awaited()
    assert press.message.components  # still open
    assert "missing perms" in make_press.answers(press.interaction)[0]


def test_db_error_after_unban_closes_the_message_and_tells_the_mod(make_press):
    cog, guild, press = _ban_env(make_press)
    cog.database.delBan.side_effect = RuntimeError("db down")
    second = make_press.build(guild, _ban_embed())
    second.interaction.channel.fetch_message = press.interaction.channel.fetch_message
    make_view = lambda: events.UnbanView(cog)  # noqa: E731
    make_press.click(make_view, "lf:unban", press.interaction)
    assert press.message.edit.await_args.kwargs["view"] is None
    assert "dashboard" in make_press.answers(press.interaction)[0]
    make_press.click(make_view, "lf:unban", second.interaction)  # no second delBan
    cog.database.delBan.assert_called_once()
    guild.unban.assert_awaited_once()


def test_edit_error_after_unban_is_told_and_the_db_is_still_updated(make_press):
    cog, guild, press = _ban_env(make_press)
    press.message.edit.side_effect = _http_error(discord.HTTPException)
    make_view = lambda: events.UnbanView(cog)  # noqa: E731
    make_press.click(make_view, "lf:unban", press.interaction)
    cog.database.delBan.assert_called_once_with("1", "spam")
    assert "could not be updated" in make_press.answers(press.interaction)[0]
    # The message is still open: the next press sees the state through fetch_ban
    guild.fetch_ban.side_effect = _http_error(discord.NotFound)
    again = make_press.build(guild, _ban_embed())
    make_press.click(make_view, "lf:unban", again.interaction)
    cog.database.delBan.assert_called_once()


def _undo_env(make_press, until, current):
    cog, _, guild, member = _cog()
    member.communication_disabled_until = current
    press = make_press.build(guild, _timeout_embed(until))
    return cog, guild, member, press


FUTURE = datetime.now(timezone.utc) + timedelta(days=1)


def test_undo_button_removes_the_timeout_and_closes_the_message(make_press):
    cog, guild, member, press = _undo_env(make_press, FUTURE.isoformat(), FUTURE)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    guild.fetch_member.assert_awaited_once_with(1)
    member.remove_timeout.assert_awaited_once_with(reason="Timeout removed")
    kwargs = press.message.edit.await_args.kwargs
    assert kwargs["view"] is None
    assert kwargs["embed"].title == "User timeout - removed"


def test_undo_compares_datetimes_not_strings(make_press):
    """The audit value can end with Z or use another offset: same instant, same timeout."""
    until = FUTURE.replace(microsecond=0)
    text = until.astimezone(timezone(timedelta(hours=2))).isoformat()
    cog, _, member, press = _undo_env(make_press, text, until)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_awaited_once()
    z = until.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    cog, _, member, press = _undo_env(make_press, z, until)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_awaited_once()


def test_old_undo_after_a_newer_timeout_does_nothing(make_press):
    cog, _, member, press = _undo_env(
        make_press, FUTURE.isoformat(), FUTURE + timedelta(days=6))
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_not_awaited()
    press.message.edit.assert_not_awaited()
    assert "already changed" in make_press.answers(press.interaction)[0]


def test_undo_when_the_timeout_is_gone_does_nothing(make_press):
    cog, _, member, press = _undo_env(make_press, FUTURE.isoformat(), None)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_not_awaited()


def test_undo_when_the_user_left(make_press):
    cog, guild, member, press = _undo_env(make_press, FUTURE.isoformat(), FUTURE)
    guild.fetch_member.side_effect = _http_error(discord.NotFound)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_not_awaited()
    assert "left" in make_press.answers(press.interaction)[0]


def test_undo_without_an_end_only_checks_that_the_member_is_timed_out(make_press):
    """AutoMod TIMEOUT action: the audit entry has no changes, so no end in the embed."""
    cog, _, member, press = _undo_env(make_press, None, FUTURE)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_awaited_once()
    cog, _, member, press = _undo_env(make_press, None, None)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    member.remove_timeout.assert_not_awaited()


def test_non_mod_cannot_press_undo(make_press):
    cog, guild, member, _ = _undo_env(make_press, None, FUTURE)
    other = make_press.build(guild, _timeout_embed(), mod=False)
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", other.interaction)
    member.remove_timeout.assert_not_awaited()


def test_failed_remove_timeout_keeps_the_buttons(make_press):
    cog, _, member, press = _undo_env(make_press, None, FUTURE)
    member.remove_timeout.side_effect = _http_error(discord.Forbidden, "no")
    make_press.click(lambda: events.UntimeoutView(cog), "lf:untimeout", press.interaction)
    press.message.edit.assert_not_awaited()
    assert press.message.components
