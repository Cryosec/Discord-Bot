# pylint: disable=F0401
import discord
from discord.ext import commands
from datetime import datetime
import config
import cogs.moderation as mod
import cogs.giveaway as ga
import pytz
from discord_slash import SlashCommand, cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_permission, create_choice
from discord_slash.model import SlashCommandPermissionType



class UsersSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /roles Command
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @cog_ext.cog_slash(
        name = 'roles',
        description = config.ROLES_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def roles(self, ctx: SlashContext): 

        embed = discord.Embed(title='Roles information', description=config.ROLES_INFO, colour=config.BLUE)
        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)

    # /dayz Command
    @commands.cooldown(1, 30, commands.BucketType.member)
    @cog_ext.cog_slash(
        name = 'dayz',
        description = config.DAYZ_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def dayz(self, ctx: SlashContext):

        embed = discord.Embed(
            title = 'Community DayZ Server Info:',
            description = config.DAYZ_DESC,
            colour = config.BLUE
        )
        embed.set_footer(text=config.FOOTER)

        await ctx.send(embed=embed)

    # /twitch Command
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @cog_ext.cog_slash(
        name = 'twitch',
        description = config.TWITCH_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def twitch(self, ctx: SlashContext):

        embed = discord.Embed(title='Twitch information', url=config.TWTICH_URL, description=config.TWITCH_INFO, colour=config.PURPLE)
        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)

    # /faq Command
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @cog_ext.cog_slash(
        name = 'faq',
        description = config.FAQ_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def faq(self, ctx: SlashContext):

        embed = discord.Embed(title='Fequently Asked Questions', description=config.FAQ, colour=config.BLUE)
        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)


    # /me Command
    @commands.cooldown(1, 86400, commands.BucketType.member)
    @cog_ext.cog_slash(
        name = 'me',
        description = config.ME_BRIEF,
        guild_ids = [config.GUILD]
    )
    async def me(self, ctx: SlashContext):
        member = ctx.author

        embed = discord.Embed(title=f'Information on {member.name}#{member.discriminator}', colour = member.colour)
        embed.set_thumbnail(url = member.avatar_url)

        # Account age
        creation_date = member.created_at.strftime('%b-%d-%Y')
        
        #Last join
        joined = ctx.author.joined_at.strftime('%b-%d-%Y')

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