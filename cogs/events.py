# pylint: disable=F0401, W0702, W0703, W0105, W0613
import re
from datetime import datetime, timezone
import pytz, shelve
import discord
from discord.ext import commands
import config
import support

tz_TX = pytz.timezone("US/Central")
TIME_FORMAT = "%b-%d-%Y %H:%M:%S"


def log(message):
    """Log to console a message with added timestamp."""
    now = datetime.now(timezone.utc)
    print(f"{now} UTC - " + message)


class Events(commands.Cog):
    def __init__(self, bot):
        """Initialize Events cog."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Manage logging of member ban.

        Keyword arguments:
        self    -- self reference of the bot
        guild   -- Discord Guild ID
        user    -- Banned user ID
        """

        now = datetime.now(tz_TX)
        dt = now.strftime(TIME_FORMAT)

        ban_entry = await guild.fetch_ban(user)

        s = shelve.open(config.WARNINGS)
        if str(user.id) in s:
            tmp = s[str(user.id)]
            tmp["bans"] = tmp.get("bans") + 1
            tmp["reasons"].append(ban_entry.reason)

            s[str(user.id)] = tmp
        else:
            if ban_entry.reason is None:
                s[str(user.id)] = {
                    "warnings": 0,
                    "kicks": 0,
                    "bans": 1,
                    "reasons": ["Ban: No reason specified"],
                    "tag": str(user),
                }
            else:
                s[str(user.id)] = {
                    "warnings": 0,
                    "kicks": 0,
                    "bans": 1,
                    "reasons": ["Ban:" + ban_entry.reason],
                    "tag": str(user),
                }

        s.close()

        author = None

        # Read audit logs
        # For whatever reason it does not assign the author of the ban and logs "None"
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                author = entry.user

        # Add 'unban' button under each ban embed
        unban_button = support.Unban()

        # Create embed to log the banning
        embed = discord.Embed(
            title="User Ban",
            description=f"User {user.name}#{user.discriminator} was banned from the Server by {author}.",
            colour=config.RED,
        )
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
        embed.add_field(name="Reason", value=ban_entry.reason, inline=False)
        embed.add_field(name="Timestamp", value=dt)

        channel = guild.get_channel(config.LOG_CHAN)

        await channel.send(embed=embed, view=unban_button)

        # Wait for button press on embed
        await unban_button.wait()

        # Respond to button press
        if unban_button.value:

            await guild.unban(user)

            # Remove ban from db
            s = shelve.open(config.WARNINGS)
            tmp = s[str(user.id)]
            tmp["bans"] = tmp.get("bans") - 1
            del tmp["reasons"][-1]
            s[str(user.id)] = tmp
            s.close()

            # Edit ban log embed to reflect
            new_embed = discord.Embed(
                title="User ban - canceled",
                description=f"User {user.name}#{user.discriminator} was unbanned by {unban_button.user}",
                colour=config.GREEN,
            )
            new_embed.set_author(
                name=self.bot.user.name, icon_url=self.bot.user.avatar.url
            )
            new_embed.add_field(name="Ban reason", value=ban_entry.reason, inline=False)
            new_embed.add_field(name="Timestamp", value=now.strftime(TIME_FORMAT))
            await unban_button.interaction.edit_original_message(
                embed=new_embed, view=None
            )

    # But there is no on_member_kick. oof
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Manage logging of member kick.

        Keyword arguments:
        self    -- self reference of the bot
        member  -- Kicked member ID
        """
        # tz_TX = pytz.timezone('US/Central')
        now = datetime.now(tz_TX)
        dt = now.strftime(TIME_FORMAT)

        guild = member.guild

        author = None

        async for entry in guild.audit_logs(
            limit=1, action=discord.AuditLogAction.kick
        ):
            if entry.target == member:
                author = entry.user

                embed = discord.Embed(
                    title="User Kick",
                    description=f"User {member.name}#{member.discriminator} was kicked from the server by {author}.",
                    colour=config.RED,
                )
                embed.set_author(
                    name=self.bot.user.name, icon_url=self.bot.user.avatar.url
                )
                embed.add_field(name="Reason", value=entry.reason)
                embed.add_field(name="Timestamp", value=dt)

                channel = guild.get_channel(config.LOG_CHAN)

                await channel.send(content=None, embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Perform various checks on each message posted in the Guild.

        Keyword arguments:
        self    -- self reference of the bot
        message -- message to scan
        """
        if message.author == self.bot.user:
            return

        if isinstance(message.channel, discord.channel.DMChannel):
            await message.reply(
                "This bot doesn't manage direct messages because the author is a lazy fuck."
            )
            return

        if not await check_spam_v2(self, message):
            await check_scam(self, message)
        await check_jac(self, message)
        await check_invites(self, message)
        await check_blacklist(self, message)
        await check_msg_link(self, message)


