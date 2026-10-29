"""Tests for the slash command fixes and the cog smoke load (no Discord connection)."""
import asyncio
import importlib
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands

import bot_setup
from cogs import moderation_slash

users_slash = importlib.import_module("cogs.users-slash")


def _ctx():
    ctx = MagicMock()
    ctx.respond = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


def _mod_cog():
    cog = moderation_slash.ModerationSlash(MagicMock())
    cog.database = MagicMock()
    return cog


def test_all_extensions_load_with_the_final_intents():
    intents = bot_setup.build_intents()
    assert intents.members is False
    assert intents.message_content is False
    assert intents.presences is False
    assert intents.auto_moderation_execution is True
    assert intents.moderation is True

    async def load():
        bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)
        for extension in bot_setup.INIT_EXTENSIONS:
            bot.load_extension(extension)
        return bot

    bot = asyncio.run(load())
    assert {"AutoMod", "Events", "ModerationSlash", "UsersSlash", "Jac"} <= set(bot.cogs)
    prefix = {c.name for c in bot.commands}
    removed = {"ping", "lundy", "toxy", "floppa", "avyy", "lotto", "tim", "help"}
    assert not prefix & removed
    assert {"load", "unload", "reload", "reconf"} <= prefix  # owner admin commands stay
    assert "cogs.automod" in bot_setup.INIT_EXTENSIONS


def test_moderation_commands_are_hidden_from_non_mods():
    cog = _mod_cog()
    commands_ = cog.get_commands()
    assert commands_
    for command in commands_:
        assert command.default_member_permissions == moderation_slash.MOD_PERMISSIONS, command.name


def test_kick_moderator_is_refused_with_respond():
    cog = _mod_cog()
    ctx = _ctx()
    member = MagicMock()
    member.roles = [ctx.guild.get_role.return_value]
    asyncio.run(cog.kick_user.callback(cog, ctx, member, "x"))
    ctx.respond.assert_awaited_once()
    ctx.send.assert_not_awaited()
    ctx.guild.kick.assert_not_called()


def test_tempban_bad_duration_uses_respond():
    cog = _mod_cog()
    ctx = _ctx()
    ctx.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    asyncio.run(cog.tempban_user.callback(cog, ctx, MagicMock(id=1), "soon", "x"))
    ctx.respond.assert_awaited_once()
    ctx.send.assert_not_awaited()


def _status(member_found):
    cog = _mod_cog()
    cog.database.getWarnUserByID.return_value = None  # fetchone: no row
    cog.database.getWarnReasons.return_value = []
    user = MagicMock(id=1)
    cog.bot.fetch_user = AsyncMock(return_value=user)
    ctx = _ctx()
    if member_found:
        ctx.guild.fetch_member = AsyncMock(return_value=MagicMock(premium_since=None, roles=[]))
    else:
        ctx.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    asyncio.run(cog.status.callback(cog, ctx, user))
    return ctx.respond.await_args.kwargs["embed"]


def test_status_user_without_infractions():
    assert _status(True).description == "No warnings issued."
    assert _status(False).description == "**User is not part of the server.**"


def test_status_lists_reasons():
    cog = _mod_cog()
    cog.database.getWarnUserByID.return_value = {"warnings": 1, "kicks": 0, "bans": 0}
    cog.database.getWarnReasons.return_value = [{"id": 3, "reason": "spam"}]
    cog.bot.fetch_user = AsyncMock(return_value=MagicMock(id=1))
    ctx = _ctx()
    ctx.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    asyncio.run(cog.status.callback(cog, ctx, MagicMock(id=1)))
    assert ctx.respond.await_args.kwargs["embed"].description.endswith("0: spam")


def test_timers_reads_dict_rows():
    cog = _mod_cog()
    cog.database.getTimers.return_value = [
        {"user_id": "1", "ban": 1, "mute": 0, "endBan": "Oct-30-2026 10:00:00", "endMute": None}]
    cog.bot.fetch_user = AsyncMock(return_value=MagicMock(mention="<@1>"))
    ctx = _ctx()
    asyncio.run(cog.show_timers.callback(cog, ctx))
    description = ctx.respond.await_args.kwargs["embed"].description
    assert "<@1>" in description and "Oct-30-2026 10:00:00" in description


