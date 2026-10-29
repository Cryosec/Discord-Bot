"""Unit tests for the audit-log helpers in support.py."""
import discord

import support

TS = "2026-10-29T18:00:00+00:00"


def test_timeout_added():
    changes = [{"key": "communication_disabled_until", "new_value": TS}]
    assert support.timeout_change(changes) == "added"


def test_timeout_extended_counts_as_added():
    changes = [{"key": "communication_disabled_until", "old_value": TS, "new_value": TS}]
    assert support.timeout_change(changes) == "added"


def test_timeout_removed_new_value_missing():
    changes = [{"key": "communication_disabled_until", "old_value": TS}]
    assert support.timeout_change(changes) == "removed"


def test_timeout_removed_new_value_null():
    changes = [{"key": "communication_disabled_until", "old_value": TS, "new_value": None}]
    assert support.timeout_change(changes) == "removed"


def test_other_member_update_is_ignored():
    changes = [{"key": "nick", "old_value": "a", "new_value": "b"}]
    assert support.timeout_change(changes) is None


def test_timeout_key_among_other_changes():
    changes = [
        {"key": "nick", "old_value": "a", "new_value": "b"},
        {"key": "communication_disabled_until", "new_value": TS},
    ]
    assert support.timeout_change(changes) == "added"


def test_no_changes():
    assert support.timeout_change(None) is None
    assert support.timeout_change([]) is None


class _Msg:
    def __init__(self, msg_type, bot=False):
        self.type = msg_type
        self.author = type("Author", (), {"bot": bot})()


def test_join_system_message_detected():
    assert support.is_member_join(_Msg(discord.MessageType.new_member)) is True


def test_regular_message_is_not_join():
    assert support.is_member_join(_Msg(discord.MessageType.default)) is False


def test_bot_join_is_ignored():
    assert support.is_member_join(_Msg(discord.MessageType.new_member, bot=True)) is False


def test_timeout_embed_with_the_default_bot_avatar():
    """bot.user.avatar is None without a custom avatar: use display_avatar."""
    from unittest.mock import MagicMock
    bot = MagicMock()
    bot.user.avatar = None
    bot.user.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    embed = support.timeout_embed(bot, MagicMock(), "AutoMod", "spam")
    assert embed.author.icon_url == bot.user.display_avatar.url
