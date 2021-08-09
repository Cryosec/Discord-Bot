# pylint: disable=F0401
import discord
from discord.ext import commands
from datetime import datetime
import config
import moderation as mod
import giveaway as ga
import pytz
from discord_slash import SlashCommand, cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_permission, create_choice
from discord_slash.model import SlashCommandPermissionType

ROLES_BRIEF = 'Get information about roles used in the server'
TWITCH_BRIEF = 'Get information about the Twitch integration'
PATREON_BRIEF = 'Get information about the Patreon integration'
FAQ_BRIEF = 'Get information about the most frequently asked questions'
JOINED_BRIEF = 'Get information about when you last joined the server'
ME_BRIEF = 'Get information on your Account in the server. Once per day.'


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
Content Creators. This role is invite-only.\n
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
**Gasoline Addicts**
Vroom vroom goes the role for those who loves vehicles. Granted case-by-case by Mods/Admins.\n
**Stonkychonk**
This is not the role you're looking for. Move along.\n
**Tarkov Escapist**
Members who are experiend Tarkov players. Granted case-by-case by Mods/Admins.\n
**Arma Vet**
Members who are experienced ArmA 3 veterans. Granted case-by-case by Mods/Admins.\n
**Blockhead**
Members who are way too much into Minecraft. Granted case-by-case by Mods/Admins.\n
**StarNerd**
Star Wars nerds. Kinda self explanatory. Granted case-by-case by Mods/Admins.\n
**Chef**
Quite obvious from the name. People who know how to cook something good-looking and not disgusting. Granted case-by-case by Mods/Admins.\n
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

class UsersSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /roles Command
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @cog_ext.cog_slash(
        name = 'roles',
        description = ROLES_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def roles(self, ctx: SlashContext): 

        embed = discord.Embed(title='Roles information', description=ROLES_INFO, colour=config.BLUE)
        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)


    # /twitch Command
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @cog_ext.cog_slash(
        name = 'twitch',
        description = TWITCH_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def twitch(self, ctx: SlashContext):

        embed = discord.Embed(title='Twitch information', url=TWTICH_URL, description=TWITCH_INFO, colour=config.PURPLE)
        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)

    # /faq Command
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @cog_ext.cog_slash(
        name = 'faq',
        description = FAQ_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def faq(self, ctx: SlashContext):

        embed = discord.Embed(title='Fequently Asked Questions', description=FAQ, colour=config.BLUE)
        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)


    # /me Command
    @commands.cooldown(1, 86400, commands.BucketType.member)
    @cog_ext.cog_slash(
        name = 'me',
        description = ME_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def me(self, ctx: SlashContext):
        member = ctx.message.author

        embed = discord.Embed(title=f'Information on {member.name}#{member.discriminator}', colour = member.colour)
        embed.set_thumbnail(url = member.avatar_url)

        # Account age
        creation_date = member.created_at.strftime('%b-%d-%Y')
        
        #Last join
        joined = ctx.message.author.joined_at.strftime('%b-%d-%Y')

        # Is nitro boosting
        if member.premium_since is not None:
            boosting = member.premium_since.strftime('%b-%d-%Y')
        else:
            boosting = 'Not boosting'

        # Roles
        roles = member.roles
        role_mentions = [role.mention for role in roles]
        role_list = ", ".join(role_mentions)

        embed.add_field(name='Creation date', value=creation_date, inline=True)
        embed.add_field(name='Last join', value=joined, inline=True)
        embed.add_field(name='Boosting since', value=boosting, inline=False)
        embed.add_field(name='Roles', value = role_list, inline=False)

        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(UsersSlash(bot))