def _users_cog():
    return users_slash.UsersSlash(MagicMock())


def test_faq_responds():
    cog = _users_cog()
    ctx = _ctx()
    asyncio.run(cog.faq.callback(cog, ctx))
    ctx.respond.assert_awaited_once()
    ctx.send.assert_not_awaited()


def test_me_with_default_avatar():
    cog = _users_cog()
    ctx = _ctx()
    member = ctx.author
    member.id = -1
    member.avatar = None  # default avatar
    member.colour = 0
    member.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    member.premium_since = None
    member.roles = []
    asyncio.run(cog.me.callback(cog, ctx))
    embed = ctx.respond.await_args.kwargs["embed"]
    assert embed.thumbnail.url == member.display_avatar.url


def test_jac_info_moved_to_the_jac_group():
    assert "jac" not in {c.name for c in _mod_cog().get_commands()}


def test_parse_duration():
    assert moderation_slash.parse_duration("1h30m") == (
        timedelta(hours=1, minutes=30), "1 hours 30 minutes")
    assert moderation_slash.parse_duration("2days") == (timedelta(days=2), "2 days")
    assert moderation_slash.parse_duration("soon") is None


def _member(uid=7):
    member = MagicMock(id=uid, mention=f"<@{uid}>")
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    member.send = AsyncMock()
    return member


def _timer_cog(monkeypatch, row=None):
    """Cog whose getTimers returns `row`, or the timer that the command stored."""
    cog = _mod_cog()
    sleep = AsyncMock()
    monkeypatch.setattr(moderation_slash.asyncio, "sleep", sleep)

    def timers():
        if row is not None:
            return [row]
        stored = cog.database.addTimerMute.call_args or cog.database.addTimerBan.call_args
        user_id, end = stored.args
        mute = cog.database.addTimerMute.call_args is not None
        return [{"user_id": user_id, "ban": int(not mute), "mute": int(mute),
                 "endBan": None if mute else end, "endMute": end if mute else None}]

    cog.database.getTimers.side_effect = timers
    cog.database.addTimerMute.call_args = None
    cog.database.addTimerBan.call_args = None
    ctx = _ctx()
    ctx.guild.get_channel.return_value.send = AsyncMock()
    ctx.guild.ban = AsyncMock()
    ctx.guild.unban = AsyncMock()
    return cog, ctx, sleep


def test_mute_duration_with_an_a_is_not_indefinite(monkeypatch):
    """'2days' contains an 'a': it was an indefinite mute."""
    cog, ctx, sleep = _timer_cog(monkeypatch)
    member = _member()
    asyncio.run(cog.mute.callback(cog, ctx, member, "2days"))
    cog.database.addTimerMute.assert_called_once()
    sleep.assert_awaited_once_with(2 * 86400)
    member.remove_roles.assert_awaited_once()
    cog.database.delTimer.assert_called_once_with("7")


def test_mute_default_is_indefinite(monkeypatch):
    cog, ctx, sleep = _timer_cog(monkeypatch)
    member = _member()
    asyncio.run(cog.mute.callback(cog, ctx, member, "a"))
    member.add_roles.assert_awaited_once()
    cog.database.addTimerMute.assert_not_called()
    sleep.assert_not_awaited()


def test_mute_end_keeps_a_running_tempban(monkeypatch):
    """One row holds both timers: delTimer would also delete the ban timer."""
    cog, ctx, _ = _timer_cog(monkeypatch)
    member = _member()

    def timers():
        _, end = cog.database.addTimerMute.call_args.args
        return [{"user_id": "7", "ban": 1, "mute": 1, "endBan": "Dec-01-2026 10:00:00", "endMute": end}]

    cog.database.getTimers.side_effect = timers
    asyncio.run(cog.mute.callback(cog, ctx, member, "1h"))
    cog.database.endTimerMute.assert_called_once_with("7")
    cog.database.delTimer.assert_not_called()


def test_mute_end_skips_a_replaced_timer(monkeypatch):
    """A newer /mute changed the end: the old sleeper must not unmute early."""
    row = {"user_id": "7", "ban": 0, "mute": 1, "endBan": None, "endMute": "Dec-01-2026 10:00:00"}
    cog, ctx, _ = _timer_cog(monkeypatch, row)
    member = _member()
    asyncio.run(cog.mute.callback(cog, ctx, member, "1h"))
    member.remove_roles.assert_not_awaited()
    cog.database.delTimer.assert_not_called()
    cog.database.endTimerMute.assert_not_called()


