# pylint: disable=F0401, W0702, W0703, W0105, W0613, W1201
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import pytz
from datetime import datetime, timedelta
import re, asyncio
import logging
from logging.handlers import RotatingFileHandler
import discord
from discord.commands import slash_command, Option
from discord.ext import commands
import config
import cogs.database as db


#Setup module logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")

file_handler = RotatingFileHandler(
    filename=f"logs/{__name__}.log",
    mode="a",
    maxBytes=20000,
    backupCount=5,
    encoding="utf-8")
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

log.addHandler(file_handler)
log.addHandler(console_handler)


class ModerationSlash(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.database = db.Database(self.bot)

    # /mute Command
    @slash_command(guild_ids=[config.GUILD], name="mute", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def mute(
        self,
        ctx,
        member: Option(discord.Member, "Member to mute", required=True, default=None),
        duration: Option(str, "Duration of mute", required=False, default="a"),
    ):
        """Mute a selected member for an amount of time."""
        channel = ctx.guild.get_channel(config.LOG_CHAN)
        role = ctx.guild.get_role(config.MUTE_ID)

        if "a" in duration:

            await member.add_roles(role)
            log.info("Muting %s indefinitely", member)
            await ctx.respond(
                embed=discord.Embed(
                    title=f"User {member} has been muted indefinitely",
                    colour=config.YELLOW,
                )
            )

            embed = discord.Embed(
               title="Muting issued!",
               description="No duration specified. Muting indefinitely.",
               colour=config.YELLOW,
            )
            embed.add_field(name="User:", value=f"{member.mention}")
            embed.add_field(name="Issued by:", value=f"{ctx.author.mention}")
            embed.add_field(name="End:", value="Indefinitely")
            embed.set_footer(text=config.FOOTER)

            # Log timeout in log channel
            await channel.send(content=None, embed=embed)

        else:
            tz_TX = pytz.timezone("US/Central")
            now = datetime.now(tz_TX)
            end = now
            delta = timedelta(0)
            mods = re.findall(r"([0-9]+?[wdhms])+?", duration)

            if not mods:
                await ctx.respond("**ERROR**: `duration` format is incorrect.")
                return

            dur = ""
            for x in mods:
                if "w" in x:
                    y = x[0:-1]
                    end = end + timedelta(weeks=int(y))
                    delta = delta + timedelta(weeks=int(y))
                    dur = dur + y + " weeks "
                elif "d" in x:
                    y = x[0:-1]
                    end = end + timedelta(days=int(y))
                    delta = delta + timedelta(days=int(y))
                    dur = dur + y + " days "
                elif "h" in x:
                    y = x[0:-1]
                    end = end + timedelta(hours=int(y))
                    delta = delta + timedelta(hours=int(y))
                    dur = dur + y + " hours "
                elif "m" in x:
                    y = x[0:-1]
                    end = end + timedelta(minutes=int(y))
                    delta = delta + timedelta(minutes=int(y))
                    dur = dur + y + " minutes "
                elif "s" in x:
                    y = x[0:-1]
                    end = end + timedelta(seconds=int(y))
                    delta = delta + timedelta(seconds=int(y))
                    dur = dur + y + " seconds "

            end_string = end.strftime("%b-%d-%Y %H:%M:%S")

            self.database.addTimerMute(str(member.id), end_string)

            await member.add_roles(role)

            log.info("Timer started - User %s has been muted for %s" % (member, dur))

            await ctx.respond(
                embed=discord.Embed(
                    title=f"User {member} has been muted for {dur}",
                    colour=config.YELLOW,
                )
            )

            dur = dur[0:-1]
            embed = discord.Embed(
                title="Muting issued!",
                description=f"A duration of `{dur}` was specified.",
                colour=config.YELLOW,
            )
            embed.add_field(name="User:", value=f"{member.mention}")
            embed.add_field(name="Issued by:", value=f"{ctx.author.mention}")
            embed.add_field(name="End:", value=end_string)
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)

            await asyncio.sleep(int(delta.total_seconds()))
            await member.remove_roles(role)
            log.info("Timer ended - User %s has been unmuted", member)

            self.database.delTimer(str(member.id))

            embed = discord.Embed(
                title="Timed mute complete",
                description=f"User {member.mention} has been unmuted automatically.",
                colour=config.YELLOW,
            )
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)

    # /unmute Command
    @slash_command(guild_ids=[config.GUILD], name="unmute", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def unmute(
        self,
        ctx,
        member: Option(discord.Member, "Member to unmute", required=True, default=None),
    ):
        """Unmute selected member."""
        if member is not None:
            role = ctx.guild.get_role(config.MUTE_ID)
            await member.remove_roles(role)
            log.info("User %s was unmuted", member)

            self.database.delTimer(str(member.id))

            await ctx.respond(
                embed=discord.Embed(
                    title=f"User {member} was unmuted.", colour=config.GREEN
                )
            )

    # /ban Command
    @slash_command(guild_ids=[config.GUILD], name="ban", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def ban_user(
        self,
        ctx,
        member: Option(discord.Member, "Member to ban", required=True),
        reason: Option(str, "Reason for ban", required=False, default=None),
    ):
        """Ban selected member from the server and delete all messages."""
        if member is None:
            await ctx.respond(
                "No member found with ID, might not be in the server anymore."
            )
            return

        role = ctx.guild.get_role(config.MOD_ID)

        if role in member.roles:
            await ctx.respond("You cannot ban a moderator through me.")
        else:

            tz_TX = pytz.timezone("US/Central")
            now = datetime.now(tz_TX)
            dt = now.strftime("%b-%d-%Y %H:%M:%S")

            # Create feedback embed
            embed = discord.Embed(
                title="User ban issued!",
                description=f"Reason: {reason}",
                colour=config.RED,
            )
            embed.add_field(name="Issuer:", value=ctx.author.mention)
            embed.add_field(name="Banned:", value=member.mention)
            embed.add_field(name="When:", value=dt)
            embed.set_footer(text=config.FOOTER)

            # Record ban
            # already done in events.py inside on_member_ban

            await ctx.guild.ban(member, reason=reason)
            log.info("User %s was banned", member)
            await ctx.respond(
                embed=discord.Embed(
                    title=f"User {member} was banned from the Server.",
                    colour=config.RED,
                )
            )
            channel = ctx.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)

    # /tempban Command
    @slash_command(guild_ids=[config.GUILD], name="tempban", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def tempban_user(
        self,
        ctx,
        member: Option(discord.User, "Member to ban", required=True),
        duration: Option(str, "Duration of ban", required=True, default=None),
        reason=Option(str, "Reason for ban", required=False, default="Unspecified"),
    ):
        """Temporarily ban selected member from the server without deleting messages."""
        role = ctx.guild.get_role(config.MOD_ID)
        channel = ctx.guild.get_channel(config.LOG_CHAN)
        mem = ctx.guild.get_member(member.id)

        if role in mem.roles:
            await ctx.respond("You cannot ban a moderator through me.", ephemeral = True)
        else:
            if duration is None:
                await ctx.respond("**ERROR**: Command format is incorrect.", ephemeral = True)
                return
            else:
                tz_TX = pytz.timezone("US/Central")
                now = datetime.now(tz_TX)
                end = now
                delta = timedelta(0)
                mods = re.findall(r"([0-9]+?[wdhms])+?", duration)

                if not mods:
                    await ctx.send("**ERROR**: `duration` format is incorrect.")
                    return

                dur = ""
                for x in mods:
                    if "w" in x:
                        y = x[0:-1]
                        end = end + timedelta(weeks=int(y))
                        delta = delta + timedelta(weeks=int(y))
                        dur = dur + y + " weeks "
                    elif "d" in x:
                        y = x[0:-1]
                        end = end + timedelta(days=int(y))
                        delta = delta + timedelta(days=int(y))
                        dur = dur + y + " days "
                    elif "h" in x:
                        y = x[0:-1]
                        end = end + timedelta(hours=int(y))
                        delta = delta + timedelta(hours=int(y))
                        dur = dur + y + " hours "
                    elif "m" in x:
                        y = x[0:-1]
                        end = end + timedelta(minutes=int(y))
                        delta = delta + timedelta(minutes=int(y))
                        dur = dur + y + " minutes "
                    elif "s" in x:
                        y = x[0:-1]
                        end = end + timedelta(seconds=int(y))
                        delta = delta + timedelta(seconds=int(y))
                        dur = dur + y + " seconds "

                end_string = end.strftime("%b-%d-%Y %H:%M:%S")

                self.database.addTimerBan(str(member.id), end_string)

                dur = dur[0:-1]
                embed = discord.Embed(
                    title="Temp Ban issued!",
                    description=f"A duration of `{dur}` was specified.",
                    colour=config.YELLOW,
                )
                embed.add_field(name="User:", value=f"{member.mention}")
                embed.add_field(name="Issued by:", value=f"{ctx.author.mention}")
                embed.add_field(name="End:", value=end_string)
                embed.set_footer(text=config.FOOTER)

                await channel.send(content=None, embed=embed)

                await member.send(
                    f"You have ben temporarily banned from Drewski's Operators server. The ban lasts {dur}."
                )

                await ctx.guild.ban(member, reason=reason, delete_message_days=0)

                log.info(
                    "Timer started - User %s has been temporarily banned for %s" % (member, dur)
                )

                await ctx.respond(
                    embed=discord.Embed(
                        title=f"User {member} has ben temporarily banned for {dur}",
                        colour=config.RED,
                    )
                )

                await asyncio.sleep(int(delta.total_seconds()))

                embed = discord.Embed(
                    title="Timed ban complete",
                    description=f"User {member.mention} has been unbanned automatically.",
                    colour=config.YELLOW,
                )
                embed.set_footer(text=config.FOOTER)

                await channel.send(content=None, embed=embed)
                await ctx.guild.unban(member, reason="Temp ban concluded")

                log.info("Timer ended - User %s has been unbanned.", member)

                self.database.delTimer(str(member.id))


    # /kick Command
    @slash_command(guild_ids=[config.GUILD], name="kick", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def kick_user(
        self,
        ctx,
        member: Option(discord.Member, "Member to kick", required=True),
        reason=Option(str, "Reason for kick", required=False, default="Unspecified"),
    ):
        """Kick selected member from the server."""
        role = ctx.guild.get_role(config.MOD_ID)
        if role in member.roles:
            await ctx.send("You cannot kick a moderator through me.")
        else:

            # Record kick
            # done in events.py at on_member_remove

            await ctx.guild.kick(member, reason=reason)

            log.info("User %s has been kicked.", member)

            await ctx.respond(
                embed=discord.Embed(
                    title=f"User {member} was kicked from the server", colour=config.RED
                )
            )

            # channel = ctx.guild.get_channel(config.LOG_CHAN)
            # await channel.send(content=None, embed=embed)

    # /status Command
    @slash_command(guild_ids=[config.GUILD], name="status", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def status(
        self, ctx, user: Option(discord.User, "User to lookup", required=True)
    ):
        """Show the status summary of the selected user."""
        if user is not None:

            user = await self.bot.fetch_user(user.id)
            member = ctx.guild.get_member(user.id)

            if member is not None:

                # Is nitro boosting
                if member.premium_since is not None:
                    boosting = member.premium_since.strftime("%b-%d-%Y")
                else:
                    boosting = "Not boosting"

                # Roles
                roles = member.roles
                role_mentions = [role.mention for role in roles]
                role_list = ", ".join(role_mentions)

                warn_reasons = self.database.getWarnReasons(str(member.id))
                warn_user = self.database.getWarnUserByID(str(member.id))

                if len(warn_user) > 0:
                    embed = discord.Embed(
                        title=f"Status of user {member}",
                        description="\n".join(
                            "{}: {}".format(*k)
                            for k in enumerate(warn_reasons)
                        ),
                        colour=config.GREEN,
                    )
                    embed.add_field(name="Warnings:", value=warn_user['warnings'])
                    embed.add_field(name="Kicks:", value=warn_user['kicks'])
                    embed.add_field(name="Bans:", value=warn_user['bans'])
                    embed.add_field(
                        name="Joined:",
                        value=member.joined_at.strftime("%b-%d-%Y %H:%M:%S"),
                    )
                    embed.add_field(
                        name="Created:",
                        value=member.created_at.strftime("%b-%d-%Y %H:%M:%S"),
                    )
                    embed.add_field(name="Boosting since", value=boosting, inline=False)
                    embed.add_field(name="Roles", value=role_list, inline=False)
                    embed.set_footer(text=config.FOOTER)
                else:
                    embed = discord.Embed(
                        title=f"Status of user {member}",
                        description="No warnings issued.",
                        colour=config.GREEN,
                    )
                    embed.add_field(name="Warnings:", value="0")
                    embed.add_field(name="Kicks:", value="0")
                    embed.add_field(name="Bans:", value="0")
                    embed.add_field(
                        name="Joined:",
                        value=member.joined_at.strftime("%b-%d-%Y %H:%M:%S"),
                    )
                    embed.add_field(
                        name="Created:",
                        value=member.created_at.strftime("%b-%d-%Y %H:%M:%S"),
                    )
                    embed.add_field(name="Boosting since", value=boosting, inline=False)
                    embed.add_field(name="Roles", value=role_list, inline=False)

                    embed.set_footer(text=config.FOOTER)

                await ctx.respond(content=None, embed=embed)

            else:
                warn_reasons = self.database.getWarnReasons(str(user.id))
                warn_user = self.database.getWarnUserByID(str(user.id))
                if len(warn_user) > 0:
                    embed = discord.Embed(
                        title=f"Status of user {user}",
                        description="**User is no longer in the server**\n"
                        + "\n".join(
                            "{}: {}".format(*k)
                            for k in enumerate(warn_reasons)
                        ),
                        colour=config.GREEN,
                    )
                    embed.add_field(name="Warnings:", value=warn_user['warnings'])
                    embed.add_field(name="Kicks:", value=warn_user['kicks'])
                    embed.add_field(name="Bans:", value=warn_user['bans'])
                    embed.add_field(name="Joined:", value="N/A")
                    embed.set_footer(text=config.FOOTER)

                    await ctx.respond(content=None, embed=embed)
                else:
                    embed = discord.Embed(
                        title=f"Status of user {user}",
                        description="**User is not part of the server.**",
                        colour=config.GREEN,
                    )
                    embed.add_field(name="Warnings:", value="0")
                    embed.add_field(name="Kicks:", value="0")
                    embed.add_field(name="Bans:", value="0")
                    embed.add_field(name="Joined:", value="N/A")
                    embed.set_footer(text=config.FOOTER)

                    await ctx.respond(content=None, embed=embed)

        else:
            await ctx.respond("Something went wrong")

    # /warn Command
    @slash_command(guild_ids=[config.GUILD], name="warn", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def warn(
        self,
        ctx,
        member: Option(discord.Member, "Member to warn", required=True),
        reason=Option(str, "Reason of warn", required=False, default="Unspecified"),
    ):
        """Warn the selected user."""
        print(f"INFO: Warning {member}...")
        try:
            self.database.addWarning(str(member.id), str(member.name), reason)
            warn_users = self.database.getWarnUserByID(str(member.id))
            channel = ctx.guild.get_channel(config.LOG_CHAN)
            embed = discord.Embed(
                title="Warning issued!",
                description=f"Reason: {reason}",
                colour=config.YELLOW,
            )
            embed.add_field(name="User:", value=f"{member}")
            embed.add_field(name="Issued by:", value=f"{ctx.author}")
            embed.add_field(name="Total Warnings:", value=warn_users['warnings'])
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)
            await ctx.respond(embed=discord.Embed(title=f"{member} has been warned"))
            print("INFO: Done.")
        except:
            print("WARNING: oof, warn command broke")

    # /unwarn command
    @slash_command(guild_ids=[config.GUILD], name="unwarn", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def unwarn(
        self,
        ctx,
        member: Option(
            discord.Member, "Member for which to remove the last warning", required=True
        ),
    ):
        """Remove the last warn from a user's warnings list."""
        if member is not None:

            self.database.delWarning(str(member.id), reason="")

            # Reply to command
            await ctx.respond(
                embed=discord.Embed(title=f"{member} last warning has been removed, if present."),
                ephemeral=True
            )

            # Log the event in the log channel
            log_channel = ctx.guild.get_channel(config.LOG_CHAN)
            await log_channel.send(
                embed=discord.Embed(
                    title=f"Last warning removed from user {member}",
                    colour=config.GREEN,
                )
            )

            # This goes in the container logs
            log.info("Last warning for user %s removed.", member)
        else:
            await ctx.respond(
                embed=discord.Embed(
                    title="User is not part of the server", colour=config.YELLOW
                )
            )
    """
    # /cwarn Command
    @slash_command(guild_ids=[config.GUILD], name="cwarn", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def cwarn(
        self,
        ctx,
        member: Option(
            discord.Member, "Member for which to clear all warnings", required=True
        ),
    ):
        # Remove all warnings from a user's warning list.
        if member is not None:
            self.database.delAllWarnings()
            await ctx.respond(
                embed=discord.Embed(
                    title=f"Warnings cleared for user {member}", colour=config.GREEN
                )
            )
            print(f"Warnings for user {member} cleared.")
        else:
            await ctx.respond(
                emved=discord.Embed(
                    title="User is not part of the server", colour=config.YELLOW
                )
            )
    """
    # /jac Command
    @slash_command(guild_ids=[config.GUILD], name="jac", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def jac_details(
        self, ctx, member: Option(discord.Member, "Member for which to show JAC status")
    ):
        """Get the details of the JAC entry for a selected user."""
        jac = self.database.getJacByID(str(member.id))

        if len(jac) > 0:
            tz_TX = pytz.timezone("US/Central")
            now = datetime.now(tz_TX)
            dt = datetime.strptime(jac[0]['date'], "%b-%d-%Y %H:%M:%S")
            dt = dt.replace(tzinfo=tz_TX)

            end = dt + timedelta(days=14)

            delta = end - now

            embed = discord.Embed(
                title=f"User {member}",
                description=jac[0]['link'],
                colour=config.GREEN,
            )
            embed.add_field(name="Timestamp", value=jac[0]['date'])
            embed.add_field(name="Time left", value=str(delta), inline=False)
            embed.set_footer(text=config.FOOTER)

            await ctx.respond(content=None, embed=embed)
        else:
            await ctx.respond("User is not in the database")

    # /unjac command
    @slash_command(guild_ids=[config.GUILD], name="unjac", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def unjac(
        self,
        ctx,
        member: Option(discord.Member, "Member for which to remove the last JAC entry"),
    ):
        """Remove the JAC entry for the selected user."""
        if member is not None:
            self.database.delJac(str(member.id))
            await ctx.respond(
                embed=discord.Embed(
                    title=f"JAC entry removed for user {member}", colour=config.GREEN
                )
            )
        else:
            await ctx.respond(
                embed=discord.Embed(
                    title="User is not part of the server", colour=config.YELLOW
                )
            )

    # /timers Command
    @slash_command(guild_ids=[config.GUILD], name="timers", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def show_timers(self, ctx, group: str = None):
        """Show a list of currently active timers."""
        if group is None:
            t = self.database.getTimers()

            timers = []
            for elem in t:

                usr = await self.bot.fetch_user(int(elem[0]))
                ban = str(t[elem][1])
                mute = str(t[elem][2])
                endBan = str(t[elem][3])
                endMute = str(t[elem][4])


                timers.append(
                    f"{usr.mention}"
                    + "```\nBan: "
                    + ban
                    + "\nMute: "
                    + mute
                    + "\nendBan: "
                    + endBan
                    + "\nendMute: "
                    + endMute
                    + "```"
                )

            if not timers:
                await ctx.respond(
                    embed=discord.Embed(
                        title="There are no timers left.", colour=config.YELLOW
                    )
                )
            else:

                embed = discord.Embed(
                    title="Timers",
                    description="\n".join(
                        "{}: {}".format(*k) for k in enumerate(timers)
                    ),
                    colour=config.GREEN,
                )
                embed.set_footer(text=config.FOOTER)

                await ctx.respond(embed=embed)

    # /delete Command
    @slash_command(guild_ids=[config.GUILD], name="delete", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def delete_messages(
        self, ctx, messages: Option(int, "Number of messages to delete", required=True)
    ):
        """Deleted the specified amount of messages from the current channel."""
        await ctx.respond("Deleting", ephemeral=True)
        await ctx.channel.purge(limit=messages)

        channel = ctx.guild.get_channel(config.LOG_CHAN)

        embed = discord.Embed(
            title="Bulk Message Deletion",
            description=f"{messages} messages were deleted \
                                from {ctx.channel.name} by {ctx.author.name}#{ctx.author.discriminator}",
            colour=config.ORANGE,
        )
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)

    # /slow Command
    @slash_command(guild_ids=[config.GUILD], name="slow", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def slowmode(
        self,
        ctx,
        channel: Option(
            discord.TextChannel, "Channel in which to set the slowmode", required=True
        ),
        seconds: Option(
            int,
            "Number of seconds for the slowmode. 0 to remove",
            required=True,
            default=0,
        ),
    ):
        """Specify a slowmode for the selected channel."""
        try:
            await channel.edit(slowmode_delay=seconds)

            if seconds == 0:
                await ctx.respond(
                    embed=discord.Embed(
                        title=f"Slowmode disabled for {channel}", colour=config.GREEN
                    )
                )
            else:
                await ctx.respond(
                    embed=discord.Embed(
                        title=f"Slowmode for {channel} set to {seconds} seconds",
                        colour=config.YELLOW,
                    )
                )
        except:
            print(f"Error setting slowmode for channel {channel}")

    # /timeout command
    @slash_command(guild_ids=[config.GUILD], name="timeout", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def timeout(
        self,
        ctx,
        member: Option(discord.Member, "Member to timeout", required=True),
        minutes: Option(
            int, "Duration in minutes for the timeout", required=True, default=10
        ),
        reason: Option(str, "Reason for the timeout", required=False, default=None),
    ):
        """Set a timeout for a given user."""
        duration = timedelta(minutes=minutes)
        await member.timeout_for(duration, reason=reason)
        await ctx.respond(f"Member {member} timed out for {minutes} minutes.")

    # /kc
    @slash_command(guild_ids=[config.GUILD], name="kc", default_permission=False)
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def killcount(
        self,
        ctx,
        member: Option(discord.Member, "Counter for Member, defaults to all", required=False)
    ):
        """Get total kill count or specific count for a member"""
        if not member:
            counter = self.database.getKillCount("*")
            await ctx.respond(f"Total kill counter is {counter}.")
        else:
            counter = self.database.getKillCount(str(member.id))
            await ctx.respond(f"Kill count for member {member} is {counter}.")



def setup(bot):
    bot.add_cog(ModerationSlash(bot))
