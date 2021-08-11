# pylint: disable=F0401
import os, sys, traceback
import logging
import discord
from discord.ext import commands, tasks
from discord_slash import SlashCommand
from dotenv import load_dotenv
import asyncio
import config, shelve, pytz
from datetime import datetime, timedelta
from cogwatch import Watcher


# System setup
log = logging.getLogger('discord')
log.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
log.addHandler(handler)

# cogwatch logger
watch_log = logging.getLogger('cogwatch')
watch_log.setLevel(logging.INFO)
watch_handler = logging.StreamHandler(sys.stdout)
watch_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
watch_log.addHandler(watch_handler)

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot setup
init_extensions = [ 'cogs.moderation',
                    'cogs.moderation-slash',
                    'cogs.users',
                    'cogs.users-slash',
                    'cogs.events']

intents = discord.Intents.default()
intents.presences = True
intents.members = True
bot = commands.Bot(command_prefix='!', help_command=None, intents=intents)

slash = SlashCommand(bot, sync_commands=True)

timelines = []

# Here starts the logic
if __name__ == '__main__':
    for extension in init_extensions:
        try:
            bot.load_extension(extension)
        except Exception as e:
            print(f'can\'t load extension {extension}')
            log.error(f'Failed to load extension {extension}.')
            traceback.print_exc()


@tasks.loop(minutes=60)
async def check_timers():
    
    # Setup variables
    guild = await bot.fetch_guild(config.GUILD)
    channel = bot.get_channel(config.LOG_CHAN)

    # Run through the timers
    # JAC refers to channel join-a-clan, where clan ads are posted
    try:
        print('Checking if there are JAC logs to remove...')

        jac = shelve.open(config.JAC)
        for elem in jac:
            # setup current time
            tz_TX = pytz.timezone('US/central')
            now_string = datetime.now(tz_TX).strftime('%b-%d-%Y')
            now = datetime.strptime(now_string, '%b-%d-%Y')
            time = datetime.strptime(jac[elem]['date'].split(" ")[0],'%b-%d-%Y')
            delta = timedelta(days=14)
            newtime = time + delta

            # check if same day or passed
            if newtime <= now:
                print(f'Removing entry for {elem}')
                del jac[elem]

        jac.close()

        print('Checking if I missed some unbanning or unmuting...')
        t = shelve.open(config.TIMED, writeback=True)
        # Cycle shelve database to check for timed events to resume
        for mem in t:
            print(mem + '- Ban: ' + str(t[mem]['ban']) + ', Mute: ' + str(t[mem]['mute']))
            if t[mem]['mute']:
                time = datetime.strptime(t[mem]['endMute'], '%b-%d-%Y %H:%M:%S')
                tz_TX = pytz.timezone('US/Central')
                now_string = datetime.now(tz_TX).strftime('%b-%d-%Y %H:%M:%S')
                now = datetime.strptime(now_string, '%b-%d-%Y %H:%M:%S')
                
                if time < now:
                    print(f'\nUser {mem} needs to be unmuted.')

                    try:
                        member = await guild.fetch_member(int(mem))
                        role = guild.get_role(config.MUTE_ID)

                        embed = discord.Embed(title = 'Timed mute complete',
                                    description = f'User {member} has been unmuted automatically.',
                                    colour=config.YELLOW)
                        embed.set_footer(text=config.FOOTER)

                        await channel.send(content=None, embed=embed)
                        await member.remove_roles(role)

                    except:
                        print('\nError in fetching user, removing entry from db...')
                    
                    t[mem]['mute'] = False
                    t[mem]['endMute'] = None
                    t.sync()


            if t[mem]['ban']:
                time = datetime.strptime(t[mem]['endBan'], '%b-%d-%Y %H:%M:%S')
                tz_TX = pytz.timezone('US/Central')
                now_string = datetime.now(tz_TX).strftime('%b-%d-%Y %H:%M:%S')
                now = datetime.strptime(now_string, '%b-%d-%Y %H:%M:%S')

                if time < now:

                    user = await bot.fetch_user(int(mem))

                    embed = discord.Embed(title = 'Timed ban complete',
                                description = f'User {user.name}#{user.discriminator} has been unbanned automatically.',
                                colour=config.YELLOW)
                    embed.set_footer(text=config.FOOTER)

                    await channel.send(content=None, embed=embed)

                    await guild.unban(user)
                    t[mem]['ban'] = False
                    t[mem]['endBan'] = None
                    t.sync()
                
                elif time > now:
                    print(f'\nUser {mem} is tempbanned. Adding to wait...')
                    t.close()
                    await asyncio.sleep((time - now).total_seconds())
                    await guild.unban(user)
                    t = shelve.open(config.TIMED)
                    t[mem]['ban'] = False
                    t[mem]['endBan'] = None
                    t.sync()

            if not t[mem]['mute'] and not t[mem]['ban']:
                print(f'\nUser {mem} has no more timers. Removing from db...')
                del t[mem]
        t.close()

        
        print('Done! Waiting 60 minutes for next check...')
    except:
        print('Error while checking timers, waiting next loop...')

# When bot is loaded up and ready
@bot.event
async def on_ready():

    watcher = Watcher(bot, path='cogs')
    await watcher.start()

    print(f'\nLogged in as {bot.user.name} - {bot.user.id}\nAPI version: {discord.__version__}')
    tz_IT = pytz.timezone('Europe/Rome')
    current_time = datetime.now(tz_IT).strftime('%b-%d-%Y %H:%M:%S')
    print(f'Current time and date (UTC+1): {current_time}')
    print('-----------')
    await bot.wait_until_ready()

    if not check_timers.is_running():
        check_timers.start()

# Manage errors globally
@bot.event
async def on_command_error(ctx, error):
    log.error(error)

#check_timers.start()
bot.run(TOKEN, bot=True, reconnect=True)