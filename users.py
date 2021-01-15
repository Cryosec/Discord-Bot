import discord
from discord.ext import commands
from datetime import datetime
import config
import moderation as mod

### CONSTANTS ###
# Help messages by command
ROLES_BRIEF = 'Get information about roles used in the server'
TWITCH_BRIEF = 'Get information about the Twitch integration'
PATREON_BRIEF = 'Get information about the Patreon integration'
FAQ_BRIEF = 'Get information about the most frequently asked questions'
JOINED_BRIEF = 'Get information about when you last joined the server'

# Long text constants here
HELP_INFO_USER = f'''
```asciidoc
*User available commands:*
!roles  :: {ROLES_BRIEF}
!twitch :: {TWITCH_BRIEF}
!faq    :: {FAQ_BRIEF}
!joined :: {JOINED_BRIEF}
```
'''

HELP_INFO_MOD = f'''
```asciidoc
*User available commands:*
!roles  :: {ROLES_BRIEF}
!twitch :: {TWITCH_BRIEF}
!faq    :: {FAQ_BRIEF}
!joined :: {JOINED_BRIEF}

*Moderation available commands:*
!mute   :: {mod.BRIEF_MUTE}
!unmute :: {mod.BRIEF_UNMUTE}
!warn   :: {mod.BRIEF_WARN}
!unwarn :: {mod.BRIEF_UNWARN}
!warns  :: {mod.BRIEF_WARNINGS}
!cwarn  :: {mod.BRIEF_CLEAR}
!status :: {mod.BRIEF_STATUS}
!timers :: {mod.BRIEF_TIMERS}
!delete :: {mod.BRIEF_DELETE}
!kick   :: {mod.BRIEF_KICK}
!ban    :: {mod.BRIEF_BAN}
!tempban:: {mod.BRIEF_TEMPBAN}

== type !help <command> for specific help about that command.
```
'''

ROLES_INFO = """
**Lord Franklin's Servants**
Owners of the server.\n
**Admins**
Friends of Drewski who Administrate the community.\n
**Moderators**
Hand picked community members who have been around for years and keep the community safe.\n
**Community Regular**
Long time members of the community. Granted case-by-case by Admins.\n
**YouTuber/Streamer**
Content Creators. If you have a Channel/Stream with a sizable following, DM a Moderator/Admin with proof to get the role.\n
**Patreon Operators**
Members who support Drewski on Patreon, use !patreon for more information.\n
**Twitch Subscriber**
Members who are subscribed to OperatorDrewski on Twitch. If you are a subscriber, use the command `!twitch` for instructions on how to get the role.\n
**Supporter**
Members who have donated to Drewski during live streams.\n
**Tech Support**
Experienced PC Builders and Tech masters. Mention this role in #tech_talk for help. Granted case-by-case by Mods/Admins.\n
**Aviator**
Members who are knowledgable/experienced with aircraft. Granted case-by-case by Mods/Admins.\n
**Ballistics Autistics**
Members who are very knowledgeable about real steel firearms. Granted case-by-case by Mods/Admins.\n
**Airsoft Nerds**
Members who are very knowledgeable about airsoft guns and gear. Granted case-by-case by Mods/Admins.\n
**Arma Vet**
Members who are experienced ArmA 3 veterans. Granted case-by-case by Mods/Admins.\n
**Blockhead**
Members who are way too much into Minecraft. Granted case-by-case by Mods/Admins.\n
**Gamers**
I don't know why this exists. Lottery wanted it so now we have it. Granted case-by-case by Mods/Admins\n
    
"""

TWITCH_INFO = """
**How do I get the Twitch Subscriber role?**
You can get the role by connecting your Twitch account to Discord. 
You can do so by going into User Settings > Connections > Twitch, clicking on the Twitch icon will open twitch.tv where you can authorize Discord to access your account. 
Once you have connect Twitch to Discord, it can take up to 1 hour for the server to sync with Twitch and update your roles.\n
**What do I get with the Twitch Subscriber role?**
Being a sub gives you access to the #subs_n_patrons text and voice channels where other subscribers and cool people from the community hang out. 
You can even find Drewski and the other Admins/Mods hanging around and playing games from time to time.\n
**What happens when my Twitch subscription runs out?**
We have implemented a 30 day grace period before the Twitch Subscriber role is taken away and you lose access to the private channels. 
If you renew your subscription within that time, the role will stay until your subscription runs out again.
"""
TWTICH_URL = 'https://support.discord.com/hc/en-us/articles/212112068-Twitch-Integration-FAQ'

