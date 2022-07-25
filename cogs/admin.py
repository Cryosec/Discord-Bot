# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from discord.ext import commands
import config, support
import importlib


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="load", hidden=True)
    @commands.is_owner()
    async def load(self, ctx, *, module: str):
        """Loads a module."""
        try:
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.reply("Error loading module.")
            await ctx.send("{}: {}".format(type(e).__name__, e))
        else:
            await ctx.reply(f"Loaded module {module}.")

    @commands.command(name="unload", hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, *, module: str):
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.reply("Error loading module.")
            await ctx.send("{}: {}".format(type(e).__name__, e))
        else:
            await ctx.reply(f"Unloaded module {module}.")

    @commands.command(name="reload", hidden=True)
    @commands.is_owner()
    async def _reload(self, ctx, *, module: str):
        """Reloads a module."""
        try:
            self.bot.reload_extension(module)
        except Exception as e:
            await ctx.reply("Error loading module.")
            await ctx.send("{}: {}".format(type(e).__name__, e))
        else:
            await ctx.reply(f"Reloaded module {module}.")

    # Reload config.py
    @commands.command(name="reconf", hidden=True)
    @commands.is_owner()
    async def reconf(self, ctx):
        try:
            importlib.reload(config)
            importlib.reload(support)
        except Exception as e:
            await ctx.reply("Error reloading config.")
            await ctx.send("{}: {}".format(type(e).__name__, e))
        else:
            await ctx.reply("Configuration file reloaded.")

    # cover my ass when I fuck up with timeouts
    @commands.command(name="rt", hidden=True)
    @commands.is_owner()
    async def rt(self, ctx, user):
        guild = await self.bot.fetch_guild(config.GUILD)
        member = await guild.fetch_member(user)

        await member.remove_timeout()


def setup(bot):
    bot.add_cog(Admin(bot))