def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Events(bot))


async def check_spam_v2(self, message) -> bool:
    """Detects if a message has the typical scam format of @everyone and a link. Excludes admins and mods."""
    admin_role = message.guild.get_role(config.ADMIN_ID)
    mod_role = message.guild.get_role(config.MOD_ID)

    # Spam / phishing filtering
    scam_link = re.search(r"(?P<url>https?://[^\s]+)", message.content)

    # if not admin or mod and message is typical spam, block and notify
    if admin_role in message.author.roles or mod_role in message.author.roles:
        return False

    if scam_link is not None and "@everyone" in message.content:
        await message.delete()

        if scam_link.group("url") not in config.SCAM:
            log("INFO: Possible spam detected.")
            config.SCAM.append(scam_link.group("url"))
            await scam_check_embed(self, message, scam_link.group("url"))
        return True
    return False


async def check_jac(self, message):
    """Check posts inside the Join-A-Clan channel to find duplicates within the time limit.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check

    If a message in the config.CLAN_CHAN channel is sent from the same user or contains the
    same discord invite URL within the span of 14 days, intercept the message and warn the
    user for violating the rules of the channel.
    """
    if int(message.channel.id) == config.CLAN_CHAN:
        role = message.guild.get_role(config.MOD_ID)
        botrole = message.guild.get_role(config.BOT_ID)

        # Don't do anything if moderator sent message
        if role in message.author.roles:
            return
        # Don't do anything if bot (self) is talking
        if botrole in message.author.roles:
            return
        # Save entries in JAC db, check if existence
        jac = shelve.open(config.JAC)
        s = shelve.open(config.WARNINGS)

        if str(message.author.id) in jac:
            await issue_warn(
                self,
                s,
                message,
                f"**WARNING:** {message.author.mention}, you have already posted in the last 14 days.",
            )
            await message.delete()

        else:
            # Regexp the link
            link = re.search(r"(?P<url>[https?://]*discord.gg/[^\s]+)", message.content)

            if link is None:
                link = "No link posted"
            else:
                link = link.group("url")

                # Check if link already in db
                for _key, value in jac.items():
                    if value["link"] == link:

                        # Issue warning as link already exists
                        await issue_warn(
                            self,
                            s,
                            message,
                            f"**WARNING:** {message.author.mention}, ad has already been posted in the last 14 days.",
                        )
                        await message.delete()

                        s.close()
                        jac.close()
                        return

            # Get timestamp
            now = datetime.now(tz_TX)
            date = now.strftime(TIME_FORMAT)

            # Add entry because wasn't there before
            tmp = {"link": link, "date": date}
            jac[str(message.author.id)] = tmp
            jac.sync()

        s.close()
        jac.close()


