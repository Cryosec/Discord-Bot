"""Tests for the manual review and the purge in cogs/honeypot.py (no Discord connection)."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs import honeypot


UNTIL = datetime.now(timezone.utc) + timedelta(days=1)


def _review_message():
    message = MagicMock()
    message.content = "SECRET-CONTENT"
    message.channel.mention = "#trap"
    message.author.id = 5
    message.author.mention = "@spammer"
    message.author.joined_at.strftime.return_value = "joined"
    message.author.created_at.strftime.return_value = "created"
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    message.guild.get_channel.return_value = log_channel
    return message, log_channel


def _cog():
    bot = MagicMock()
    bot.is_ready.return_value = False
    return honeypot.Honeypot(bot)


def _review_embed(purged=None, until=UNTIL):
    message, log_channel = _review_message()
    asyncio.run(honeypot.honeypot_review_embed(_cog(), message, purged, until))
    return log_channel.send.await_args.kwargs


def test_review_embed_has_no_message_field_and_carries_the_state():
    kwargs = _review_embed({"general": 2})
    first = kwargs["embed"]
    assert isinstance(kwargs["view"], honeypot.HoneypotReviewView)
    assert "Message" not in [f.name for f in first.fields]
    assert "SECRET-CONTENT" not in str(first.to_dict())
    assert [f.name for f in first.fields][:2] == ["Channel", "Author"]
    assert "Deleted messages" in [f.name for f in first.fields]
    fields = {f.name: f.value for f in first.fields}
    assert fields["User ID"] == "5"
    assert fields["Timeout until"] == UNTIL.isoformat()


def _env(make_press, current=UNTIL):
    embed = _review_embed({"general": 2})["embed"]
    member = MagicMock()
    member.communication_disabled_until = current
    member.remove_timeout = AsyncMock()
    guild = MagicMock()
    guild.fetch_member = AsyncMock(return_value=member)
    guild.ban = AsyncMock()
    press = make_press.build(guild, embed)
    return guild, member, press


def _view():
    return honeypot.HoneypotReviewView(_cog())


def test_view_is_persistent_with_fixed_custom_ids_and_registered():
    async def run():
        view = _view()
        assert view.is_persistent()
        assert [i.custom_id for i in view.children] == ["lf:honeypot:ban", "lf:honeypot:release"]
        cog = _cog()
        await cog.on_ready()
        assert isinstance(cog.bot.add_view.call_args.args[0], honeypot.HoneypotReviewView)
        assert len(cog.bot.add_view.call_args.args) == 1  # no message_id
        late = MagicMock()
        late.is_ready.return_value = True  # cogwatch reload while the bot runs
        honeypot.Honeypot(late)
        late.add_view.assert_called_once()
    asyncio.run(run())


def test_ban_button_bans_and_closes_the_review(make_press, monkeypatch):
    monkeypatch.setattr(honeypot.config, "HONEYPOT_DELETE_SECONDS", 3600, raising=False)
    guild, member, press = _env(make_press)
    make_press.click(_view, "lf:honeypot:ban", press.interaction)
    guild.ban.assert_awaited_once()
    assert guild.ban.await_args.args[0].id == 5
    assert guild.ban.await_args.kwargs["delete_message_seconds"] == 3600
    assert guild.ban.await_args.kwargs["reason"] == "Honeypot hit confirmed by mod#1"
    member.remove_timeout.assert_not_awaited()
    kwargs = press.message.edit.await_args.kwargs
    done = kwargs["embed"]
    assert kwargs["view"] is None
    assert done.title == "Honeypot hit - manual review completed"
    assert [f.name for f in done.fields] == ["Author", "Result"]
    assert done.fields[1].value == "Banned"


def test_release_button_removes_the_timeout_and_closes_the_review(make_press):
    guild, member, press = _env(make_press)
    make_press.click(_view, "lf:honeypot:release", press.interaction)
    member.remove_timeout.assert_awaited_once_with(
        reason="Honeypot review completed. Timeout removed")
    guild.ban.assert_not_awaited()
    kwargs = press.message.edit.await_args.kwargs
    assert kwargs["view"] is None
    assert kwargs["embed"].fields[1].value == "Released"


def test_release_after_a_newer_timeout_does_nothing(make_press):
    guild, member, press = _env(make_press, current=UNTIL + timedelta(days=6))
    make_press.click(_view, "lf:honeypot:release", press.interaction)
    member.remove_timeout.assert_not_awaited()
    press.message.edit.assert_not_awaited()
    assert "already changed" in make_press.answers(press.interaction)[0]


def test_release_when_the_user_left(make_press):
    guild, member, press = _env(make_press)
    guild.fetch_member.side_effect = discord.NotFound(MagicMock(status=404), "gone")
    make_press.click(_view, "lf:honeypot:release", press.interaction)
    member.remove_timeout.assert_not_awaited()
    assert "left" in make_press.answers(press.interaction)[0]


def test_ban_of_an_unknown_user_is_a_failure_not_a_ban(make_press):
    guild, _, press = _env(make_press)
    guild.ban.side_effect = discord.NotFound(MagicMock(status=404), "unknown")
    make_press.click(_view, "lf:honeypot:ban", press.interaction)
    press.message.edit.assert_not_awaited()
    assert press.message.components


def test_ban_and_release_together_act_once(make_press):
    guild, member, press = _env(make_press)
    other = make_press.build(guild, press.message.embeds[0])
    other.interaction.channel.fetch_message = press.interaction.channel.fetch_message

    async def run():
        ban, release = _view().children
        await asyncio.gather(ban.callback(press.interaction), release.callback(other.interaction))

    asyncio.run(run())
    guild.ban.assert_awaited_once()
    member.remove_timeout.assert_not_awaited()


def test_non_mod_cannot_press_honeypot_buttons(make_press):
    guild, member, press = _env(make_press)
    other = make_press.build(guild, press.message.embeds[0], mod=False)
    make_press.click(_view, "lf:honeypot:ban", other.interaction)
    make_press.click(_view, "lf:honeypot:release", other.interaction)
    guild.ban.assert_not_awaited()
    member.remove_timeout.assert_not_awaited()


def test_non_autoban_hit_times_out_and_posts_the_review_with_the_end(monkeypatch):
    for name, value in {"HONEYPOT_CHAN": 77, "HONEYPOT_AUTOBAN": False, "ADMIN_ID": 1,
                        "MOD_ID": 2, "HONEYPOT_PURGE_SECONDS": 0, "HONEYPOT_DM": "dm",
                        "HONEYPOT_REASON": "Honeypot hit"}.items():
        monkeypatch.setattr(honeypot.config, name, value, raising=False)
    message, log_channel = _review_message()
    message.channel.id = 77
    message.guild.get_role.return_value = MagicMock()
    message.webhook_id = None
    message.author = MagicMock(spec=discord.Member)
    message.author.bot = False
    message.author.roles = []
    message.author.id = 5
    message.author.mention = "@spammer"
    message.author.send = AsyncMock()
    message.author.timeout_for = AsyncMock()
    message.delete = AsyncMock()

    asyncio.run(asyncio.wait_for(honeypot.check_honeypot(_cog(), message), 1))  # no wait()

    message.author.timeout_for.assert_awaited_once()
    kwargs = log_channel.send.await_args.kwargs
    fields = {f.name: f.value for f in kwargs["embed"].fields}
    until = honeypot.support.parse_until(fields["Timeout until"])
    planned = discord.utils.utcnow() + timedelta(days=1)
    assert abs((until - planned).total_seconds()) < 5
    assert isinstance(kwargs["view"], honeypot.HoneypotReviewView)


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


def test_honeypot_reason_is_a_review_timeout_reason(monkeypatch):
    monkeypatch.setattr(honeypot.config, "HONEYPOT_REASON", "Honeypot hit", raising=False)
    assert honeypot.support.is_review_timeout("Honeypot hit")
    monkeypatch.setattr(honeypot.config, "HONEYPOT_REASON", "Changed by reconf", raising=False)
    assert honeypot.support.is_review_timeout("Changed by reconf")
    assert not honeypot.support.is_review_timeout("Honeypot hit")
    assert not honeypot.support.is_review_timeout(None)
