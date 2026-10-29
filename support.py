# pylint: disable=F0401, W0702, W0703, W0105, W0613, unused-variable
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import asyncio
import inspect
import discord
from datetime import datetime, timezone
import pytz
import config
import logging
from logging.handlers import RotatingFileHandler
import os

# Define a simple view with two buttons, confirm and cancel
class Confirm(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
        self.user = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_message("Confirming", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Cancelling", ephemeral=True)
        self.value = False
        self.user = interaction.user
        self.stop()


class BanButton(discord.ui.Button):
    def __init__(self, button_id):
        super().__init__(
            label="Ban", style=discord.ButtonStyle.red, custom_id="ban" + button_id
        )

    async def callback(self, interaction: discord.Interaction):

        # Who pressed the button
        user = interaction.user


class StopPoll(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.value = None

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.blurple)
    async def stop_poll(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_message("Stopping poll", ephemeral=True)
        self.value = True
        self.stop()

tz_TX = pytz.timezone("US/Central")
TIME_FORMAT = "%b-%d-%Y %H:%M:%S"

# Audit-log reasons of the bot's own review timeouts: they already have a
# review embed, so events.log_timeout does not log them a second time.
AUTOMOD_REVIEW_REASON = "Temporary timeout for spam review"


def is_review_timeout(reason):
    """True if `reason` is the audit reason of a bot review timeout.

    The honeypot reason is read at call time: !reconf reloads config.py.
    """
    if not reason:
        return False
    return reason in (AUTOMOD_REVIEW_REASON, getattr(config, "HONEYPOT_REASON", None))


# Support function for timeout log event
def timeout_embed(
    bot: discord.Bot, user: discord.Member, author: discord.Member, reason: str,
    until: str | None = None,
) -> discord.Embed:
    """Generate log embed for a user timeout event

    Args:
        user (User): The user that received the timeout
        author (User): The user that called the timeout
        reason (String): Reason for the timeout
        until (String): ISO end of the timeout, from the audit log change. The
            Undo button reads it back (see timeout_member). None for the AutoMod
            TIMEOUT action: its audit entry has no changes.
    """

    # Generate timestamp
    now = datetime.now(tz_TX)
    dt = now.strftime(TIME_FORMAT)

    embed = discord.Embed(
        title="User timeout issued",
        description=f"User {user.name}#{user.discriminator} has been timed out by {author}.",
        colour=config.YELLOW,
    )
    embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Timestamp", value=dt)
    # State for the persistent Undo button (the view keeps nothing in memory)
    embed.add_field(name="User ID", value=str(user.id))
    if until:
        embed.add_field(name="Timeout until", value=until)

    return embed


def timeout_change(changes) -> str:
    """Read the raw 'changes' of a MEMBER_UPDATE audit log entry.

    The bot has no GUILD_MEMBERS intent, so it gets timeouts from the audit log.

    Returns:
        "added" if a timeout was set or extended, "removed" if it was
        removed, None if the entry is not about a timeout.
    """
    for change in changes or []:
        if change.get("key") != "communication_disabled_until":
            continue
        if change.get("new_value") is not None:
            return "added"
        if change.get("old_value") is not None:
            return "removed"
    return None


def is_member_join(message) -> bool:
    """True if the message is the system 'user joined' message of a human.

    Without the GUILD_MEMBERS intent there is no on_member_join. The join
    system message comes with GUILD_MESSAGES, and its author is the new member.
    """
    return message.type == discord.MessageType.new_member and not message.author.bot

# Define a persistent view for @Survivor role
class Survivor(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Join the Survivors", custom_id="survivor-join", style=discord.ButtonStyle.primary)
    async def button_add_role(self, button, interaction):

        role = interaction.guild.get_role(config.SURV_ID)

        if role not in interaction.user.roles:
            await interaction.user.add_roles(role, reason="Member pressed button in #rules channel")
            await interaction.response.send_message("Welcome to the Survivors! You can now see the DayZ channels.", ephemeral=True)
        else:
            await interaction.response.send_message("You're already a Survivor! Head down to #dayz-announcements for the most recent updates.", ephemeral=True)

    @discord.ui.button(label="Leave the Survivors", custom_id="survivor-leave", style=discord.ButtonStyle.danger)
    async def button_rem_role(self, button, interaction):

        role = interaction.guild.get_role(config.SURV_ID)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Member pressed button in #rules channel")
            await interaction.response.send_message("Sad to see you go! You can join back any time.", ephemeral=True)
        else:
            await interaction.response.send_message("You're not a Survivor! Can't remove a role you don't have.", ephemeral=True)



def get_logger(name):
    """Configura e restituisce un logger standardizzato."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Evita duplicati: se il logger ha già handler, non aggiungerne altri
    if logger.handlers:
        return logger

    # Evita propagazione al root logger (rimuove il 4° log duplicato)
    logger.propagate = False

    # Assicura che la cartella logs esista
    if not os.path.exists("logs"):
        os.makedirs("logs")

    log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")

    # File Handler
    file_handler = RotatingFileHandler(
        filename=f"logs/{name}.log",
        mode="a",
        maxBytes=20000,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# ---------------------------------------------------------------------------
# Persistent log buttons (Unban, Undo timeout, scam review, honeypot review).
#
# The views keep no state: the user, the ban reason and the timeout end are
# fields of the embed ("User ID", "Reason", "Timeout until"), so a button
# works after a restart or a cog reload. `press` is the flow they all share.
# ---------------------------------------------------------------------------

# Two timeout ends are the same if they are this close (in seconds). The review
# timeouts store utcnow()+1 day computed by the bot before the API call; Discord
# applies the value computed inside timeout_for, a few milliseconds later.
TIMEOUT_TOLERANCE = 2


class Refused(Exception):
    """The press is refused with a message: nothing was done, the buttons stay."""


class Closing:
    """What a button did: the embed that closes the message, and the DB step."""

    def __init__(self, embed, answer="Done.", after=None):
        self.embed = embed
        self.answer = answer
        self.after = after  # callable (sync or async): DB update, runs after the edit


def is_mod(user) -> bool:
    """True if the member holds config.MOD_ID or config.ADMIN_ID (interaction members carry roles)."""
    allowed = {config.MOD_ID, config.ADMIN_ID}
    return any(role.id in allowed for role in getattr(user, "roles", None) or [])


def embed_fields(embed) -> dict:
    """Name -> value of the embed fields: the state of a persistent view."""
    return {field.name: field.value for field in embed.fields}


def parse_until(value):
    """Aware datetime from an ISO timeout end (audit log string), None if unreadable."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def same_until(current, expected) -> bool:
    """Compare two timeout ends as datetimes (within TIMEOUT_TOLERANCE seconds), never as strings."""
    current, expected = parse_until(current), parse_until(expected)
    if current is None or expected is None:
        return False
    return abs((current - expected).total_seconds()) <= TIMEOUT_TOLERANCE


async def timeout_member(guild, user_id, until=None):
    """Fetch the member of a timeout and check that the timeout is still the one of the embed.

    Raises Refused if the user left, or if the timeout is not the one of the
    embed any more (`until` is the embed's "Timeout until"). Without `until`
    (AutoMod TIMEOUT action) it only checks that the member is still timed out.
    """
    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound as err:
        raise Refused("The user left the server: no timeout to remove.") from err
    current = member.communication_disabled_until
    if until is not None:
        still = current is not None and same_until(current, until)
    else:
        still = current is not None and parse_until(current) > discord.utils.utcnow()
    if not still:
        raise Refused("The timeout was already changed: nothing done.")
    return member


async def press(cog, interaction, act, log):
    """Common flow of a persistent log button.

    Mod check, defer, per-message lock, "still open" check, then
    `act(message)`: it does the Discord action and returns a Closing, or raises
    Refused (nothing done, buttons stay). Order: action -> edit the message to
    the closing embed without a view -> DB step. A failed Discord action keeps
    the buttons. A failed edit or DB step is logged and told to the mod; the DB
    step runs also after a failed edit, so a second press cannot repeat it.
    `cog.review_locks` maps message ID -> asyncio.Lock.
    """
    if not is_mod(interaction.user):
        await interaction.response.send_message(
            "Only moderators can use this button.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    async def reply(text):
        try:
            await interaction.followup.send(text, ephemeral=True)
        except Exception as err:
            log.error("Cannot answer the button press: %s", err)

    message_id = interaction.message.id
    lock = cog.review_locks.setdefault(message_id, asyncio.Lock())
    closed = False
    try:
        async with lock:
            try:
                message = await interaction.channel.fetch_message(message_id)
            except discord.NotFound:
                closed = True
                await reply("This review was already handled.")
                return
            except discord.HTTPException as err:
                log.error("Cannot read the log message %s: %s", message_id, err)
                await reply(f"Cannot read the log message: {err}")
                return
            if not message.components:
                closed = True
                await reply("This review was already handled.")
                return

            try:
                closing = await act(message)
            except Refused as err:
                await reply(str(err))
                return
            except discord.HTTPException as err:
                log.error("Action of the button on message %s failed: %s", message_id, err)
                await reply(f"Discord refused the action: {err}")
                return
            except Exception:
                log.exception("Action of the button on message %s failed", message_id)
                await reply("Unexpected error: nothing was changed, the buttons stay.")
                return

            answer = closing.answer
            try:
                await message.edit(embed=closing.embed, view=None)  # closes the message
                closed = True
            except Exception as err:
                log.error("Done, but the log message %s was not updated: %s", message_id, err)
                answer += " The log message could not be updated: check the state by hand."
            if closing.after is not None:
                try:
                    result = closing.after()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    log.exception("DB update after the button on message %s failed", message_id)
                    answer += (" The database update failed: fix the counter in the"
                               " dashboard. The message is closed, do not press again.")
            await reply(answer)
    finally:
        if closed:
            cog.review_locks.pop(message_id, None)
