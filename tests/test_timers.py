"""Tests for the background timer checks in timers.py (moved out of franky.py)."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import timers

NOW = datetime(2026, 10, 29, 12, 0, 0)
PAST, FUTURE = "Oct-29-2026 11:00:00", "Oct-29-2026 13:00:00"


def _setup(rows):
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=MagicMock(name="u", discriminator="0"))
    database = MagicMock()
    database.getJac.return_value = []
    database.getTimers.return_value = rows
    guild = MagicMock()
    member = MagicMock()
    member.remove_roles = AsyncMock()
    guild.fetch_member = AsyncMock(return_value=member)
    guild.unban = AsyncMock()
    channel = MagicMock()
    channel.send = AsyncMock()
    return bot, database, guild, channel, member


def _row(ban=0, mute=0, end_ban=None, end_mute=None):
    """A row as getTimers returns it: a dict, not a tuple."""
    return {"user_id": "1", "ban": ban, "mute": mute, "endBan": end_ban, "endMute": end_mute}


def _run(rows):
    bot, database, guild, channel, member = _setup(rows)
    asyncio.run(timers.check_all(bot, database, guild, channel, NOW))
    return bot, database, guild, channel, member


def test_expired_mute_is_removed():
    _, database, _, channel, member = _run([_row(mute=1, end_mute=PAST)])
    member.remove_roles.assert_awaited_once()
    channel.send.assert_awaited_once()
    database.delTimer.assert_called_once_with("1")


def test_expired_mute_keeps_a_running_tempban():
    """delTimer deletes the whole row: the ban timer of the same user must survive."""
    _, database, guild, _, member = _run([_row(ban=1, mute=1, end_ban=FUTURE, end_mute=PAST)])
    member.remove_roles.assert_awaited_once()
    database.delTimer.assert_not_called()
    database.endTimerMute.assert_called_once_with("1")
    guild.unban.assert_not_awaited()


def test_expired_ban_keeps_a_running_mute():
    _, database, guild, _, member = _run([_row(ban=1, mute=1, end_ban=PAST, end_mute=FUTURE)])
    guild.unban.assert_awaited_once()
    database.delTimer.assert_not_called()
    database.endTimerBan.assert_called_once_with("1")


def test_both_expired_delete_the_row():
    _, database, _, _, _ = _run([_row(ban=1, mute=1, end_ban=PAST, end_mute=PAST)])
    database.delTimer.assert_called_once_with("1")
    database.endTimerMute.assert_not_called()


def test_mute_of_a_user_who_left_is_dropped():
    bot, database, guild, channel, _ = _setup([_row(mute=1, end_mute=PAST)])
    guild.fetch_member.side_effect = Exception("gone")
    asyncio.run(timers.check_all(bot, database, guild, channel, NOW))
    database.delTimer.assert_called_once_with("1")


def test_running_mute_is_kept():
    _, database, _, _, member = _run([_row(mute=1, end_mute=FUTURE)])
    member.remove_roles.assert_not_awaited()
    database.delTimer.assert_not_called()


def test_expired_ban_is_removed():
    _, database, guild, _, _ = _run([_row(ban=1, end_ban=PAST)])
    guild.unban.assert_awaited_once()
    database.delTimer.assert_called_once_with("1")


def test_running_ban_does_not_block_the_loop():
    """The old code slept until the ban ended, so the hourly loop stopped for days."""
    _, database, guild, _, _ = _run([_row(ban=1, end_ban=FUTURE)])
    guild.unban.assert_not_awaited()
    database.delTimer.assert_not_called()


def test_row_without_timers_is_deleted_by_user_id():
    _, database, _, _, _ = _run([_row()])
    database.delTimer.assert_called_once_with("1")


def test_old_jac_entries_are_pruned():
    bot, database, guild, channel, _ = _setup([])
    database.getJac.return_value = [
        {"user_id": "1", "date": "Oct-01-2026 10:00:00"},
        {"user_id": "2", "date": "Oct-28-2026 10:00:00"},
    ]
    asyncio.run(timers.check_all(bot, database, guild, channel, NOW))
    database.delJac.assert_called_once_with("1")