async def check_scam(self, message):
    """Check each message to filter out possible scam or phishing URLs.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check

    Each message will be scanned to check either a known scam/phishing domain or
    suspicious text/phrases that were used by userbots to spread malicious URLs.
    """
    # Spam / phishing filtering
    scam_link = re.search(r"(?P<url>https?://[^\s]+)", message.content)

    if scam_link is not None:

        # discord nitro scam, aggressive check
        scam_msg = message.content.replace(scam_link.group("url"), "")

        if any(y in scam_msg.lower() for y in config.SCAMTEXT):
            try:
                await message.delete()

                if scam_link.group("url") not in config.SCAM:
                    config.SCAM.append(scam_link.group("url"))
                    log("INFO: nitro scam blocked.")
                    await scam_check_embed(self, message, scam_link.group("url"))

            except:
                log("INFO: Message not found.")

        # normal url scam check
        if any(x in scam_link.group("url") for x in config.SCAMURLS):
            try:
                await message.delete()

                if scam_link.group("url") not in config.SCAM:
                    config.SCAM.append(scam_link.group("url"))
                    log("INFO: general scam blocked.")
                    await scam_check_embed(self, message, scam_link.group("url"))

            except:
                log("INFO: message not found.")
    else:
        # discord nitro scam, aggressive check pt.2
        scam_msg = message.content

        if any(y in scam_msg.lower() for y in config.SCAMTEXT):
            await message.delete()

            if scam_msg not in config.SCAM:
                config.SCAM.append(scam_msg)

                await scam_check_embed(self, message, scam_msg)
                log("INFO: nitro text scam blocked.")


async def scam_check_embed(self, message, filtered_url):
    """Generate an embed with buttons to manage possible scam or phishing messages.

    Keyword arguments:
    self         -- self reference of the bot
    message      --  message to check
    filtered_url -- URL that was filtered from the message
    """
    # Define a list of two buttons that will be displayed under the embed
    # add filtered_url to custom_id to avoid action on pre-existing buttons
    ban_button = support.Scam(filtered_url)

    # Generate control embed in log channel
    embed = discord.Embed(
        title="Possible scam - manual review",
        description="Review the blocked message ",
        colour=config.RED,
    )
    embed.add_field(name="Suspicious message", value=message.content, inline=False)
    embed.add_field(name="Suspicious link", value=filtered_url)
    embed.add_field(name="Channel", value=message.channel.mention)
    embed.add_field(name="Author", value=message.author.mention)
    embed.add_field(
        name="Join date", value=message.author.joined_at.strftime(TIME_FORMAT)
    )
    embed.add_field(
        name="Creation date", value=message.author.created_at.strftime(TIME_FORMAT)
    )
    embed.set_footer(text=config.FOOTER)

    channel = message.guild.get_channel(config.LOG_CHAN)

    await channel.send(embed=embed, view=ban_button)

    # Wait for a mod to press a button
    await ban_button.wait()

    # If mod confirms ban
    if ban_button.value:
        log(f"INFO: Spam confirmed by {ban_button.user}")
        modrole = message.guild.get_role(config.MOD_ID)
        if modrole not in message.author.roles:

            new_embed = discord.Embed(
                title="Possible scam - manual review completed",
                description=f"Review of the blocked message was done by {ban_button.user}",
                colour=config.GREEN,
            )
            new_embed.add_field(
                name="Suspicious message", value=message.content, inline=False
            )
            new_embed.add_field(name="Suspicious link", value=filtered_url)
            new_embed.add_field(name="Author", value=message.author.mention)
            new_embed.add_field(
                name="Join date", value=message.author.joined_at.strftime(TIME_FORMAT)
            )
            new_embed.add_field(
                name="Creation date",
                value=message.author.created_at.strftime(TIME_FORMAT),
            )

            await ban_button.inter.message.edit(embed=new_embed, view=None)
            await message.author.ban(
                reason=f"Spam message confirmed by {ban_button.user}",
                delete_message_days=0,
            )
            try:
                config.SCAM.remove(filtered_url)
            except:
                pass

    # If mod cancels
    else:
        log(f"INFO: Spam negated by {ban_button.user}")
        new_embed = discord.Embed(
            title="Possible scam - manual review completed",
            description=f"Review of the blocked message was done by {ban_button.user}",
            colour=config.GREEN,
        )
        new_embed.add_field(
            name="Suspicious message", value=message.content, inline=False
        )
        new_embed.add_field(name="Suspicious link", value=filtered_url)
        new_embed.add_field(name="Author", value=message.author.mention)
        new_embed.add_field(
            name="Join date", value=message.author.joined_at.strftime(TIME_FORMAT)
        )
        new_embed.add_field(
            name="Creation date", value=message.author.created_at.strftime(TIME_FORMAT)
        )

        await ban_button.inter.message.edit(embed=new_embed, view=None)
        try:
            config.SCAM.remove(filtered_url)
        except:
            pass