FAQ = """
**How can I play with Drewski?**
Unfortunately, the short answer is that you probably can't. Being a Youtuber means being busy a lot, and organizing/participating in public events usually means a lot of time and hassle. 
The notable exceptions are the few games we will play with members of #subs_n_patrons and livestream events with viewers.\n
**How can I play on Drewski's ArmA 3 server?**
We don't actually have a public ArmA 3 server, all of the operations that you see in videos are hosted on a private server session. 
You can check out #announcements for a brief overview of the modpacks we usually use if you want to recreate the general structure of our operations.\n
**Where's the DayZ server?**
Server has been shutdown for various reasons. There is no plan to open a new one currently.\n
**How do I post pictures in channels?**
Due to previous offenders posting not-okay images and links in public channels, we made the decision to restrict pictures from members with no roles. 
If you would like to post a picture, you can politely ask someone with a role to repost the picture/link for you. They do reserve the right to say no.\n
**How do I get a role?**
You can use `!roles` to see information about each of this server's roles and how you can get them.\n
**I'm a Twitch subscriber / Patreon supporter, Where's my role?**
You can type `!twitch` or `!patreon` for details on how to link those accounts to Discord to automatically get the respective roles.\n
**What is the purpose of ____ channel?**
Every text channel has a description at the top which you can click on to expand and view fully, it also highly advised to check the pinned messages for important information/guidelines by clicking the push pin icon at the top right of the channel.\n

"""
class Users(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Answer to command !help
    @commands.command(name='help')
    #@commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def help(self, ctx, command=None):
        
        role = ctx.guild.get_role(config.MOD_ID)
        # if message author is a moderator
        if role in ctx.message.author.roles:
            if command is None:
                answer = HELP_INFO_MOD

                embed = discord.Embed(title='Commands information', description=answer, colour=config.BLUE)
                embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
                embed.set_footer(text=config.FOOTER)
                await ctx.send(content=None, embed=embed)
            else:
                def f(x):
                    return {
                        'mute': mod.HELP_MUTE,
                        'unmute': mod.HELP_UNMUTE,
                        'warn': mod.HELP_WARN,
                        'unwarn': mod.HELP_UNWARN,
                        'warns': mod.HELP_WARNINGS,
                        'cwarn': mod.HELP_CLEAR,
                        'delete': mod.HELP_DELETE,
                        'status': mod.HELP_STATUS,
                        'kick': mod.HELP_KICK,
                        'ban': mod.HELP_BAN,
                        'tempban': mod.HELP_TEMPBAN,
                    }[x]
                answer = f(command)
                
                embed = discord.Embed(title='Command information', description=answer, colour=config.BLUE)
                embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
                embed.set_footer(text=config.FOOTER)
                await ctx.send(content=None, embed=embed)

        # if message author is not a moderator
        else:

            if ctx.message.channel.id != config.UCMD_CHAN:
                await ctx.send(f'Use <#{config.UCMD_CHAN}> for bot commands.')
            else:
                answer = HELP_INFO_USER

                embed = discord.Embed(title='Commands information', description=answer, colour=config.BLUE)
                embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
                embed.set_footer(text=config.FOOTER)
                await ctx.send(content=None, embed=embed)

            

    # Answer to command !roles
    @commands.command(name='roles', brief=ROLES_BRIEF)
    # 1 usage every 30 seconds per channel
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def roles(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID) 

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.send(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            answer = ROLES_INFO

            embed = discord.Embed(title='Roles information', description=answer, colour=config.BLUE)
            embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.send(content=None, embed=embed)

    # Answer to command !twitch
    @commands.command(name='twitch', brief=TWITCH_BRIEF)
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def twitch(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.send(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            answer = TWITCH_INFO

            embed = discord.Embed(title='Twitch information', url=TWTICH_URL, description=answer, colour=config.PURPLE)
            embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.send(content=None, embed=embed)


    # Answer to command !faq
    @commands.command(name="faq", brief=FAQ_BRIEF)
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def faq(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.send(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            answer = FAQ

            embed = discord.Embed(title='Fequently Asked Questions', description=answer, colour=config.BLUE)
            embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.send(content=None, embed=embed)

    # Answer to command !joined
    @commands.command(name="joined", brief=JOINED_BRIEF)
    @commands.cooldown(1, 60, commands.BucketType.member)
    @commands.guild_only()
    async def joined(self, ctx):
        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.send(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            timestamp = ctx.message.author.joined_at.strftime('%b-%d-%Y')
            await ctx.send(f"{ctx.message.author.mention} you have joined the server on {timestamp}")

def setup(bot):
    bot.add_cog(Users(bot))