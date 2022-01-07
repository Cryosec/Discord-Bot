# pylint: disable=F0401, W0702, W0703, W0105, W0613
import discord
from discord.commands import slash_command, Option, permissions
from discord.ext import commands
import random, asyncio
import config

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
    @slash_command(guild_ids=[config.GUILD], name='giveaway',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def giveaway(
        self, ctx,
        channel: Option(discord.TextChannel, "Select a channel for the giveaway.", required = True),
        duration: Option(int, "Select a duration in minutes for the giveaway", required = True),
        prize: Option(str, "Describe the prize. Don't put the actual prize here", required = True)
    ):
        """Start a giveaway event in a selected channel."""
        embed = discord.Embed(
            title = '🎉 New Giveaway! 🎉',
            color = config.GREEN)
        embed.add_field(
            name = 'Prize:',
            value = "{}".format(prize),
            inline = False)
        embed.add_field(
            name = 'Duration:',
            value = "{}m".format(duration),
            inline = False)
        embed.set_footer(text=config.FOOTER)

        # Ping everyone in channel
        #msg = await channel.send(content = ctx.message.guild.default_role, embed = embed)
        msg = await channel.send(embed = embed)
        await msg.add_reaction("🎉")

        # Confirm giveaway creation
        await ctx.respond(content = f"Giveaway created in channel {channel}. Here the preview:", embed = embed)

        # wait duration minutes
        await asyncio.sleep(60 * duration)
        #await asyncio.sleep(duration)

        # Refresh msg reference
        msg = await msg.channel.fetch_message(msg.id)
        winner = None

        for reaction in msg.reactions:
            if reaction.emoji == "🎉":
                users = await reaction.users().flatten()
                try:
                    users.remove(self.bot)
                except:
                    pass
                winner = random.choice(users)

        if winner is not None:
            end_embed = discord.Embed(
                title = 'Giveaway Ended!',
                description = 'Prize: {}\nWinner: {}'.format(prize, winner))
            end_embed.set_footer(text=config.FOOTER)

            await msg.edit(embed=end_embed)

            notify_embed = discord.Embed(
                title = 'Giveaway Winner Selected!',
                color = config.GREEN)
            notify_embed.add_field(
                name = 'Prize: ',
                value = "{}".format(prize),
                inline = False)
            notify_embed.add_field(
                name = 'Winner: ',
                value = "{}".format(winner.mention),
                inline = False)
            notify_embed.set_footer(text=config.FOOTER)

            await channel.send(embed=notify_embed)

            # Log winner embed in mod_log
            mod_log = ctx.guild.get_channel(config.LOG_CHAN)
            await mod_log.send(embed=notify_embed)


def setup(bot):
    bot.add_cog(Giveaway(bot))