async def check_invites(self, message):
    """Check each message for unauthorized discord invites.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check

    Perform a check on each message to intercept discord invites in any channel that
    is not config.CLAN_CHAN and warn the user who posted it. If the URL is in
    config.INVITE_WHITELIST, the message is ignored.
    """
    if "discord.gg/" in message.content:
        # Check if in invite whitelist
        if any(url in message.content for url in config.INVITE_WHITELIST):
            return
        else:
            role = message.guild.get_role(config.MOD_ID)
            # Whitelist mods, again
            if role in message.author.roles:
                pass
            elif message.channel.id == config.CLAN_CHAN:
                pass
            else:
                # Create warning message
                await message.channel.send(
                    f"**WARNING:** {message.author.mention}, do not post invite links."
                )

                reason = f"User posted invite link in {message.channel}"
                s = shelve.open(config.WARNINGS)
                if str(message.author.id) in s:
                    tmp = s[str(message.author.id)]
                    tmp["warnings"] = tmp.get("warnings") + 1
                    tmp["reasons"].append(reason)

                    s[str(message.author.id)] = tmp

                    s.close()
                else:
                    s[str(message.author.id)] = {
                        "warnings": 1,
                        "kicks": 0,
                        "bans": 0,
                        "reasons": [reason],
                        "tag": str(message.author),
                    }
                    s.close()

                # Generate log embed
                embed = discord.Embed(
                    title="Warning issued!",
                    description=f"Reason: {reason}",
                    colour=config.YELLOW,
                )
                embed.add_field(name="User:", value=f"{message.author}")
                embed.add_field(name="Issued by:", value=f"{self.bot.user.mention}")
                msg = (
                    (message.content[:1020] + "...")
                    if len(message.content) > 1024
                    else message.content
                )
                embed.add_field(name="Message:", value=msg, inline=False)
                embed.set_footer(text=config.FOOTER)

                channel = message.guild.get_channel(config.LOG_CHAN)
                await channel.send(content=None, embed=embed)
                log("Invite link blocked.")
                # Delete message
                await message.delete()


async def check_blacklist(self, message):
    """Check each message for blacklisted words.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check

    Perform a check on each message to intercept blacklisted words defined in
    config.BLACKLIST and warn user who posted any.
    """
    # Delete and warn for use of blacklisted (offensive, racist and all that) words
    if any(word in message.content.lower() for word in config.BLACKLIST):
        role = message.guild.get_role(config.MOD_ID)
        if role in message.author.roles:
            pass
        else:
            await message.channel.send(
                f"**WARNING:** {message.author.mention}, Use of offensive terms is prohibited."
            )

            reason = f"User sent prohibited word in {message.channel}"
            s = shelve.open(config.WARNINGS)
            if str(message.author.id) in s:
                tmp = s[str(message.author.id)]
                tmp["warnings"] = tmp.get("warnings") + 1
                tmp["reasons"].append(reason)

                s[str(message.author.id)] = tmp

                s.close()
            else:
                s[str(message.author.id)] = {
                    "warnings": 1,
                    "kicks": 0,
                    "bans": 0,
                    "reasons": [reason],
                    "tag": str(message.author),
                }
                s.close()

            # Generate log embed
            embed = discord.Embed(
                title="Warning issued!",
                description=f"Reason: {reason}",
                colour=config.YELLOW,
            )
            embed.add_field(name="User:", value=f"{message.author}")
            embed.add_field(name="Issued by:", value=f"{self.bot.user.name}")
            msg = (
                (message.content[:1020] + "...")
                if len(message.content) > 1024
                else message.content
            )
            embed.add_field(name="Message:", value=msg, inline=False)
            embed.set_footer(text=config.FOOTER)

            channel = message.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)
            # Delete message
            await message.delete()


