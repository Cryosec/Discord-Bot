import discord
from discord.ext import commands
import config
import shelve, pytz
from datetime import datetime, timedelta
import random, typing, asyncio
import DiscordUtils

# BRIEF HELP
BRIEF_GA = 'Start a giveaway event in a specified channel'

# LONG HELP
HELP_GA = """**Usage::**
`!giveaway #channel <seconds> <prize description>`

The channel must be specified with the usual hashtag mention.
Giveaway duration is in seconds, and will be displayed in the bot message.
The prize **MUST** be a description, **NOT** the actual prize as it\'s visible to everyone.

NOTE: this command is available only to some specific mods/admins
"""

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if command from Moderator
    async def cog_check(self, ctx):
        if ctx.author.id in config.GA_ACCESS:
            return True
        else:
            return False

    # Giveaway setup command
    @commands.command(name='giveaway', brief=BRIEF_GA, help=HELP_GA)
    async def giveaway(self, ctx, channel: discord.TextChannel = None, duration: int = 10, prize: str = None):

        embed = discord.Embed(title = '🎉 New Giveaway! 🎉',
                            color = config.GREEN)
        embed.add_field(name = 'Prize:', value = "{}".format(prize), inline = False)
        embed.add_field(name = 'Duration:', value = "{}m".format(duration), inline = False)
        embed.set_footer(text=config.FOOTER)

        msg = await channel.send(embed = embed)
        await msg.add_reaction("🎉")

        # wait duration minutes
        #await asyncio.sleep(60 * duration)
        await asyncio.sleep(duration)

        # Refresh msg reference
        msg = await msg.channel.fetch_message(msg.id)
        winner = None

        for reaction in msg.reactions:
            if reaction.emoji == "🎉":
                users = await reaction.users().flatten()
                #users.remove(self.bot)
                winner = random.choice(users)

        if winner is not None:
            end_embed = discord.Embed(title = 'Giveaway Ended!',
                                    description = 'Prize: {}\nWinner: {}'.format(prize, winner))
            end_embed.set_footer(text=config.FOOTER)

            await msg.edit(embed=end_embed)

            notify_embed = discord.Embed(title = 'Giveaway Winner Selected!')
            notify_embed.add_field(name = 'Prize: ', value = "{}".format(prize), inline = False)
            notify_embed.add_field(name = 'Winner: ', value = "{}".format(winner.mention), inline = False)
            notify_embed.set_footer(text=config.FOOTER)

            await channel.send(embed=notify_embed)


def setup(bot):
    bot.add_cog(Giveaway(bot))

