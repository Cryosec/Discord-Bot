# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from datetime import datetime
import pytz
import discord
from discord.ext import commands
import config
import support
import cogs.database as db


#Setup module logging
log = support.get_logger(__name__)

tz_TX = pytz.timezone("US/Central")
TIME_FORMAT = "%b-%d-%Y %H:%M:%S"

# Stored in jac.link: without MESSAGE_CONTENT the bot cannot read the invite
JAC_NO_LINK = "Not available"


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


    # Member join. Without the GUILD_MEMBERS intent there is no on_member_join:
    # on_message calls this for the system join message (author = new member).
    async def add_new_member(self, member):
        """Add new members to the database for monitoring."""
        try:
            self.database.addNewUser(str(member.id))
            log.info("New user %s added to monitoring list.", member)
        except Exception as e:
            log.error("Error adding new user %s to DB: %s", member, e)



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

    async def _get_user(self, user_id):
        """Get a user from the cache, or from the API if not cached."""
        if user_id is None:
            return None
        return self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

    # Without the GUILD_MEMBERS intent there is no on_member_remove or
    # on_member_update. The audit log (GUILD_MODERATION intent) tells us about
    # kicks and timeouts. The raw event fires also if the user is not cached.
    @commands.Cog.listener()
    async def on_raw_audit_log_entry(self, payload):
        """Log kicks and timeouts from the audit log.

        Keyword arguments:
        self    -- self reference of the bot
        payload -- RawAuditLogEntryEvent
        """
        if payload.action_type == discord.AuditLogAction.kick:
            await self.log_kick(payload)
        elif payload.action_type == discord.AuditLogAction.member_update:
            change = support.timeout_change(payload.changes)
            if change == "added":
                await self.log_timeout(payload)
            elif change == "removed":
                await self.log_timeout_removed(payload)
        elif payload.action_type == discord.AuditLogAction.auto_moderation_user_communication_disabled:
            # AutoMod TIMEOUT action: not a member_update entry
            rule = (payload.extra or {}).get("auto_moderation_rule_name", "unknown")
            await self.log_timeout(payload, author="AutoMod", reason=f"AutoMod rule: {rule}")

    async def log_kick(self, payload):
        """Manage logging of member kick."""
        now = datetime.now(tz_TX)
        dt = now.strftime(TIME_FORMAT)

        guild = self.bot.get_guild(payload.guild_id)
        member = await self._get_user(payload.target_id)
        author = await self._get_user(payload.user_id)

        embed = discord.Embed(
            title="User Kick",
            description=f"User {member.name}#{member.discriminator} was kicked from the server by {author}.",
            colour=config.RED,
        )
        embed.set_author(
            name=self.bot.user.name, icon_url=self.bot.user.avatar.url
        )
        embed.add_field(name="Reason", value=payload.reason)
        embed.add_field(name="Timestamp", value=dt)

        channel = guild.get_channel(config.LOG_CHAN)

        await channel.send(content=None, embed=embed)

        self.database.addKick(str(member.id), str(member.name), payload.reason)

    async def log_timeout(self, payload, author=None, reason=None):
        """Log a timeout, with a button to undo it."""
        guild = self.bot.get_guild(payload.guild_id)
        user = await self._get_user(payload.target_id)
        if author is None:
            author = await self._get_user(payload.user_id)

        # Create button to undo timeout
        undo_button = support.Untimeout()

        channel = guild.get_channel(config.LOG_CHAN)
        await channel.send(
            embed=support.timeout_embed(
                self.bot, user, author, reason or payload.reason
            ),
            view=undo_button
        )

        # Wait for button press on embed
        await undo_button.wait()

        # Respond to button press
        if undo_button.value:
            try:
                member = await guild.fetch_member(payload.target_id)
                await member.remove_timeout(reason="Timeout removed")
            except discord.NotFound:
                log.info("User %s left the server, no timeout to remove.", user)

    async def log_timeout_removed(self, payload):
        """Log the removal of a timeout."""
        now = datetime.now(tz_TX)
        dt = now.strftime(TIME_FORMAT)
        guild = self.bot.get_guild(payload.guild_id)
        user = await self._get_user(payload.target_id)

        embed = discord.Embed(
            title="User timeout removed",
            description = f"User {user.name}#{user.discriminator} timeout has been removed.",
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

        # System join message: track the new member, no filters to run
        if support.is_member_join(message):
            await self.add_new_member(message.author)
            return

        # Ignore DMs
        if isinstance(message.channel, discord.channel.DMChannel):
            await message.reply(
                "This bot doesn't manage direct messages because the author is a lazy fuck."
            )
            return

        # The honeypot cog manages its channel alone. The other filters must not
        # act on a message that is already deleted, or on a banned author.
        if message.channel.id == getattr(config, "HONEYPOT_CHAN", 0):
            return

        # Content filters (invites, scam, spam, blacklist) are Discord AutoMod
        # rules now: see automod_rules.py and cogs/automod.py.

        # Check for Join-A-Clan stuff
        await check_jac(self, message)


def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Events(bot))

async def check_jac(self, message):
    """Check posts inside the Join-A-Clan channel to find duplicates within the time limit.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check

    If a message in the config.CLAN_CHAN channel is sent from the same user within the
    span of 14 days, intercept the message and warn the user for violating the rules of
    the channel. Without the MESSAGE_CONTENT intent the invite link is not readable, so
    the check is per author only.
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

        if str(message.author.id) in map(lambda x: x['user_id'], jac):

            # DB logging happens within function
            await issue_warn(
                self,
                message,
                f"**WARNING:** {message.author.mention}, you have already posted in the last 14 days.",
            )
            await message.delete()
            # Add to kill counter
            self.database.addKillCount(str(message.author.id))

        else:
            # Get timestamp
            now = datetime.now(tz_TX)
            date = now.strftime(TIME_FORMAT)

            # Add entry because wasn't there before
            self.database.addJac(str(message.author.id), JAC_NO_LINK, date)


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

    if str(message.author.id) in map(lambda x: x['user_id'], warn_user):

        self.database.addWarning(str(message.author.id), str(message.author.name), reason)

        # Check if multiple 14-days violation warnings
        count = self.database.getWarnCount(str(message.author.id), reason)

        # If second violation, kick from the server
        # and notify user in DMs
        if count == 2 or count == 3:
            reason = "Kick: Multiple violations of 14-day rule in JAC"

            # No addKick here: the kick audit log entry stores it (log_kick)
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
