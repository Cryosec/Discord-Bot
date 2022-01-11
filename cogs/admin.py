# pylint: disable=F0401, W0703
from discord.ext import commands
from discord.commands import permissions
import config, support
import importlib


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="load", hidden=True)
    @permissions.is_owner()
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
    @permissions.is_owner()
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
    @permissions.is_owner()
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
    @permissions.is_owner()
    async def reconf(self, ctx):
        try:
            importlib.reload(config)
            importlib.reload(support)
        except Exception as e:
            await ctx.reply("Error reloading config.")
            await ctx.send("{}: {}".format(type(e).__name__, e))
        else:
            await ctx.reply("Configuration file reloaded.")


def setup(bot):
    bot.add_cog(Admin(bot))
