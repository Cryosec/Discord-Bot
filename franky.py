# pylint: disable=F0401, W0702, W0703, W0105, W0613, E1101
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import os
import logging
from logging.handlers import RotatingFileHandler
import asyncio
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from cogwatch import Watcher
import config
import support
import cogs.database as db

#Setup module logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")

file_handler = RotatingFileHandler(
    filename=f"logs/{__name__}.log",
    mode="a",
    maxBytes=20000,
    backupCount=5,
    encoding="utf-8")
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

log.addHandler(file_handler)
log.addHandler(console_handler)

# cogwatch logger
#Setup module logging
watch_log = logging.getLogger("cogwatch")
watch_log.setLevel(logging.INFO)

watch_file_handler = RotatingFileHandler(
    filename="logs/cogwatch.log",
    mode="a",
    maxBytes=20000,
    backupCount=5,
    encoding="utf-8")
watch_file_handler.setFormatter(log_formatter)

watch_log.addHandler(watch_file_handler)
watch_log.addHandler(console_handler)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot setup
init_extensions = [
    "cogs.admin",
    "cogs.moderation",
    "cogs.moderation_slash",
    "cogs.users",
    "cogs.users-slash",
    "cogs.events",
    #"cogs.giveaway",
    #"cogs.poll",
    #"cogs.modalpoll",
]

intents = discord.Intents.default()
intents.presences = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    help_command=None,
    owner_id=config.CRYO_ID,
    intents=intents,
)

database = db.Database(bot)

# Here starts the logic
if __name__ == "__main__":
    """Load the extensions from the list and launch a warning on failure."""
    for extension in init_extensions:
        try:
            print(f"INFO: Loading extension {extension}")
            bot.load_extension(extension)
        except Exception as exception:
            log.exception("Failed to load extension %s", extension)


async def check_jac_timers(now):
    """Check which JAC timers have surpassed 14 days and remove from list."""
    #print("Checking if there are JAC logs to remove...")

    jac = database.getJac()
    for elem in jac:
        # entry_time = datetime.strptime(jac[elem]['date'].split(" ")[0],'%b-%d-%Y')
        entry_time = datetime.strptime(elem['date'], "%b-%d-%Y %H:%M:%S")
        delta = timedelta(days=14)
        newtime = entry_time + delta

        # check if 14 days have passed
        if newtime < now:
            print(f"Removing entry for {elem['user_id']}")
            #del jac[elem]
            database.delJac(elem['user_id'])


async def check_mute_timers(now, time_db, guild, channel, mem):
    """Check which finished mute timers have been missed and remove the mute."""
    mute_time = datetime.strptime(time_db[4], "%b-%d-%Y %H:%M:%S")

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

            database.delTimer(str(mem))

        except:
            log.exception("\nError in fetching user, removing entry from db...")
            database.delTimer(str(mem))


async def check_ban_timers(now, time_db, guild, channel, mem):
    """Check which finished ban timers have been missed and remove the ban"""
    ban_time = datetime.strptime(time_db['endBan'], "%b-%d-%Y %H:%M:%S")

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
            log.exception("Error while executing timed unban")
        database.delTimer(str(mem))

    # Re-add the timer to the list -- this could cause duplicate timers
    elif ban_time > now:
        user = await bot.fetch_user(int(mem))
        print(f"\nUser {mem} is tempbanned. Adding to wait...")
        await asyncio.sleep((ban_time - now).total_seconds())
        try:
            await guild.unban(user)
        except:
            log.exception("Error while executing timed unban")
        database.delTimer(str(mem))


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

        #print("Checking if I missed some unbanning or unmuting...")
        timers = database.getTimers()

        # Cycle database to check for timed events to resume
        for elem in timers:
            print(
                elem['user_id'] + "- Ban: " + str(elem['ban']) + ", Mute: " + str(elem['mute'])
            )
            if elem['mute']:
                await check_mute_timers(now, elem, guild, channel, elem['user_id'])

            if elem['ban']:
                await check_ban_timers(now, elem, guild, channel, elem['user_id'])

            # If there are no more timers for a user, there's no need to keep track of them
            if not elem['mute'] and not elem['ban']:
                print(f"\nUser {elem['user_id']} has no more timers. Removing from db...")
                database.delTimer(str(elem[0]))

        #print("Done! Waiting 60 minutes for next check...")
        #print("-----------")
    except:
        log.exception("Error while checking timers, waiting next loop...")
        #print("-----------")

@tasks.loop(minutes=15)
async def war_channel():

    #guild = await bot.fetch_guild(config.GUILD)
    channel = bot.get_channel(config.WAR_CHAN)

    messages = await channel.history(limit=25).flatten()

    for msg in messages:
        if msg.author == bot.user:
            return

    await channel.send(config.WAR_MSG)

@bot.event
async def on_ready():
    """Function called when bot is ready to operate, starts cogwatcher and tasks."""

    # Start cogwatch
    watcher = Watcher(bot, path='cogs')
    await watcher.start()

    # Register view for persistence
    bot.add_view(support.Survivor())

    print(
        f"\nLogged in as {bot.user.name} - {bot.user.id}\nAPI version: {discord.__version__}"
    )
    tz_IT = pytz.timezone("Europe/Rome")
    current_time = datetime.now(tz_IT).strftime("%b-%d-%Y %H:%M:%S")
    print(f"Current time and date (UTC+1): {current_time} UTC/Rome")
    print("-----------")
    await bot.wait_until_ready()

    if not check_timers.is_running():
        check_timers.start()

    if not war_channel.is_running():
        war_channel.start()

# Manage errors globally
@bot.event
async def on_command_error(ctx, error):
    """Log the error output by a command."""
    if isinstance(error, commands.CommandOnCooldown):
        #await ctx.reply("This command is currently on cooldown.", ephemeral=True)
        log.error(error)
    elif isinstance(error, commands.CommandNotFound):
        log.error(error)
    else:
        raise error

@bot.event
async def on_application_command_error(ctx, error):
    """Log the error output by application commands."""
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.respond("This command is currently on cooldown.", ephemeral=True)
    else:
        raise error


bot.run(str(TOKEN), reconnect=True)
