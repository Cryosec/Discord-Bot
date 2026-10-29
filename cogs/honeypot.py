# pylint: disable=F0401, W0702, W0703, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Honeypot channel: auto-ban of the users who post in a trap channel.

The channel is a trap for spam bots. Every user who posts in it is banned,
with the exception of moderators and administrators. Moderators can cancel
the ban with the 'Unban' button of the log embed that on_member_ban creates.
The manual review (non-autoban mode) has persistent Ban/Release buttons.
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


HONEYPOT_BAN_ID = "lf:honeypot:ban"
HONEYPOT_RELEASE_ID = "lf:honeypot:release"


class HoneypotReviewView(discord.ui.View):
    """Persistent Ban/Release buttons of the honeypot review. State: "User ID", "Timeout until"."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Ban", custom_id=HONEYPOT_BAN_ID, style=discord.ButtonStyle.red)
    async def ban(self, button, interaction):
        await support.press(self.cog, interaction, self.act_ban(interaction), log)

    @discord.ui.button(label="Release", custom_id=HONEYPOT_RELEASE_ID,
                       style=discord.ButtonStyle.grey)
    async def release(self, button, interaction):
        await support.press(self.cog, interaction, self.act_release(interaction), log)

    @staticmethod
    def done_embed(message, interaction, result):
        """The completed embed: the Author field of the review and the result."""
        embed = discord.Embed(
            title="Honeypot hit - manual review completed",
            description=f"Review of the honeypot hit was done by {interaction.user}",
            colour=config.GREEN,
        )
        author = support.embed_fields(message.embeds[0]).get("Author")
        if author is not None:
            embed.add_field(name="Author", value=author)
        embed.add_field(name="Result", value=result)
        return embed

    def act_ban(self, interaction):
        """Ban without a relevance check (a mod decision)."""
        async def run(message):
            user_id = int(support.embed_fields(message.embeds[0])["User ID"])
            log.info("Honeypot hit confirmed by %s", interaction.user)
            try:
                await interaction.guild.ban(
                    discord.Object(id=user_id),
                    reason=f"Honeypot hit confirmed by {interaction.user}",
                    delete_message_seconds=config.HONEYPOT_DELETE_SECONDS,
                )
            except discord.NotFound as err:
                # Unknown user: the ban did not happen, never mark it done
                raise support.Refused("Discord does not know this user: not banned.") from err
            return support.Closing(self.done_embed(message, interaction, "Banned"), "Banned.")
        return run

    def act_release(self, interaction):
        """Remove the review timeout, if it is still the one of the embed."""
        async def run(message):
            fields = support.embed_fields(message.embeds[0])
            member = await support.timeout_member(
                interaction.guild, int(fields["User ID"]), fields.get("Timeout until"))
            log.info("Honeypot hit negated by %s", interaction.user)
            await member.remove_timeout(reason="Honeypot review completed. Timeout removed")
            return support.Closing(
                self.done_embed(message, interaction, "Released"), "Released.")
        return run


class Honeypot(commands.Cog):

    database = None

    def __init__(self, bot):
        """Initialize Honeypot cog."""
        self.bot = bot
        self.database = db.Database(self.bot)
        # User IDs of the members that are under punishment, to avoid double bans
        self.processing = set()
        self.review_locks = {}  # review message ID -> asyncio.Lock, see support.press
        # Loaded or reloaded (cogwatch) while the bot runs: on_ready does not fire again
        if bot.is_ready():
            bot.add_view(HoneypotReviewView(self))

    @commands.Cog.listener()
    async def on_ready(self):
        """Register the persistent buttons after a restart."""
        self.bot.add_view(HoneypotReviewView(self))


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
    until = None
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
            # The end goes in the review embed (the Release button checks it). It is
            # computed just before timeout_for computes its own: the Release check
            # allows support.TIMEOUT_TOLERANCE seconds of difference.
            until = discord.utils.utcnow() + timedelta(days=1)
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
        # Free the guard here: the review below only posts the embed, but the
        # guard must not cover the log channel call.
        self.processing.discard(message.author.id)

    # The punishment is complete. The review runs outside of the guard.
    if review:
        try:
            await honeypot_review_embed(self, message, purged, until)
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


async def honeypot_review_embed(self, message, purged=None, until=None):
    """Generate an embed with buttons for the manual review of a honeypot hit.

    Keyword arguments:
    self    -- self reference of the bot
    message -- message that triggered the honeypot
    purged  -- dictionary of the channels cleaned by purge_user_messages
    until   -- datetime end of the review timeout (stored in the embed)

    Used only when config.HONEYPOT_AUTOBAN is False. The author is muted for
    24 hours and a moderator decides between the ban and the release. The embed
    has no message content: the bot cannot read it (no MESSAGE_CONTENT intent).
    """
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

    # State for the persistent buttons (the view keeps nothing in memory)
    embed.add_field(name="User ID", value=str(message.author.id))
    if until is not None:
        embed.add_field(name="Timeout until", value=until.isoformat())

    embed.set_footer(text=config.FOOTER)

    channel = message.guild.get_channel(config.LOG_CHAN)

    # The persistent buttons (HoneypotReviewView) do the follow-up
    await channel.send(embed=embed, view=HoneypotReviewView(self))
