# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import asyncio
import discord
from discord.ext import commands
import config


class Users(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Answer to command !help
    @commands.command(name="help")
    # @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def help(self, ctx, command: str = None):

        role = ctx.guild.get_role(config.MOD_ID)
        # if message author is a moderator
        if role in ctx.message.author.roles:
            if command is None:
                answer = config.HELP_INFO_MOD

                embed = discord.Embed(
                    title="Commands information", description=answer, colour=config.BLUE
                )
                embed.set_author(
                    icon_url=self.bot.user.avatar.url, name=self.bot.user.name
                )
                embed.set_footer(text=config.FOOTER)
                await ctx.reply(embed=embed)
            else:

                def f(x):
                    return {
                        "mute": config.HELP_MUTE,
                        "unmute": config.HELP_UNMUTE,
                        "warn": config.HELP_WARN,
                        "unwarn": config.HELP_UNWARN,
                        "cwarn": config.HELP_CLEAR,
                        "delete": config.HELP_DELETE,
                        "status": config.HELP_STATUS,
                        "kick": config.HELP_KICK,
                        "ban": config.HELP_BAN,
                        "tempban": config.HELP_TEMPBAN,
                        "timers": config.HELP_TIMERS,
                        "jac": config.HELP_JAC,
                        #"giveaway": config.HELP_GA,
                        "users": config.HELP_INFO_USER,
                        "poll": config.HELP_POLL,
                    }[x]

                answer = f(command)

                embed = discord.Embed(
                    title="Command information", description=answer, colour=config.BLUE
                )
                embed.set_author(
                    icon_url=self.bot.user.avatar.url, name=self.bot.user.name
                )
                embed.set_footer(text=config.FOOTER)
                await ctx.reply(embed=embed)

        # if message author is not a moderator
        else:

            if ctx.message.channel.id != config.UCMD_CHAN:
                await ctx.reply(f"Use <#{config.UCMD_CHAN}> for bot commands.")
            else:
                answer = config.HELP_INFO_USER

                embed = discord.Embed(
                    title="Commands information", description=answer, colour=config.BLUE
                )
                embed.set_author(
                    icon_url=self.bot.user.avatar.url, name=self.bot.user.name
                )
                embed.set_footer(text=config.FOOTER)
                await ctx.send(embed=embed)

    # Answer to command !roles
    @commands.command(name="roles", brief=config.ROLES_BRIEF)
    # 1 usage every 30 seconds per channel
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def roles(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if (
            ctx.message.channel.id != config.UCMD_CHAN
        ) and role not in ctx.message.author.roles:
            await ctx.reply(f"Use <#{config.UCMD_CHAN}> for bot commands.")
        else:
            answer = config.ROLES_INFO

            embed = discord.Embed(
                title="Roles information", description=answer, colour=config.BLUE
            )
            embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.reply(content=None, embed=embed)

    # Answer to command !twitch
    @commands.command(name="twitch", brief=config.TWITCH_BRIEF)
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def twitch(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if (
            ctx.message.channel.id != config.UCMD_CHAN
        ) and role not in ctx.message.author.roles:
            await ctx.reply(f"Use <#{config.UCMD_CHAN}> for bot commands.")
        else:
            answer = config.TWITCH_INFO

            embed = discord.Embed(
                title="Twitch information",
                url=config.TWTICH_URL,
                description=answer,
                colour=config.PURPLE,
            )
            embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.reply(content=None, embed=embed)

    # Answer to command !faq
    @commands.command(name="faq", brief=config.FAQ_BRIEF)
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def faq(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if (
            ctx.message.channel.id != config.UCMD_CHAN
        ) and role not in ctx.message.author.roles:
            await ctx.reply(f"Use <#{config.UCMD_CHAN}> for bot commands.")
        else:
            answer = config.FAQ

            embed = discord.Embed(
                title="Fequently Asked Questions",
                description=answer,
                colour=config.BLUE,
            )
            embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.reply(content=None, embed=embed)

    # Answer to command !merch
    @commands.command(name="merch")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def merch(self, ctx):
        """Return the URL with Operator Drewski's merch website."""
        await ctx.reply(
            "You can find Operator Drewski's merch at this link:\n https://bunkerbranding.com/pages/operator-drewski"
        )

    # Anser to command !me
    @commands.command(name="me", brief=config.ME_BRIEF)
    # @commands.cooldown(1, 86400, commands.BucketType.member)
    @commands.guild_only()
    async def me(self, ctx):
        member = ctx.message.author

        # Gooz keeps using this command every day
        if member.id == config.GOOZ_ID:
            await ctx.reply("Stop using this command, gooz")
            muted = ctx.guild.get_role(config.MUTE_ID)
            await member.add_roles(muted)
            await asyncio.sleep(30)
            await member.remove_roles(muted)
            return

        embed = discord.Embed(
            title=f"Information on {member.name}#{member.discriminator}",
            colour=member.colour,
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar)

        # Account age
        creation_date = member.created_at.strftime("%b-%d-%Y")

        # Last join
        joined = ctx.message.author.joined_at.strftime("%b-%d-%Y")

        # Is nitro boosting
        if member.premium_since is not None:
            boosting = member.premium_since.strftime("%b-%d-%Y")
        else:
            boosting = "Not boosting"

        # Roles
        roles = member.roles
        role_mentions = [role.mention for role in roles]
        role_list = ", ".join(role_mentions)

        embed.add_field(name="Creation date", value=creation_date, inline=True)
        embed.add_field(name="Last join", value=joined, inline=True)
        embed.add_field(name="Boosting since", value=boosting, inline=False)
        embed.add_field(name="Roles", value=role_list, inline=False)

        embed.set_author(icon_url=self.bot.user.avatar.url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)

        await ctx.reply(embed=embed)

def setup(bot):
    bot.add_cog(Users(bot))