async def check_msg_link(self, message):
    """Check if message contains a URL to another message in the same server and embed it.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check
    """
    # Embed the linked message showing content and author
    if "discord.com/channels/" in message.content:
        # Grab the link
        link_reg = re.search(
            r"(?P<url>[https?://]*discord.com/channels/[^\s]+)", message.content
        )

        if link_reg is None:
            return

        link_reg = link_reg.group("url")

        # Split the link into its path components
        link = link_reg.split("/")

        # server_id = int(link[4])
        channel_id = int(link[5])
        message_id = int(link[6])

        channel = message.guild.get_channel(channel_id)
        msg = await channel.fetch_message(message_id)
        msg.content = (
            (msg.content[:1020] + "...") if len(msg.content) > 1024 else msg.content
        )
        embed = discord.Embed(
            title=f"{msg.author}", description=msg.content, color=config.GREEN
        )
        embed.set_thumbnail(url=msg.author.avatar.url)
        embed.add_field(name="Channel", value=msg.channel)
        embed.add_field(
            name="Time", value=msg.created_at.strftime(TIME_FORMAT) + " UTC"
        )
        embed.set_footer(text=config.FOOTER)

        await message.reply(embed=embed)


async def issue_warn(self, s, message, warning):
    """Issue a warning to the specified user and create relative embed for JAC violations.

    Keyword arguments:
    self    -- self reference of the bot
    s       -- Shelve containing the warnings list
    message -- message that was scanned
    warning -- warning message"""
    # Notify and warn user
    await message.channel.send(warning)
    reason = f"User violated 14-day wait period in {message.channel}"

    # if the author is in the warnings database,
    # increase the relative warnings counter
    if str(message.author.id) in s:
        tmp = s[str(message.author.id)]
        tmp["warnings"] = tmp.get("warnings") + 1
        tmp["reasons"].append(reason)

        s[str(message.author.id)] = tmp

        # Check if multiple 14-days violation warnings
        count = 0
        for warn in s[str(message.author.id)]["reasons"]:
            if "User violated 14-day wait period" in warn:
                count = count + 1

        # If second violation, kick from the server
        # and notify user in DMs
        if count == 2 or count == 3:
            reason = "Kick: Multiple violations of 14-day rule in JAC"

            tmp = s[str(message.author.id)]
            tmp["kicks"] = tmp.get("kicks") + 1
            tmp["reasons"].append(reason)

            s[str(message.author.id)] = tmp

            await message.author.send(
                "You have been kicked from Drewski's Operators server for violating the 14-day wait period for clan ads multiple times."
            )
            await message.guild.kick(message.author, reason=reason)
        elif count == 4:
            reason = "Ban: Multiple kicks for violation of 14-day rule in JAC"

            await message.author.send(
                "You have been banned from Drewski's Operators server for violating the 14-day wait period for clan ads multiple times."
            )
            s.close()
            await message.guild.ban(message.author, reason=reason)
            return

        s.sync()
    else:
        s[str(message.author.id)] = {
            "warnings": 1,
            "kicks": 0,
            "bans": 0,
            "reasons": [reason],
            "tag": str(message.author),
        }
        s.sync()

    # Generate log embed
    embed = discord.Embed(
        title="Warning issued!", description=f"Reason: {reason}", colour=config.YELLOW
    )
    embed.add_field(name="User:", value=f"{message.author}")
    embed.add_field(name="Issued by:", value=f"{self.bot.user.mention}")
    embed.add_field(name="Message:", value="{Clan Advertisment}", inline=False)
    embed.set_footer(text=config.FOOTER)

    channel = message.guild.get_channel(config.LOG_CHAN)
    await channel.send(content=None, embed=embed)
