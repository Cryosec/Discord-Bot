# pylint: disable=F0401
import asyncio
import random
import discord
from discord.ext import commands
from discord.commands import slash_command, Option
import config


class UsersSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /roles Command
    @slash_command(guild_ids=[config.GUILD], name="roles")
    async def roles(self, ctx):
        """Show a list of roles available in the server."""
        embed = discord.Embed(title='Roles information',
            description=config.ROLES_INFO, colour=config.BLUE)
        embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.respond(content=None, embed=embed)

    # /dayz Command
    @slash_command(guild_ids=[config.GUILD], name="dayz")
    async def dayz(self, ctx):
        """Show information on the Community DayZ Server."""
        embed = discord.Embed(
            title = 'Community DayZ Server Info:',
            description = config.DAYZ_DESC,
            colour = config.BLUE
        )
        embed.set_footer(text=config.FOOTER)

        await ctx.respond(embed=embed)

    # /twitch Command
    @slash_command(guild_ids=[config.GUILD], name="twitch")
    async def twitch(self, ctx):
        """Show information on the Twitch role in the server."""
        embed = discord.Embed(title='Twitch information',
            url=config.TWTICH_URL, description=config.TWITCH_INFO, colour=config.PURPLE)
        embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.respond(content=None, embed=embed)

    # /faq Command
    @slash_command(guild_ids=[config.GUILD], name="faq")
    async def faq(self, ctx):
        """Show frequently asked questions and their answers."""
        embed = discord.Embed(title='Fequently Asked Questions',
            description=config.FAQ, colour=config.BLUE)
        embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)
        await ctx.send(content=None, embed=embed)

    # /merch command
    @slash_command(guild_ids=[config.GUILD], name="merch")
    async def merch(self, ctx):
        """Return information on OperatorDrewski's merch."""
        await ctx.respond("You can find Operator Drewski's merch at this link:\n https://bunkerbranding.com/pages/operator-drewski")


    # /me Command
    @commands.cooldown(1, 86400, commands.BucketType.member)
    @slash_command(guild_ids=[config.GUILD], name="me")
    async def me(self, ctx):
        """Get information on the account of the user calling the command."""
        member = ctx.author

        # Gooz keeps using this command every day
        if member.id == config.GOOZ_ID:
            await ctx.respond('Stop using this command, gooz')
            muted = ctx.guild.get_role(config.MUTE_ID)
            await member.add_roles(muted)
            await asyncio.sleep(30)
            await member.remove_roles(muted)
            return

        embed = discord.Embed(title=f'Information on {member.name}#{member.discriminator}',
            colour = member.colour)
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

        await ctx.respond(embed=embed)

    @slash_command(guild_ids=[config.GUILD], name="rr")
    async def russian_roulette(self, ctx):
        """Russian Roulette for users. Lose, and you get banned."""
        role = ctx.guild.get_role(config.MOD_ID)

        if role in ctx.author.roles:
            await ctx.respond('Don\t be daft. Mods can\'t play.')
            return

        num = random.random(1, 6)
        if num == 1:
            await ctx.respond("*Bang*")
            await ctx.guild.ban(ctx.author, reason = "Russian roulette loser.")
        else:
            await ctx.respond("*Click*")

def setup(bot):
    bot.add_cog(UsersSlash(bot))