def test_unmute_keeps_a_running_tempban(monkeypatch):
    row = {"user_id": "7", "ban": 1, "mute": 1, "endBan": "Dec-01-2026 10:00:00",
           "endMute": "Dec-01-2026 10:00:00"}
    cog, ctx, _ = _timer_cog(monkeypatch, row)
    asyncio.run(cog.unmute.callback(cog, ctx, _member()))
    cog.database.endTimerMute.assert_called_once_with("7")
    cog.database.delTimer.assert_not_called()


def test_tempban_bans_also_when_the_dm_fails(monkeypatch):
    cog, ctx, _ = _timer_cog(monkeypatch)
    ctx.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    member = _member()
    member.send.side_effect = discord.Forbidden(MagicMock(status=403), "Cannot send messages to this user")
    asyncio.run(cog.tempban_user.callback(cog, ctx, member, "1d", "x"))
    ctx.guild.ban.assert_awaited_once()
    ctx.guild.unban.assert_awaited_once()
    cog.database.delTimer.assert_called_once_with("7")


def test_unwarn_removes_the_newest_warning():
    cog = _mod_cog()
    cog.database.getWarnUserByID.return_value = {"warnings": 2}
    cog.database.delWarning.return_value = 1
    ctx = _ctx()
    ctx.guild.get_channel.return_value.send = AsyncMock()
    asyncio.run(cog.unwarn.callback(cog, ctx, _member()))
    cog.database.delWarning.assert_called_once_with("7")
    ctx.guild.get_channel.return_value.send.assert_awaited_once()


def test_unwarn_without_warnings_changes_nothing():
    cog = _mod_cog()
    cog.database.getWarnUserByID.return_value = {"warnings": 0}
    ctx = _ctx()
    ctx.guild.get_channel.return_value.send = AsyncMock()
    asyncio.run(cog.unwarn.callback(cog, ctx, _member()))
    cog.database.delWarning.assert_not_called()
    ctx.guild.get_channel.return_value.send.assert_not_awaited()
    assert "no warnings" in ctx.respond.await_args.kwargs["embed"].title


def test_warn_error_is_answered():
    cog = _mod_cog()
    cog.database.addWarning.side_effect = RuntimeError("db down")
    ctx = _ctx()
    asyncio.run(cog.warn.callback(cog, ctx, _member(), "spam"))
    assert ctx.respond.await_args.kwargs["ephemeral"] is True


def test_timers_need_no_api_call():
    cog = _mod_cog()
    cog.database.getTimers.return_value = [
        {"user_id": "1", "ban": 1, "mute": 0, "endBan": "Oct-30-2026 10:00:00", "endMute": None}]
    cog.bot.fetch_user = AsyncMock()
    ctx = _ctx()
    asyncio.run(cog.show_timers.callback(cog, ctx))
    cog.bot.fetch_user.assert_not_awaited()
    assert "<@1>" in ctx.respond.await_args.kwargs["embed"].description


def test_many_timers_fit_in_one_embed():
    cog = _mod_cog()
    cog.database.getTimers.return_value = [
        {"user_id": str(10**17 + i), "ban": 1, "mute": 1, "endBan": "Oct-30-2026 10:00:00",
         "endMute": "Oct-30-2026 10:00:00"} for i in range(100)]
    ctx = _ctx()
    asyncio.run(cog.show_timers.callback(cog, ctx))
    description = ctx.respond.await_args.kwargs["embed"].description
    assert len(description) <= 4096
    assert description.endswith("more")


def test_prefix_info_commands_with_the_default_bot_avatar():
    users = importlib.import_module("cogs.users")
    bot = MagicMock()
    bot.user.avatar = None
    bot.user.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    cog = users.Users(bot)
    ctx = _ctx()
    ctx.reply = AsyncMock()
    ctx.message.author.roles = [ctx.guild.get_role.return_value]  # a mod: any channel
    for command in (cog.roles, cog.twitch, cog.faq):
        asyncio.run(command.callback(cog, ctx))
        assert ctx.reply.await_args.kwargs["embed"].author.icon_url == bot.user.display_avatar.url
