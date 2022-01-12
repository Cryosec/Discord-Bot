# pylint: disable=F0401, W0702, W0703, W0105, W0613
import os, traceback
import logging
import asyncio
from datetime import datetime, timedelta
import shelve, pytz
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from cogwatch import Watcher
import config

# System setup
log = logging.getLogger("discord")
log.setLevel(logging.WARNING)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
log.addHandler(handler)

# cogwatch logger
# watch_log = logging.getLogger('cogwatch')
# watch_log.setLevel(logging.INFO)
# watch_handler = logging.FileHandler(filename='cogwatch.log', encoding='utf-8', mode='w')
# watch_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# watch_log.addHandler(watch_handler)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot setup
init_extensions = [
    "cogs.admin",
    "cogs.moderation",
    "cogs.moderation-slash",
    "cogs.users",
    "cogs.users-slash",
    "cogs.events",
    "cogs.giveaway",
    "cogs.poll",
]

intents = discord.Intents.default()
intents.presences = True
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    help_command=None,
    owner_id=config.CRYO_ID,
    intents=intents,
)


# Here starts the logic
if __name__ == "__main__":
    """Load the extensions from the list and launch a warning on failure."""
    for extension in init_extensions:
        try:
            print(f"INFO: Loading extension {extension}")
            bot.load_extension(extension)
        except Exception as exception:
            print(f"ERROR: can't load extension {extension}")
            log.error("Failed to load extension %s", extension)
            traceback.print_exc()


async def check_jac_timers(now):
    """Check which JAC timers have surpassed 14 days and remove from list."""
    print("Checking if there are JAC logs to remove...")

    jac = shelve.open(config.JAC)
    for elem in jac:
        # entry_time = datetime.strptime(jac[elem]['date'].split(" ")[0],'%b-%d-%Y')
        entry_time = datetime.strptime(jac[elem]["date"], "%b-%d-%Y %H:%M:%S")
        delta = timedelta(days=14)
        newtime = entry_time + delta

        # check if 14 days have passed
        if newtime < now:
            print(f"Removing entry for {elem}")
            del jac[elem]

    jac.close()


async def check_mute_timers(now, time_db, guild, channel, mem):
    """Check which finished mute timers have been missed and remove the mute."""
    mute_time = datetime.strptime(time_db[mem]["endMute"], "%b-%d-%Y %H:%M:%S")

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
            print("\nError in fetching user, removing entry from db...")

        time_db[mem]["mute"] = False
        time_db[mem]["endMute"] = None
        time_db.sync()


async def check_ban_timers(now, time_db, guild, channel, mem):
    """Check which finished ban timers have been missed and remove the ban"""
    ban_time = datetime.strptime(time_db[mem]["endBan"], "%b-%d-%Y %H:%M:%S")

    # If timer ran out, unban user
    if ban_time < now:

        user = await bot.fetch_user(int(mem))
        # Create embed to log unbanning
        embed = discord.Embed(
            title="Timed ban complete",
            description=f"User {user.name}#{user.discriminator} \
                    has been unbanned automatically.",
            colour=config.YELLOW,
        )
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)

        try:
            await guild.unban(user)
        except:
            print("Error while executing timed unban")
        time_db[mem]["ban"] = False
        time_db[mem]["endBan"] = None
        time_db.sync()
    # Re-add the timer to the list -- this could cause duplicate timers
    elif ban_time > now:
        user = await bot.fetch_user(int(mem))
        print(f"\nUser {mem} is tempbanned. Adding to wait...")
        time_db.close()
        await asyncio.sleep((ban_time - now).total_seconds())
        try:
            await guild.unban(user)
        except:
            print("Error while executing timed unban")
        time_db = shelve.open(config.TIMED)
        time_db[mem]["ban"] = False
        time_db[mem]["endBan"] = None
        time_db.sync()


@tasks.loop(minutes=60)
async def check_timers():
    """Task that runs every 60 minutes, checking all active timers for any that finished."""
    # Setup variables
    guild = await bot.fetch_guild(config.GUILD)
    channel = bot.get_channel(config.LOG_CHAN)

    # Setup current time
    tz_TX = pytz.timezone("US/central")
    now_string = datetime.now(tz_TX).strftime("%b-%d-%Y %H:%M:%S")
    now = datetime.strptime(now_string, "%b-%d-%Y %H:%M:%S")

    # Run through the timers
    # JAC refers to channel join-a-clan, where clan ads are posted
    try:
        await check_jac_timers(now)

        print("Checking if I missed some unbanning or unmuting...")
        t = shelve.open(config.TIMED, writeback=True)

        # Cycle shelve database to check for timed events to resume
        for mem in t:
            print(
                mem + "- Ban: " + str(t[mem]["ban"]) + ", Mute: " + str(t[mem]["mute"])
            )
            if t[mem]["mute"]:
                await check_mute_timers(now, t, guild, channel, mem)

            if t[mem]["ban"]:
                await check_ban_timers(now, t, guild, channel, mem)

            # If there are no more timers for a user, there's no need to keep track of them
            if not t[mem]["mute"] and not t[mem]["ban"]:
                print(f"\nUser {mem} has no more timers. Removing from db...")
                del t[mem]
        t.close()

        print("Done! Waiting 60 minutes for next check...")
        print("-----------")
    except:
        print("Error while checking timers, waiting next loop...")
        traceback.print_exc()
        print("-----------")


@bot.event
async def on_ready():
    """Function called when bot is ready to operate, starts cogwatcher and tasks."""
    # watcher = Watcher(bot, path='cogs')
    # await watcher.start()

    # Register persistent views for listening
    # if not self.persistent_views_added:
    # self.add_view(support.Unban())
    # self.add_view(support.Scam())
    # self.persistent_views_added = True
    # pass

    print(
        f"\nLogged in as {bot.user.name} - {bot.user.id}\nAPI version: {discord.__version__}"
    )
    tz_IT = pytz.timezone("Europe/Rome")
    current_time = datetime.now(tz_IT).strftime("%b-%d-%Y %H:%M:%S")
    print(f"Current time and date (UTC+1): {current_time}")
    print("-----------")
    await bot.wait_until_ready()

    if not check_timers.is_running():
        check_timers.start()


# Manage errors globally
@bot.event
async def on_command_error(ctx, error):
    """Log the error output by a command."""
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply("This command is currently on cooldown.", ephemeral=True)
        log.error(error)
    else:
        raise error

@bot.event
async def on_application_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.respond("This command is currently on cooldown.", ephemeral=True)
    else:
        raise error


bot.run(str(TOKEN), reconnect=True)
