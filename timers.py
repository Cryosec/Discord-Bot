# pylint: disable=W0702, W0703
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Checks of the check_timers task in franky.py: JAC expiry, timed mutes and bans.

The rows of getJac and getTimers are dicts (column name -> value).
"""
from datetime import datetime, timedelta
import discord
import config
import support

log = support.get_logger(__name__)

TIME_FORMAT = "%b-%d-%Y %H:%M:%S"
JAC_DAYS = 14


async def check_jac_timers(database, now):
    """Remove the JAC entries older than 14 days. A bad row does not stop the others."""
    for elem in await database.getJac():
        try:
            entry_time = datetime.strptime(elem['date'], TIME_FORMAT)
        except (TypeError, ValueError):
            log.error("JAC entry of %s has an invalid date %r, not pruned", elem.get('user_id'), elem.get('date'))
            continue
        if entry_time + timedelta(days=JAC_DAYS) < now:
            print(f"Removing entry for {elem['user_id']}")
            await database.delJac(elem['user_id'])


async def check_mute_timers(now, time_db, guild, channel) -> bool:
    """Remove the mute role when a timed mute ends. True if the mute ended.

    Only a user who left ends the timer without the role removal. Other errors
    propagate: check_all keeps the timer and the next hourly check tries again.
    """
    mem = time_db['user_id']
    mute_time = datetime.strptime(time_db['endMute'], TIME_FORMAT)

    # If timer ran out, unmute user
    if mute_time < now:
        print(f"\nUser {mem} needs to be unmuted.")

        try:
            member = await guild.fetch_member(int(mem))
        except discord.NotFound:
            log.info("User %s left the server, removing mute timer from db...", mem)
            return True

        await member.remove_roles(guild.get_role(config.MUTE_ID))

        # Create embed to log unmuting
        embed = discord.Embed(
            title="Timed mute complete",
            description=f"User {member} has been unmuted automatically.",
            colour=config.YELLOW,
        )
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)
        return True
    return False


async def check_ban_timers(now, time_db, guild, channel) -> bool:
    """Unban the user when a timed ban ends. True if the ban ended.

    A ban that is still running waits for a later hourly check: the unban can be
    up to 60 minutes late, but the loop does not stop. The unban goes by ID, so
    it works also for a deleted account. Errors other than "not banned"
    propagate: check_all keeps the timer and the next hourly check tries again.
    """
    mem = time_db['user_id']
    ban_time = datetime.strptime(time_db['endBan'], TIME_FORMAT)

    # If timer ran out, unban user
    if ban_time < now:
        try:
            await guild.unban(discord.Object(id=int(mem)), reason="Temp ban concluded")
        except discord.NotFound:
            log.info("User %s is not banned anymore, removing ban timer from db...", mem)
            return True

        # Create embed to log unbanning
        embed = discord.Embed(
            title="Timed ban complete",
            description=f"User <@{mem}> ({mem}) has been unbanned automatically.",
            colour=config.YELLOW,
        )
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)
        return True
    return False


async def check_all(database, guild, channel, now):
    """Run every check. An error on one timer does not stop the others."""
    try:
        await check_jac_timers(database, now)
    except:
        log.exception("Error while checking JAC timers")

    for elem in await database.getTimers():
        try:
            user_id = str(elem['user_id'])
            print(f"{user_id} - Ban: {elem['ban']}, Mute: {elem['mute']}")
            mute_ended = bool(elem['mute']) and await check_mute_timers(now, elem, guild, channel)
            ban_ended = bool(elem['ban']) and await check_ban_timers(now, elem, guild, channel)
            mute_left = bool(elem['mute']) and not mute_ended
            ban_left = bool(elem['ban']) and not ban_ended

            # One row per user holds both timers: delTimer deletes the row, so
            # use it only when no timer is left.
            if not mute_left and not ban_left:
                print(f"\nUser {user_id} has no more timers. Removing from db...")
                await database.delTimer(user_id)
            elif mute_ended:
                await database.endTimerMute(user_id)
            elif ban_ended:
                await database.endTimerBan(user_id)
        except:
            log.exception("Error while checking the timers of %s", elem.get('user_id'))
