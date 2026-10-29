# pylint: disable=F0401, W0702, W0703, W0105, W0613, E1101
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import pytz
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from cogwatch import Watcher
import config
import support
import bot_setup
import timers
import cogs.database as db

#Setup module logging
log = support.get_logger(__name__)

# cogwatch logger
#Setup module logging
watch_log = logging.getLogger("cogwatch")
watch_log.setLevel(logging.INFO)

log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

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
intents = bot_setup.build_intents()

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    help_command=None,
    owner_id=config.CRYO_ID,
    intents=intents,
)

database = db.AsyncDatabase(bot)

# on_ready fires again after a new gateway session: start cogwatch only once
watcher = None

# Here starts the logic
if __name__ == "__main__":
    """Load the extensions from the list and launch a warning on failure."""
    for extension in bot_setup.INIT_EXTENSIONS:
        try:
            print(f"INFO: Loading extension {extension}")
            bot.load_extension(extension)
        except Exception as exception:
            log.exception("Failed to load extension %s", extension)


@tasks.loop(minutes=60)
async def check_timers():
    """Task that runs every 60 minutes, checking all active timers for any that finished.

    tasks.loop stops for good on an exception it does not retry (for example a
    discord.HTTPException), so every error is caught here.
    """
    try:
        # Setup variables
        guild = await bot.fetch_guild(config.GUILD)
        channel = bot.get_channel(config.LOG_CHAN)

        # Setup current time
        tz_TX = pytz.timezone("US/central")
        now_string = datetime.now(tz_TX).strftime("%b-%d-%Y %H:%M:%S")
        now = datetime.strptime(now_string, "%b-%d-%Y %H:%M:%S")

        # Run through the timers
        # JAC refers to channel join-a-clan, where clan ads are posted
        await timers.check_all(database, guild, channel, now)
    except Exception:
        log.exception("Error while checking timers, waiting next loop...")

@tasks.loop(minutes=15)
async def war_channel():
    """Repost config.WAR_MSG when it is not in the last 25 messages of the war channel."""
    # An uncaught exception would stop the loop for good (see check_timers)
    try:
        channel = bot.get_channel(config.WAR_CHAN)

        messages = await channel.history(limit=25).flatten()

        for msg in messages:
            if msg.author == bot.user:
                return

        await channel.send(config.WAR_MSG)
    except Exception:
        log.exception("Error in the war channel task, waiting next loop...")

@bot.event
async def on_ready():
    """Function called when bot is ready to operate, starts cogwatcher and tasks."""
    global watcher

    # Start cogwatch: one watcher, else one save reloads the cog once per watcher
    if watcher is None:
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
