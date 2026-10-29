"""Tests for automod_rules.py: rule specs from config and the idempotent sync."""
import asyncio
import re
import types
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import automod_rules as ar

MOD, ADMIN, CLAN, ALERT = 11, 12, 13, 14


def _cfg(**overrides):
    cfg = types.SimpleNamespace(
        MOD_ID=MOD, ADMIN_ID=ADMIN, CLAN_CHAN=CLAN, LOG_CHAN=ALERT,
        INVITE_BANLIST=["discord.gg/badclan"],
        INVITE_WHITELIST=["discord.gg/drewski"],
        SCAMURLS=["steamcommunnity.com", "dlscord-gift.com"],
        SCAMTEXT=["Free Nitro", "free nitro"],
        BLACKLIST=["badword"],
        NSFW=["onlyfans", "18+"],
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _by_name(specs):
    return {spec.name: spec for spec in specs}


def test_one_rule_per_bot_action():
    specs = _by_name(ar.build_rules(_cfg()))
    assert set(specs) == {ar.INVITE_BANLIST, ar.INVITES, ar.SCAM, ar.BLACKLIST, ar.EVERYONE_SPAM}
    assert {name: ar.RULE_KIND[name] for name in specs} == {
        ar.INVITE_BANLIST: ar.BAN, ar.INVITES: ar.REVIEW, ar.SCAM: ar.REVIEW,
        ar.BLACKLIST: ar.WARN, ar.EVERYONE_SPAM: ar.REVIEW,
    }


def test_keywords_are_substring_wildcards_lowercase_and_unique():
    specs = _by_name(ar.build_rules(_cfg()))
    assert specs[ar.SCAM].keywords == [
        "*steamcommunnity.com*", "*dlscord-gift.com*", "*free nitro*"]
    assert specs[ar.BLACKLIST].keywords == ["*badword*"]
    assert specs[ar.INVITE_BANLIST].keywords == ["*discord.gg/badclan*"]


def test_invite_rule_allows_whitelist_and_leaves_banlist_to_its_own_rule():
    spec = _by_name(ar.build_rules(_cfg()))[ar.INVITES]
    assert "*discord.gg/*" in spec.keywords
    assert spec.allow_list == ["*discord.gg/drewski*", "*discord.gg/badclan*"]


def test_exemptions_match_the_old_filters():
    specs = _by_name(ar.build_rules(_cfg()))
    for name in (ar.INVITE_BANLIST, ar.INVITES):
        assert specs[name].exempt_roles == [MOD, ADMIN]
        assert specs[name].exempt_channels == [CLAN]
    assert specs[ar.BLACKLIST].exempt_roles == [MOD]
    assert specs[ar.EVERYONE_SPAM].exempt_roles == [MOD, ADMIN]
    assert specs[ar.SCAM].exempt_roles == []


def test_everyone_spam_regex_matches_like_check_spam_v2():
    patterns = _by_name(ar.build_rules(_cfg()))[ar.EVERYONE_SPAM].regex_patterns

    def hit(text):
        return any(re.search(p, text) for p in patterns)

    assert hit("@everyone free stuff https://x.y")
    assert hit("https://x.y check this @everyone")
    assert hit("@here my OnlyFans")
    assert hit("18+ pics @everyone")
    assert not hit("@here raid tonight")
    assert not hit("https://x.y onlyfans")
    assert all(len(p) <= ar.MAX_REGEX_LEN for p in patterns)


def test_everyone_spam_regex_escapes_metacharacters():
    patterns = _by_name(ar.build_rules(_cfg(NSFW=["a.b"])))[ar.EVERYONE_SPAM].regex_patterns
    assert any(re.search(p, "@here a.b") for p in patterns)
    assert not any(re.search(p, "@here axb") for p in patterns)


def test_long_nsfw_list_is_split_into_patterns_under_the_limit():
    words = [f"word{i:03d}xxxxxxxxxx" for i in range(40)]
    patterns = _by_name(ar.build_rules(_cfg(NSFW=words)))[ar.EVERYONE_SPAM].regex_patterns
    assert all(len(p) <= ar.MAX_REGEX_LEN for p in patterns)
    for word in words:
        assert any(re.search(p, f"@here {word}") for p in patterns)


def test_keyword_over_60_chars_is_rejected():
    with pytest.raises(ValueError, match="60"):
        ar.build_rules(_cfg(BLACKLIST=["x" * 59]))


def test_too_many_regex_patterns_is_rejected():
    words = [f"w{i:04d}" + "y" * 50 for i in range(60)]
    with pytest.raises(ValueError, match="regex"):
        ar.build_rules(_cfg(NSFW=words))


def test_alert_only_actions_by_default():
    actions = ar.build_actions(enforce=False, alert_channel_id=ALERT)
    assert [a.type for a in actions] == [discord.AutoModActionType.send_alert_message]
    assert actions[0].metadata.channel_id == ALERT


def test_enforce_adds_block_with_custom_message():
    actions = ar.build_actions(enforce=True, alert_channel_id=ALERT)
    assert [a.type for a in actions] == [
        discord.AutoModActionType.block_message,
        discord.AutoModActionType.send_alert_message,
    ]
    assert 0 < len(actions[0].metadata.custom_message) <= 150


# --- sync_rules -------------------------------------------------------------

def _rule(name, blocking=False, enabled=True, trigger=discord.AutoModTriggerType.keyword):
    rule = MagicMock()
    rule.name = name
    rule.enabled = enabled
    rule.trigger_type = trigger
    types_ = [discord.AutoModActionType.send_alert_message]
    if blocking:
        types_.insert(0, discord.AutoModActionType.block_message)
    rule.actions = [types.SimpleNamespace(type=t) for t in types_]
    rule.edit = AsyncMock()
    return rule


def _guild(rules):
    guild = MagicMock()
    guild.fetch_auto_moderation_rules = AsyncMock(return_value=rules)
    guild.create_auto_moderation_rule = AsyncMock()
    return guild


def _sync(guild, **kwargs):
    specs = ar.build_rules(_cfg())
    asyncio.run(ar.sync_rules(guild, specs, ALERT, log=lambda *_: None, **kwargs))
    return specs


def _action_types(kwargs):
    return [a.type for a in kwargs["actions"]]


def test_sync_creates_missing_rules_alert_only_and_enabled():
    guild = _guild([])
    specs = _sync(guild)
    calls = guild.create_auto_moderation_rule.await_args_list
    assert sorted(c.kwargs["name"] for c in calls) == sorted(ar.PREFIX + s.name for s in specs)
    for call in calls:
        assert call.kwargs["enabled"] is True
        assert call.kwargs["trigger_type"] == discord.AutoModTriggerType.keyword
        assert call.kwargs["event_type"] == discord.AutoModEventType.message_send
        assert _action_types(call.kwargs) == [discord.AutoModActionType.send_alert_message]


def test_sync_sends_exempt_roles_as_snowflakes():
    guild = _guild([])
    _sync(guild)
    call = next(c for c in guild.create_auto_moderation_rule.await_args_list
                if c.kwargs["name"] == ar.PREFIX + ar.INVITES)
    assert [r.id for r in call.kwargs["exempt_roles"]] == [MOD, ADMIN]
    assert [c.id for c in call.kwargs["exempt_channels"]] == [CLAN]
    assert call.kwargs["trigger_metadata"].allow_list == [
        "*discord.gg/drewski*", "*discord.gg/badclan*"]


def test_sync_updates_existing_rules_and_is_idempotent():
    rules = [_rule(ar.PREFIX + n) for n in ar.RULE_KIND]
    guild = _guild(rules)
    _sync(guild)
    _sync(guild)
    guild.create_auto_moderation_rule.assert_not_awaited()
    for rule in rules:
        assert rule.edit.await_count == 2


def test_sync_keeps_existing_enforcement_unless_told_otherwise():
    scam = _rule(ar.PREFIX + ar.SCAM, blocking=True)
    banlist = _rule(ar.PREFIX + ar.INVITE_BANLIST)
    blacklist = _rule(ar.PREFIX + ar.BLACKLIST, blocking=True)
    guild = _guild([scam, banlist, blacklist])
    _sync(guild, enforce=[ar.INVITE_BANLIST], alert_only=[ar.BLACKLIST])
    assert discord.AutoModActionType.block_message in _action_types(scam.edit.await_args.kwargs)
    assert discord.AutoModActionType.block_message in _action_types(banlist.edit.await_args.kwargs)
    assert discord.AutoModActionType.block_message not in _action_types(blacklist.edit.await_args.kwargs)


def test_sync_enforce_all():
    guild = _guild([])
    _sync(guild, enforce=["all"])
    for call in guild.create_auto_moderation_rule.await_args_list:
        assert discord.AutoModActionType.block_message in _action_types(call.kwargs)


def test_sync_rejects_unknown_rule_names():
    with pytest.raises(ValueError, match="nope"):
        _sync(_guild([]), enforce=["nope"])


def test_disable_turns_off_only_bot_rules():
    ours = _rule(ar.PREFIX + ar.SCAM)
    theirs = _rule("Block mention spam")
    guild = _guild([ours, theirs])
    _sync(guild, disable=True)
    ours.edit.assert_awaited_once_with(enabled=False, reason=ar.AUDIT_REASON)
    theirs.edit.assert_not_awaited()
    guild.create_auto_moderation_rule.assert_not_awaited()


def test_sync_stops_before_exceeding_the_keyword_rule_limit():
    others = [_rule(f"mod rule {i}") for i in range(2)]
    guild = _guild(others)
    with pytest.raises(ValueError, match="KEYWORD"):
        _sync(guild)
    guild.create_auto_moderation_rule.assert_not_awaited()


def test_asterisk_in_config_words_is_rejected():
    with pytest.raises(ValueError, match=r"\*"):
        ar.build_rules(_cfg(BLACKLIST=["*bad"]))


def test_enforce_and_alert_only_on_the_same_rule_is_rejected():
    with pytest.raises(ValueError, match="scam"):
        _sync(_guild([]), enforce=[ar.SCAM], alert_only=[ar.SCAM])


def test_check_makes_no_api_calls(monkeypatch, capsys):
    import config
    for key, value in vars(_cfg()).items():
        monkeypatch.setattr(config, key, value, raising=False)
    monkeypatch.setattr(ar, "_run", MagicMock(side_effect=AssertionError("API call")))
    ar.main(["--check"])
    assert '"invite-banlist"' in capsys.readouterr().out
    ar._run.assert_not_called()
