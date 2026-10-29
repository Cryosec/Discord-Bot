# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import discord
from discord.ext import commands
import config
from datetime import timedelta
import random
import asyncio


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if command from Moderator
    async def cog_check(self, ctx):
        mod = ctx.guild.get_role(config.MOD_ID)
        admin = ctx.guild.get_role(config.ADMIN_ID)
        if mod in ctx.author.roles:
            return True
        elif admin in ctx.author.roles:
            return True
        else:
            return False

    @commands.command(name="ping")
    async def ping(self, ctx):
        await ctx.reply("Pong! {0} ms".format(round(self.bot.latency * 1000, 1)))

    # Lundy insults, this one's an inside joke
    @commands.command(name="lundy")
    @commands.guild_only()
    async def lundy(self, ctx):

        # Remove command call
        await ctx.message.delete(reason = "!lundy command invocation")

        # Get lundy object, and ping with insult
        lundy = await ctx.guild.fetch_member(config.LUNDY_ID)
        insults = config.INSULTS
        insult = random.choice(insults)
        answer = lundy.mention + " " + insult
        await ctx.channel.send(answer)

    # Another inside joke with a different user
    @commands.command(name="toxy")
    @commands.guild_only()
    async def toxy(self, ctx):

        await ctx.message.channel.purge(limit=1)
        await ctx.send("Shut the fuck up, toxy")
        toxy = await ctx.guild.fetch_member(config.TOXY_ID)
        muted = ctx.guild.get_role(config.MUTE_ID)

        await toxy.add_roles(muted)
        await asyncio.sleep(30)
        await toxy.remove_roles(muted)

    # Floppa Friday!
    @commands.command(name="floppa")
    @commands.guild_only()
    async def floppa(self, ctx, member: discord.Member):
        # await ctx.message.channel.purge(limit=1)
        await ctx.send("I am the one who flops")

        # Timeout the member for 30 seconds
        await member.timeout_for(timedelta(seconds=30), reason="floppa'd")

    # Blame avyy
    @commands.command(name="avyy")
    @commands.guild_only()
    async def avyy(self, ctx):

        await ctx.message.delete(reason = "!avyy command invocation")

        avyy = await self.bot.get_or_fetch_user(config.AVYY_ID)

        embed = discord.Embed()
        embed.set_image(url="https://i.imgur.com/Zb6iKwA.png")

        await ctx.send(content=avyy.mention, embed=embed)

    # Lotto
    @commands.command(name="lotto")
    @commands.guild_only()
    async def lotto(self, ctx):

        await ctx.message.delete(reason = "!lotto command invocation")

        lotto = await self.bot.get_or_fetch_user(config.LOTTO_ID)

        embed = discord.Embed()
        embed.set_image(url="https://c.tenor.com/GehTGeLa3yEAAAAC/cap-cap-check.gif")

        await ctx.send(content=lotto.mention, embed=embed)

    # Lotto
    @commands.command(name="tim")
    @commands.guild_only()
    async def tim(self, ctx):

        await ctx.message.delete(reason = "!tim command invocation")

        tim = await self.bot.get_or_fetch_user(config.TIM_ID)

        embed = discord.Embed()
        embed.set_image(url="https://m.media-amazon.com/images/M/MV5BMmIyNDQwODMtMTI4Yy00ZTY5LWEyZmYtNTQ0NGUzMjdhMGJiXkEyXkFqcGdeQXVyMTE0MzYxMjM5._V1_.jpg")

        await ctx.send(content=tim.mention, embed=embed)

    # Error handling
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                "Missing arguments, type `!help <command>` for info on your command."
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.reply("I could not find that user. Try again.")


def setup(bot):
    bot.add_cog(Moderation(bot))
