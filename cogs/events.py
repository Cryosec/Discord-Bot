# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import pytz
import discord
from discord.ext import commands
import config
import support
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


tz_TX = pytz.timezone("US/Central")
TIME_FORMAT = "%b-%d-%Y %H:%M:%S"


#def log(message):
#   """Log to console a message with added timestamp."""
#    now = datetime.now(timezone.utc)
#    print(f"{now} UTC - " + message)


class Events(commands.Cog):

    database = None

    def __init__(self, bot):
        """Initialize Events cog."""
        self.bot = bot
        self.database = db.Database(self.bot)


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

        # Add ban log to DB
        if ban_entry.reason is None:
            self.database.addBan(str(user.id), str(user), "Ban: No reason Specified")
        else:
            self.database.addBan(str(user.id), str(user), ban_entry.reason)

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
            self.database.delBan(str(user.id), ban_entry.reason)

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
            await unban_button.inter.edit_original_message(
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

        # Check if latest entry is actually a kick log
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

                self.database.addKick(str(member.id), str(member.name), entry.reason)

    # When a member gets timed out, this should be called
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Called when a member updates their profile.

        Args:
            before (Member): The updated member's old info
            after (Member): The updated member's new info
        """

        now = datetime.now(tz_TX)
        dt = now.strftime(TIME_FORMAT)
        guild = after.guild

        # If timed_out from false -> true
        if not before.timed_out and after.timed_out:

            # Get last entry of audit log that's a member update
            async for entry in guild.audit_logs(
                limit=1, action=discord.AuditLogAction.member_update
            ):
                # Check if it's the same user of the invoked event
                if entry.target == after:
                    # Get who caused the update
                    author = entry.user

                # Create button to undo timeout
                undo_button = support.Untimeout()

                channel = guild.get_channel(config.LOG_CHAN)
                await channel.send(
                    embed=support.timeout_embed(
                        self.bot, after, author, entry.reason
                    ),
                    view=undo_button
                )

                # Wait for button press on embed
                await undo_button.wait()

                # Respond to button press
                if undo_button.value:
                    await after.remove_timeout(reason="Timeout removed")


        # If timed_out from true -> false
        if not after.timed_out and before.timed_out:
            embed = discord.Embed(
                title="User timeout removed",
                description = f"User {after.name}#{after.discriminator} timeout has been removed.",
                colour = config.YELLOW,
            )
            embed.set_author(
                name = self.bot.user.name, icon_url = self.bot.user.avatar.url
            )
            embed.add_field(name="Timestamp", value = dt)

            channel = guild.get_channel(config.LOG_CHAN)
            await channel.send(embed=embed)


    @commands.Cog.listener()
    async def on_message(self, message):
        """Perform various checks on each message posted in the Guild.

        Keyword arguments:
        self    -- self reference of the bot
        message -- message to scan
        """
        # Ignore the bot messages
        if message.author == self.bot.user:
            return

        # Ignore DMs
        if isinstance(message.channel, discord.channel.DMChannel):
            await message.reply(
                "This bot doesn't manage direct messages because the author is a lazy fuck."
            )
            return

        await check_invites(self, message)
        if not await check_spam_v2(self, message):
            await check_scam(self, message)
        await check_jac(self, message)
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

        #await message.respond("Your message has been removed as it violates our anti-spam filters", ephemeral=True)
        await message.delete()

        if scam_link.group("url") not in config.SCAM:
            log.info("Possible spam detected: %s", message.content)
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

        jac = self.database.getJac()
        #warn_users = self.database.getWarnUsers()

        if str(message.author.id) in map(lambda x: x[0], jac):

            # DB logging happens within function
            await issue_warn(
                self,
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
                # TODO: check if this is correct
                if link in map(lambda x: x[1], jac):

                    # Issue warning as link already exists
                    await issue_warn(
                        self,
                        message,
                        f"**WARNING:** {message.author.mention}, ad has already been posted in the last 14 days.",
                    )
                    await message.delete()
                    return

            # Get timestamp
            now = datetime.now(tz_TX)
            date = now.strftime(TIME_FORMAT)

            # Add entry because wasn't there before
            self.database.addJac(str(message.author.id), link, date)


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
                #await message.respond("Your message has been deleted as it violates our anti-scam filters", ephemeral=True)
                await message.delete()
                if scam_link.group("url") not in config.SCAM:
                    config.SCAM.append(scam_link.group("url"))
                    log.info("Nitro scam blocked.")
                    await scam_check_embed(self, message, scam_link.group("url"))

            except:
                log.exception("Message not found.")

        # normal url scam check
        if any(x in scam_link.group("url") for x in config.SCAMURLS):
            try:
                #await message.respond("Your message has been deleted as it violates our anti-scam filters", ephemeral=True)
                await message.delete()

                if scam_link.group("url") not in config.SCAM:
                    config.SCAM.append(scam_link.group("url"))
                    log.info("General scam blocked.")
                    await scam_check_embed(self, message, scam_link.group("url"))

            except:
                log.exception("Message not found.")
    else:
        # discord nitro scam, aggressive check pt.2
        scam_msg = message.content

        if any(y in scam_msg.lower() for y in config.SCAMTEXT):
            #await message.respond("Your message has been deleted as it violates our anti-scam filters", ephemeral=True)
            await message.delete()

            if scam_msg not in config.SCAM:
                config.SCAM.append(scam_msg)

                await scam_check_embed(self, message, scam_msg)
                log.info("Nitro text scam blocked.")


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
        log.info("Spam confirmed by %s", ban_button.user)
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
        log.info("Spam negated by %s", ban_button.user)
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
            mod_role = message.guild.get_role(config.MOD_ID)
            admin_role = message.guild.get_role(config.ADMIN_ID)
            # if not admin or mod and message is typical spam, block and notify
            if admin_role in message.author.roles or mod_role in message.author.roles:
                pass
            elif message.channel.id == config.CLAN_CHAN:
                pass
            else:

                # Delete message
                await message.delete()

                # Check if invite is in banlist - immediately ban
                if any(url in message.content for url in config.INVITE_BANLIST):
                    await message.author.ban(reason="Blacklisted invite")
                    return

                # Create warning message
                await message.channel.send(
                    f"**WARNING:** {message.author.mention}, do not post invite links."
                )

                reason = f"User posted invite link in {message.channel}"
                self.database.addWarning(str(message.author.id), str(message.author.name), reason)

                # Check if user is spamming invites, done horribly
                if self.database.getWarnCount(str(message.author.id), reason) >= 3:
                    await message.author.timeout_for(timedelta(days=1), reason="Too many invite warnings")

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
                log.info("Invite link blocked.")



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

            self.database.addWarning(str(message.author.id), str(message.author.name), reason)

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

        # limit embed to 1024 chars, as per discord limits
        msg.content = (
            (msg.content[:1020] + "...") if len(msg.content) > 1024 else msg.content
        )
        embed = discord.Embed(
            title=f"{msg.author}", description=msg.content, color=config.GREEN
        )

        # Check if message content is an image URL, then embed the image
        if msg.attachments:
            embed.set_image(url=msg.attachments[0].url)

        # Define remove button
        remove_button = support.Remove()

        embed.set_thumbnail(url=msg.author.avatar.url)
        embed.add_field(name="Channel", value=msg.channel)
        embed.add_field(
            name="Time", value=msg.created_at.strftime(TIME_FORMAT) + " UTC"
        )
        embed.set_footer(text=config.FOOTER)

        # Reply with remove button
        reply = await message.reply(embed=embed, view=remove_button)

        await remove_button.wait()

        # Manage remove button behaviour
        role = message.guild.get_role(config.MOD_ID)

        if remove_button.user == msg.author or role in remove_button.user.roles:
            await reply.delete(reason="Poster removed embed")


async def issue_warn(self, message, warning):
    """Issue a warning to the specified user and create relative embed for JAC violations.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message that was scanned
    warning -- warning message"""
    # Notify and warn user
    await message.channel.send(warning)
    reason = f"User violated 14-day wait period in {message.channel}"

    # if the author is in the warnings database,
    # increase the relative warnings counter

    warn_user = self.database.getWarnUsers()

    if str(message.author.id) in map(lambda x: x[0], warn_user):

        self.database.addWarning(str(message.author.id), str(message.author.name), reason)

        # Check if multiple 14-days violation warnings
        count = self.database.getWarnCount(str(message.author.id), reason)

        # If second violation, kick from the server
        # and notify user in DMs
        if count == 2 or count == 3:
            reason = "Kick: Multiple violations of 14-day rule in JAC"

            self.database.addKick(str(message.author.id), str(message.author.name), reason)

            try:
                await message.author.send(
                    "You have been kicked from Drewski's Operators server for violating the 14-day wait period for clan ads multiple times."
                )
            except:
                print("Error sending message to user for warning.")
            await message.guild.kick(message.author, reason=reason)
        elif count == 4:
            reason = "Ban: Multiple kicks for violation of 14-day rule in JAC"
            #self.database.addBan(str(message.author.id), str(message.author.name), reason)
            try:
                await message.author.send(
                    "You have been banned from Drewski's Operators server for violating the 14-day wait period for clan ads multiple times."
                )
            except:
                print("Error sending message to user for warning.")
            await message.guild.ban(message.author, reason=reason)
            return

    else:
        self.database.addWarning(str(message.author.id), str(message.author), reason)

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
