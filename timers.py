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
    """Remove the JAC entries older than 14 days."""
    for elem in database.getJac():
        entry_time = datetime.strptime(elem['date'], TIME_FORMAT)
        if entry_time + timedelta(days=JAC_DAYS) < now:
            print(f"Removing entry for {elem['user_id']}")
            database.delJac(elem['user_id'])


async def check_mute_timers(now, time_db, guild, channel) -> bool:
    """Remove the mute role when a timed mute ends. True if the mute ended."""
    mem = time_db['user_id']
    mute_time = datetime.strptime(time_db['endMute'], TIME_FORMAT)

    # If timer ran out, unmute user
    if mute_time < now:
        print(f"\nUser {mem} needs to be unmuted.")

        try:
            member = await guild.fetch_member(int(mem))
            role = guild.get_role(config.MUTE_ID)
            # Create embed to log unmuting
            embed = discord.Embed(
                title="Timed mute complete",
                description=f"User {member} has been unmuted automatically.",
                colour=config.YELLOW,
            )
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)
            await member.remove_roles(role)

        except:
            log.exception("\nError in fetching user, removing mute timer from db...")
        return True
    return False


async def check_ban_timers(bot, now, time_db, guild, channel) -> bool:
    """Unban the user when a timed ban ends. True if the ban ended.

    A ban that is still running waits for a later hourly check: the unban can be
    up to 60 minutes late, but the loop does not stop.
    """
    mem = time_db['user_id']
    ban_time = datetime.strptime(time_db['endBan'], TIME_FORMAT)

    # If timer ran out, unban user
    if ban_time < now:

        user = await bot.fetch_user(int(mem))
        # Create embed to log unbanning
        embed = discord.Embed(
            title="Timed ban complete",
            description=f"User {user.name}#{user.discriminator} has been unbanned automatically.",
            colour=config.YELLOW,
        )
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)

        try:
            await guild.unban(user)
        except:
            log.exception("Error while executing timed unban")
        return True
    return False


async def check_all(bot, database, guild, channel, now):
    """Run every check. An error on one timer does not stop the others."""
    try:
        await check_jac_timers(database, now)
    except:
        log.exception("Error while checking JAC timers")

    for elem in database.getTimers():
        try:
            user_id = str(elem['user_id'])
            print(f"{user_id} - Ban: {elem['ban']}, Mute: {elem['mute']}")
            mute_ended = bool(elem['mute']) and await check_mute_timers(now, elem, guild, channel)
            ban_ended = bool(elem['ban']) and await check_ban_timers(bot, now, elem, guild, channel)
            mute_left = bool(elem['mute']) and not mute_ended
            ban_left = bool(elem['ban']) and not ban_ended

            # One row per user holds both timers: delTimer deletes the row, so
            # use it only when no timer is left.
            if not mute_left and not ban_left:
                print(f"\nUser {user_id} has no more timers. Removing from db...")
                database.delTimer(user_id)
            elif mute_ended:
                database.endTimerMute(user_id)
            elif ban_ended:
                database.endTimerBan(user_id)
        except:
            log.exception("Error while checking the timers of %s", elem.get('user_id'))
