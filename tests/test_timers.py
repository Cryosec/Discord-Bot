"""Tests for the background timer checks in timers.py (moved out of franky.py)."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import discord

import timers

NOW = datetime(2026, 10, 29, 12, 0, 0)
PAST, FUTURE = "Oct-29-2026 11:00:00", "Oct-29-2026 13:00:00"


def _setup(rows):
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
    return database, guild, channel, member


def _row(ban=0, mute=0, end_ban=None, end_mute=None):
    """A row as getTimers returns it: a dict, not a tuple."""
    return {"user_id": "1", "ban": ban, "mute": mute, "endBan": end_ban, "endMute": end_mute}


def _run(rows):
    database, guild, channel, member = _setup(rows)
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    return database, guild, channel, member


def test_expired_mute_is_removed():
    database, _, channel, member = _run([_row(mute=1, end_mute=PAST)])
    member.remove_roles.assert_awaited_once()
    channel.send.assert_awaited_once()
    database.delTimer.assert_called_once_with("1")


def test_expired_mute_keeps_a_running_tempban():
    """delTimer deletes the whole row: the ban timer of the same user must survive."""
    database, guild, _, member = _run([_row(ban=1, mute=1, end_ban=FUTURE, end_mute=PAST)])
    member.remove_roles.assert_awaited_once()
    database.delTimer.assert_not_called()
    database.endTimerMute.assert_called_once_with("1")
    guild.unban.assert_not_awaited()


def test_expired_ban_keeps_a_running_mute():
    database, guild, _, member = _run([_row(ban=1, mute=1, end_ban=PAST, end_mute=FUTURE)])
    guild.unban.assert_awaited_once()
    database.delTimer.assert_not_called()
    database.endTimerBan.assert_called_once_with("1")


def test_both_expired_delete_the_row():
    database, _, _, _ = _run([_row(ban=1, mute=1, end_ban=PAST, end_mute=PAST)])
    database.delTimer.assert_called_once_with("1")
    database.endTimerMute.assert_not_called()


def _not_found():
    return discord.NotFound(MagicMock(status=404), "gone")


def _server_error():
    return discord.DiscordServerError(MagicMock(status=503), "down")


def test_mute_of_a_user_who_left_is_dropped():
    database, guild, channel, _ = _setup([_row(mute=1, end_mute=PAST)])
    guild.fetch_member.side_effect = _not_found()
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delTimer.assert_called_once_with("1")


def test_mute_is_kept_when_discord_fails():
    """A transient error must not drop the timer: the user would stay muted forever."""
    database, guild, channel, _ = _setup([_row(mute=1, end_mute=PAST)])
    guild.fetch_member.side_effect = _server_error()
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delTimer.assert_not_called()
    database.endTimerMute.assert_not_called()


def test_mute_is_kept_when_the_role_removal_fails():
    database, guild, channel, member = _setup([_row(mute=1, end_mute=PAST)])
    member.remove_roles.side_effect = _server_error()
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delTimer.assert_not_called()


def test_ban_already_lifted_is_dropped():
    database, guild, channel, _ = _setup([_row(ban=1, end_ban=PAST)])
    guild.unban.side_effect = _not_found()
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delTimer.assert_called_once_with("1")


def test_ban_is_kept_when_the_unban_fails():
    database, guild, channel, _ = _setup([_row(ban=1, end_ban=PAST)])
    guild.unban.side_effect = _server_error()
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delTimer.assert_not_called()
    channel.send.assert_not_awaited()


def test_ban_is_lifted_by_id_without_fetching_the_user():
    """A deleted account cannot be fetched, but its ban can be lifted by ID."""
    _, guild, _, _ = _run([_row(ban=1, end_ban=PAST)])
    assert guild.unban.await_args.args[0].id == 1


def test_running_mute_is_kept():
    database, _, _, member = _run([_row(mute=1, end_mute=FUTURE)])
    member.remove_roles.assert_not_awaited()
    database.delTimer.assert_not_called()


def test_expired_ban_is_removed():
    database, guild, _, _ = _run([_row(ban=1, end_ban=PAST)])
    guild.unban.assert_awaited_once()
    database.delTimer.assert_called_once_with("1")


def test_running_ban_does_not_block_the_loop():
    """The old code slept until the ban ended, so the hourly loop stopped for days."""
    database, guild, _, _ = _run([_row(ban=1, end_ban=FUTURE)])
    guild.unban.assert_not_awaited()
    database.delTimer.assert_not_called()


def test_row_without_timers_is_deleted_by_user_id():
    database, _, _, _ = _run([_row()])
    database.delTimer.assert_called_once_with("1")


def test_old_jac_entries_are_pruned():
    database, guild, channel, _ = _setup([])
    database.getJac.return_value = [
        {"user_id": "1", "date": "Oct-01-2026 10:00:00"},
        {"user_id": "2", "date": "Oct-28-2026 10:00:00"},
    ]
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delJac.assert_called_once_with("1")


def test_bad_jac_date_does_not_stop_the_prune():
    """An ISO date (old web UI) raised ValueError and stopped the prune of the next rows."""
    database, guild, channel, _ = _setup([])
    database.getJac.return_value = [
        {"user_id": "3", "date": "2026-10-01 10:00:00"},
        {"user_id": "1", "date": "Oct-01-2026 10:00:00"},
    ]
    asyncio.run(timers.check_all(database, guild, channel, NOW))
    database.delJac.assert_called_once_with("1")
