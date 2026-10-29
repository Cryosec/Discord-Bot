"""Tests for the slash command fixes and the cog smoke load (no Discord connection)."""
import asyncio
import importlib
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
