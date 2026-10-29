# pylint: disable=F0401, W0702, W0703, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Honeypot channel: auto-ban of the users who post in a trap channel.

The channel is a trap for spam bots. Every user who posts in it is banned,
with the exception of moderators and administrators. Moderators can cancel
the ban with the 'Unban' button of the log embed that on_member_ban creates.
"""
from datetime import timedelta
import discord
from discord.ext import commands
import config
import support
import cogs.database as db


#Setup module logging
log = support.get_logger(__name__)

TIME_FORMAT = "%b-%d-%Y %H:%M:%S"


# Define a view for the manual review of a honeypot hit
class HoneypotReview(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.value = None
        self.user = None
        self.inter = None

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.red)
    async def ban(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Banning", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.inter = interaction
        self.stop()

    @discord.ui.button(label="Release", style=discord.ButtonStyle.grey)
    async def release(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Releasing", ephemeral=True)
        self.value = False
        self.user = interaction.user
        self.inter = interaction
        self.stop()


class Honeypot(commands.Cog):

    database = None

    def __init__(self, bot):
        """Initialize Honeypot cog."""
        self.bot = bot
        self.database = db.Database(self.bot)
        # User IDs of the members that are under punishment, to avoid double bans
        self.processing = set()


    @commands.Cog.listener()
    async def on_message(self, message):
        """Check each new message posted in the honeypot channel."""
        await check_honeypot(self, message)


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        """Check each edited message in the honeypot channel."""
        await check_honeypot(self, after)


def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Honeypot(bot))


def is_honeypot(channel) -> bool:
    """Return True if the channel, or its parent channel, is the honeypot.

    Keyword arguments:
    channel -- channel of the message to check

    Threads have a different ID than their parent channel. A thread of the
    honeypot channel is part of the trap.
    """
    # getattr: config.py can be older than this cog until an owner runs !reconf
    honeypot_chan = getattr(config, "HONEYPOT_CHAN", 0)

    if not honeypot_chan:
        return False

    return honeypot_chan in (
        getattr(channel, "id", None),
        getattr(channel, "parent_id", None),
    )


async def check_honeypot(self, message):
    """Ban the author of a message posted in the honeypot channel.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check

    Bots, webhooks, moderators and administrators are excluded. With
    config.HONEYPOT_AUTOBAN set to False the author is muted for 24 hours and
    a manual review embed is sent to the log channel instead of the ban.
    """
    if not is_honeypot(message.channel):
        return

    # Ignore DMs, bots and webhooks
    if message.guild is None or message.webhook_id is not None:
        return

    if message.author.bot or not isinstance(message.author, discord.Member):
        return

    admin_role = message.guild.get_role(config.ADMIN_ID)
    mod_role = message.guild.get_role(config.MOD_ID)

    # Fail safe: without the roles the check below is not reliable and a
    # moderator can get banned. Do nothing and report the configuration error.
    if admin_role is None or mod_role is None:
        log.error("Honeypot disabled: config.ADMIN_ID or config.MOD_ID is not a role of the guild")
        return

    # if admin or mod, do nothing
    if admin_role in message.author.roles or mod_role in message.author.roles:
        return

    # The member is already under punishment for a previous message
    if message.author.id in self.processing:
        log.info("Honeypot: %s is already under punishment, message ignored",
                 message.author.id)
        return

    self.processing.add(message.author.id)
    purged = None
    review = False

    try:
        log.info("Honeypot hit: %s (%s)", message.author, message.author.id)

        # Send the notice before the punishment, because a banned user
        # does not receive direct messages from the bot.
        try:
            await message.author.send(config.HONEYPOT_DM)
        except Exception as err:
            log.info("Unable to send honeypot notice to %s: %s", message.author.id, err)

        if config.HONEYPOT_AUTOBAN:
            # on_member_ban in cogs/events.py adds the ban to the database and
            # sends the log embed with the 'Unban' button.
            await message.author.ban(
                reason=config.HONEYPOT_REASON,
                delete_message_seconds=config.HONEYPOT_DELETE_SECONDS,
            )
        else:
            await message.author.timeout_for(
                duration=timedelta(days=1), reason=config.HONEYPOT_REASON
            )
            try:
                await message.delete()
            except Exception as err:
                log.error("Unable to delete honeypot message: %s", err)

            # A timeout does not delete messages. Remove the recent messages of
            # the author from the other channels, as a ban would do.
            purged = await purge_user_messages(message.guild, message.author)
            review = True

    except discord.Forbidden as err:
        log.error("Honeypot: not enough permissions to punish %s: %s", message.author.id, err)
    except Exception as err:
        log.error("Honeypot error on user %s: %s", message.author.id, err)
    finally:
        # Free the guard here. The manual review below waits for a button press
        # and can stay open for hours, the guard must not last that long.
        self.processing.discard(message.author.id)

    # The punishment is complete. The review runs outside of the guard.
    if review:
        try:
            await honeypot_review_embed(self, message, purged)
        except Exception as err:
            log.error("Honeypot review failed for user %s: %s", message.author.id, err)


async def purge_user_messages(guild, member):
    """Delete the recent messages of a member from every channel of the guild.

    Keyword arguments:
    guild  -- Discord Guild of the member
    member -- author of the messages to delete

    A timeout does not delete messages, only a ban does. This function gives the
    same result without the ban. It reads the last config.HONEYPOT_PURGE_LIMIT
    messages of each text channel and thread, and deletes the ones that the
    member wrote in the last config.HONEYPOT_PURGE_SECONDS seconds.

    Returns a dictionary with the channel name as key and the count as value.
    The log file gets the count per channel. The bot cannot read the content
    of the messages (no MESSAGE_CONTENT intent), so the content is not logged.
    """
    seconds = getattr(config, "HONEYPOT_PURGE_SECONDS", 0)
    limit = getattr(config, "HONEYPOT_PURGE_LIMIT", 100)
    result = {}

    if not seconds:
        return result

    after = discord.utils.utcnow() - timedelta(seconds=seconds)
    me = guild.me

    def is_target(msg):
        """Select only the messages of the member."""
        return msg.author.id == member.id

    for channel in list(guild.text_channels) + list(guild.threads):

        # Skip the channels that the bot cannot clean
        perms = channel.permissions_for(me)
        if not perms.manage_messages or not perms.read_message_history:
            continue

        try:
            deleted = await channel.purge(
                limit=limit,
                check=is_target,
                after=after,
                bulk=True,
                reason=config.HONEYPOT_REASON,
            )
        except discord.Forbidden:
            log.error("Honeypot purge: no permission in channel %s", channel.id)
            continue
        except Exception as err:
            log.error("Honeypot purge failed in channel %s: %s", channel.id, err)
            continue

        if deleted:
            result[channel.name] = len(deleted)
            log.info("Honeypot purge: %s messages of %s removed in #%s",
                     len(deleted), member.id, channel.name)

    if result:
        log.info("Honeypot purge: %s messages of %s removed",
                 sum(result.values()), member.id)

    return result


async def honeypot_review_embed(self, message, purged=None):
    """Generate an embed with buttons for the manual review of a honeypot hit.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message that triggered the honeypot
    purged  -- dictionary of the channels cleaned by purge_user_messages

    Used only when config.HONEYPOT_AUTOBAN is False. The author is muted for
    24 hours and a moderator decides between the ban and the release. The embed
    has no message content: the bot cannot read it (no MESSAGE_CONTENT intent).
    """
    ban_button = HoneypotReview()

    embed = discord.Embed(
        title="Honeypot hit - manual review",
        description="The user posted in the honeypot channel and is muted for 24 hours.",
        colour=config.YELLOW,
    )

    embed.add_field(name="Channel", value=message.channel.mention)
    embed.add_field(name="Author", value=message.author.mention)
    embed.add_field(
        name="Join date", value=message.author.joined_at.strftime(TIME_FORMAT)
    )
    embed.add_field(
        name="Creation date", value=message.author.created_at.strftime(TIME_FORMAT)
    )

    # Tell the moderators what the purge removed. The deletion is not
    # reversible, the embed shows the count per channel.
    if purged:
        cleaned = "\n".join(f"#{name}: {count}" for name, count in purged.items())
        embed.add_field(
            name="Deleted messages", value=cleaned[:1024], inline=False
        )

    embed.set_footer(text=config.FOOTER)

    channel = message.guild.get_channel(config.LOG_CHAN)

    review = await channel.send(embed=embed, view=ban_button)

    # Wait for a mod to press a button
    await ban_button.wait()

    new_embed = discord.Embed(
        title="Honeypot hit - manual review completed",
        description=f"Review of the honeypot hit was done by {ban_button.user}",
        colour=config.GREEN,
    )
    new_embed.add_field(name="Author", value=message.author.mention)

    # If mod confirms ban
    if ban_button.value:
        log.info("Honeypot hit confirmed by %s", ban_button.user)
        new_embed.add_field(name="Result", value="Banned")
        try:
            await message.author.ban(
                reason=f"Honeypot hit confirmed by {ban_button.user}",
                delete_message_seconds=config.HONEYPOT_DELETE_SECONDS,
            )
        except Exception as err:
            log.error("Unable to ban honeypot user %s: %s", message.author.id, err)

    # If mod releases the user
    else:
        log.info("Honeypot hit negated by %s", ban_button.user)
        new_embed.add_field(name="Result", value="Released")
        try:
            await message.author.remove_timeout(
                reason="Honeypot review completed. Timeout removed"
            )
        except Exception as err:
            log.error("Unable to remove timeout of %s: %s", message.author.id, err)

    await review.edit(embed=new_embed, view=None)
