"""Tests for cogs/automod.py, with real py-cord AutoModActionExecutionEvent payloads."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import automod_rules as ar
from cogs import automod

GUILD, USER, CHANNEL, ALERT_CHAN, ALERT_MSG, MSG = 99, 5, 7, 14, 555, 777
RULE_IDS = {name: 100 + i for i, name in enumerate(ar.RULE_KIND)}


def _event(rule, action=2, message_id=None, alert=True, keyword="*free nitro*", state=None):
    """Gateway AUTO_MODERATION_ACTION_EXECUTION payload. Content is empty without the intent."""
    data = {
        "guild_id": str(GUILD),
        "action": {"type": action, "metadata": {"channel_id": str(ALERT_CHAN)} if action == 2 else {}},
        "rule_id": str(rule if isinstance(rule, int) else RULE_IDS[rule]),
        "rule_trigger_type": 1,
        "user_id": str(USER),
        "channel_id": str(CHANNEL),
        "content": "",
        "matched_keyword": keyword,
        "matched_content": "",
    }
    if message_id:
        data["message_id"] = str(message_id)
    if alert and action == 2:
        data["alert_system_message_id"] = str(ALERT_MSG)
    return discord.AutoModActionExecutionEvent(state, data)


def _rule(name, rule_id):
    rule = MagicMock()
    rule.name = name
    rule.id = rule_id
    return rule


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(automod.config, "LOG_CHAN", 1, raising=False)
    monkeypatch.setattr(automod.config, "MOD_ID", 11, raising=False)
    monkeypatch.setattr(automod.config, "AUTOMOD_DRY_RUN", False, raising=False)

    log_chan, where = MagicMock(), MagicMock()
    log_chan.send = AsyncMock()
    where.send = AsyncMock()
    where.mention = f"<#{CHANNEL}>"
    partial = MagicMock()
    partial.delete = AsyncMock()
    where.get_partial_message.return_value = partial

    member = MagicMock()
    member.id = USER
    member.roles = []
    member.timeout_for = AsyncMock()
    member.remove_timeout = AsyncMock()

    guild = MagicMock()
    guild.id = GUILD
    guild.get_channel.side_effect = {1: log_chan}.get
    guild.get_channel_or_thread.side_effect = {CHANNEL: where}.get
    guild.get_member.return_value = None
    guild.fetch_member = AsyncMock(return_value=member)
    guild.ban = AsyncMock()
    guild.get_role.return_value = MagicMock()
    rules = [_rule(ar.PREFIX + n, i) for n, i in RULE_IDS.items()] + [_rule("Mods' own rule", 1)]
    guild.fetch_auto_moderation_rules = AsyncMock(return_value=rules)

    user = MagicMock()
    user.id = USER
    user.name = "spammer"
    bot = MagicMock()
    bot.get_guild.return_value = guild
    bot.get_user.return_value = user

    state = MagicMock()
    state._get_guild.return_value = guild
    state._get_message.return_value = None

    cog = automod.AutoMod(bot)
    cog.database = MagicMock()
    view = MagicMock()
    view.wait = AsyncMock()
    view.value = False
    view.inter.message.edit = AsyncMock()
    monkeypatch.setattr(automod.support, "Scam", lambda *_: view)

    def fire(*args, **kwargs):
        asyncio.run(cog.on_auto_moderation_action_execution(_event(*args, state=state, **kwargs)))

    return MagicMock(cog=cog, guild=guild, member=member, log_chan=log_chan,
                     where=where, partial=partial, view=view, fire=fire)


def _embed(chan):
    return chan.send.await_args.kwargs["embed"]


def test_banlist_bans_by_id(env):
    env.fire(ar.INVITE_BANLIST)
    env.guild.ban.assert_awaited_once()
    assert env.guild.ban.await_args.args[0].id == USER
    assert env.guild.ban.await_args.kwargs["reason"] == "Blacklisted invite"
    env.cog.database.addKillCount.assert_called_once_with(str(USER))


def test_scam_times_out_and_posts_review_without_content(env):
    env.fire(ar.SCAM)
    env.member.timeout_for.assert_awaited_once()
    assert env.member.timeout_for.await_args.kwargs["duration"].days == 1
    embed = _embed(env.log_chan)
    fields = {f.name: f.value for f in embed.fields}
    assert embed.title == "Possible scam - manual review"
    assert fields["Matched keyword"] == "`*free nitro*`"
    assert fields["Rule"] == ar.SCAM
    assert fields["AutoMod alert"].endswith(f"/{GUILD}/{ALERT_CHAN}/{ALERT_MSG}")
    assert env.log_chan.send.await_args.kwargs["view"] is env.view


def test_scam_review_ban_confirmed(env):
    env.view.value = True
    env.fire(ar.SCAM)
    env.guild.ban.assert_awaited_once()
    assert env.guild.ban.await_args.kwargs["delete_message_seconds"] == 43200
    env.member.remove_timeout.assert_not_awaited()


def test_scam_review_cancelled_removes_timeout(env):
    env.fire(ar.SCAM)
    env.member.remove_timeout.assert_awaited_once()
    env.guild.ban.assert_not_awaited()
    assert env.view.inter.message.edit.await_args.kwargs["view"] is None


def test_scam_review_when_user_already_left(env):
    env.guild.fetch_member.side_effect = discord.NotFound(MagicMock(status=404), "gone")
    env.view.value = True
    env.fire(ar.SCAM)
    env.guild.ban.assert_awaited_once()


def test_blacklist_warns_in_channel_and_db(env):
    env.fire(ar.BLACKLIST, keyword="*badword*")
    assert f"<@{USER}>" in env.where.send.await_args.args[0]
    env.cog.database.addWarning.assert_called_once()
    assert env.cog.database.addWarning.call_args.args[0] == str(USER)
    assert _embed(env.log_chan).title == "Warning issued!"
    env.guild.ban.assert_not_awaited()


def test_block_event_is_ignored_only_alert_counts(env):
    env.fire(ar.INVITE_BANLIST, action=1)
    env.guild.ban.assert_not_awaited()
    env.log_chan.send.assert_not_awaited()


def test_same_user_two_review_rules_one_review(env):
    env.fire(ar.SCAM)
    env.fire(ar.EVERYONE_SPAM)
    assert env.log_chan.send.await_count == 1
    assert env.member.timeout_for.await_count == 1


def test_dedup_never_skips_the_deletion_of_alert_only_messages(env):
    """Same scam in two channels within the window: both messages go, one review."""
    env.fire(ar.SCAM, message_id=MSG)
    env.fire(ar.EVERYONE_SPAM, message_id=MSG + 1)
    assert [c.args[0] for c in env.where.get_partial_message.call_args_list] == [MSG, MSG + 1]
    assert env.partial.delete.await_count == 2
    assert env.cog.database.addKillCount.call_count == 2
    assert env.log_chan.send.await_count == 1


def test_failed_ban_is_logged_not_raised(env):
    env.guild.ban.side_effect = discord.Forbidden(MagicMock(status=403), "higher role")
    env.fire(ar.INVITE_BANLIST)
    env.guild.ban.assert_awaited_once()


def test_failed_review_timeout_still_posts_the_review(env):
    env.member.timeout_for.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    env.fire(ar.SCAM)
    assert _embed(env.log_chan).title == "Possible scam - manual review"


def test_uncached_guild_is_ignored(env):
    env.cog.bot.get_guild.return_value = None
    state = MagicMock()
    state._get_guild.return_value = env.guild
    event = _event(ar.SCAM, state=state)
    event.guild = None  # py-cord itself fails to parse the event without a cached guild
    asyncio.run(env.cog.on_auto_moderation_action_execution(event))
    env.log_chan.send.assert_not_awaited()


def test_unknown_rule_is_ignored_and_rules_are_cached(env):
    env.fire(1)
    env.fire(1)
    env.fire(ar.SCAM)
    env.log_chan.send.assert_awaited_once()
    env.guild.fetch_auto_moderation_rules.assert_awaited_once()


def test_alert_only_rule_message_is_deleted_by_the_bot(env):
    env.fire(ar.SCAM, message_id=MSG)
    env.where.get_partial_message.assert_called_once_with(MSG)
    env.partial.delete.assert_awaited_once()


def test_blocked_message_is_not_deleted_again(env):
    env.fire(ar.SCAM)
    env.where.get_partial_message.assert_not_called()


def test_dry_run_only_reports(env, monkeypatch):
    monkeypatch.setattr(automod.config, "AUTOMOD_DRY_RUN", True, raising=False)
    env.fire(ar.INVITE_BANLIST, message_id=MSG)
    env.fire(ar.BLACKLIST)
    env.guild.ban.assert_not_awaited()
    env.member.timeout_for.assert_not_awaited()
    env.partial.delete.assert_not_awaited()
    env.where.send.assert_not_awaited()
    env.cog.database.addWarning.assert_not_called()
    env.cog.database.addKillCount.assert_not_called()
    titles = [c.kwargs["embed"].title for c in env.log_chan.send.await_args_list]
    assert titles == ["AutoMod dry run"] * 2
    assert "would ban" in env.log_chan.send.await_args_list[0].kwargs["embed"].description


def test_only_an_explicit_false_turns_dry_run_off(monkeypatch):
    if "AUTOMOD_DRY_RUN" in vars(automod.config):
        monkeypatch.delattr(automod.config, "AUTOMOD_DRY_RUN")
    assert automod.dry_run() is True
    monkeypatch.setattr(automod.config, "AUTOMOD_DRY_RUN", 0, raising=False)
    assert automod.dry_run() is True
    monkeypatch.setattr(automod.config, "AUTOMOD_DRY_RUN", False, raising=False)
    assert automod.dry_run() is False
