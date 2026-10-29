# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Join-A-Clan ads through a modal: /jac post and a pinned "Post your clan" button.

The bot has no MESSAGE_CONTENT intent, so it cannot read ads posted as
messages. A modal submission contains the text: the bot checks it and posts
the ad as an embed in config.CLAN_CHAN. @everyone must not be able to send
messages there (channel permission, set by hand), only use application commands.
"""
import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pytz
import discord
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands
import config
import support
import cogs.database as db

#Setup module logging
log = support.get_logger(__name__)

tz_TX = pytz.timezone("US/Central")
TIME_FORMAT = "%b-%d-%Y %H:%M:%S"
JAC_DAYS = 14

BUTTON_ID = "jac-post"
PLATFORMS = ["PC", "Xbox", "PlayStation"]

_INVITE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)/?(?:\?\S*)?$",
    re.IGNORECASE,
)
# Links outside the invite field: AutoMod does not check the bot's embed
_LINK = re.compile(r"https?://|www\.|discord\.gg/|discord(?:app)?\.com/invite", re.IGNORECASE)


def parse_invite(link) -> str | None:
    """Invite code of a Discord invite link, None if the text is anything else."""
    match = _INVITE.match((link or "").strip())
    return match.group(1) if match else None


def same_invite(a, b) -> bool:
    """Compare invite codes ignoring case: vanity invites are case-insensitive."""
    return a is not None and b is not None and a.lower() == b.lower()


def invite_url(code: str) -> str:
    return f"https://discord.gg/{code}"


@dataclass
class JacPost:
    """The fields of the /jac post modal."""
    name: str
    link: str
    platforms: list = field(default_factory=list)
    description: str = ""
    guild_id: str | None = field(default=None, compare=False)  # set by validate


class JacPostModal(discord.ui.DesignerModal):
    """Clan name, invite link, platforms and description."""

    def __init__(self, cog):
        self.cog = cog
        self.name_input = discord.ui.InputText(
            custom_id="jac-name", max_length=60, placeholder="Clan name")
        self.link_input = discord.ui.InputText(
            custom_id="jac-link", max_length=100, placeholder="https://discord.gg/...")
        self.platform_select = discord.ui.Select(
            custom_id="jac-platform",
            placeholder="Platforms",
            options=[discord.SelectOption(label=p, value=p) for p in PLATFORMS],
            min_values=0,
            max_values=len(PLATFORMS),
            required=False,
        )
        self.description_input = discord.ui.InputText(
            custom_id="jac-description", style=discord.InputTextStyle.long,
            max_length=1000, placeholder="Who you are, what you play, what you look for")
        super().__init__(
            discord.ui.Label("Clan name", self.name_input),
            discord.ui.Label("Invite link", self.link_input,
                             description="A Discord invite to your clan server"),
            discord.ui.Label("Platform", self.platform_select),
            discord.ui.Label("Description", self.description_input),
            title="Post your clan",
            timeout=1800,  # a dismissed modal leaves the ModalStore
        )

    async def callback(self, interaction: discord.Interaction):
        await self.cog.submit(interaction, JacPost(
            name=self.name_input.value or "",
            link=self.link_input.value or "",
            platforms=list(self.platform_select.values or []),
            description=self.description_input.value or "",
        ))


class JacPostView(discord.ui.View):
    """Persistent view with the button of the pinned message in the JAC channel."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Post your clan", custom_id=BUTTON_ID, style=discord.ButtonStyle.primary)
    async def post(self, button, interaction):
        await interaction.response.send_modal(JacPostModal(self.cog))


class Jac(commands.Cog):

    database = None

    jac = SlashCommandGroup("jac", "Join-A-Clan ads", guild_ids=[config.GUILD])

    def __init__(self, bot):
        """Initialize Jac cog."""
        self.bot = bot
        self.database = db.Database(self.bot)
        # Validation and posting run one at a time, so the 14-day dedup holds
        self.lock = asyncio.Lock()
        # Loaded or reloaded (cogwatch) while the bot runs: on_ready does not fire again
        if bot.is_ready():
            bot.add_view(JacPostView(self))

    async def cog_command_error(self, ctx, error):
        """Answer a refused /jac info: without it the user sees "did not respond"."""
        if isinstance(error, commands.CheckFailure) and isinstance(ctx, discord.ApplicationContext):
            await ctx.respond("Only moderators can use this command.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """Register the persistent button, so it works after a restart."""
        self.bot.add_view(JacPostView(self))

    @jac.command(name="post")
    async def jac_post(self, ctx):
        """Post an ad for your clan in the Join-A-Clan channel."""
        await ctx.send_modal(JacPostModal(self))

    @jac.command(name="info")
    @commands.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def jac_info(
        self, ctx, member: Option(discord.Member, "Member for which to show JAC status")
    ):
        """Get the details of the JAC entry for a selected user (moderators)."""
        jac = self.database.getJacByID(str(member.id))

        if len(jac) > 0:
            now = datetime.now(tz_TX)
            dt = datetime.strptime(jac[0]['date'], TIME_FORMAT)
            dt = dt.replace(tzinfo=tz_TX)

            end = dt + timedelta(days=JAC_DAYS)

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

    @commands.command(name="jacsetup", hidden=True)
    @commands.is_owner()
    async def jac_setup(self, ctx):
        """Post and pin the message with the "Post your clan" button.

        Without MESSAGE_CONTENT, prefix commands need the mention: @bot jacsetup.
        Every run posts and pins a new message.
        """
        channel = await self.bot.fetch_channel(config.CLAN_CHAN)
        embed = discord.Embed(
            title="Looking for a clan? Recruiting?",
            description=(
                "Press **Post your clan** or use `/jac post` to publish your clan ad.\n"
                f"One ad per member every {JAC_DAYS} days, and one ad per invite every {JAC_DAYS} days."
            ),
            colour=config.GREEN,
        )
        embed.set_footer(text=config.FOOTER)
        message = await channel.send(embed=embed, view=JacPostView(self))
        await message.pin(reason="Join-A-Clan instructions")

    async def validate(self, user_id: int, post: JacPost) -> str | None:
        """Reason to refuse the ad, None if it can be published."""
        code = parse_invite(post.link)
        if code is None:
            return "The invite link must be a Discord invite, like https://discord.gg/yourclan."

        if _LINK.search(post.name) or _LINK.search(post.description):
            return "Do not put links in the clan name or description: use the invite link field."

        # The bot posts the ad: AutoMod does not check bot messages
        texts = " ".join([post.name, post.link, post.description]).lower()
        substrings = [t.strip().lower() for t in (list(config.INVITE_BANLIST)
                      + list(config.SCAMURLS) + list(config.SCAMTEXT)) if t.strip()]
        words = [w.strip().lower() for w in config.BLACKLIST if w.strip()]
        if (any(same_invite(code, parse_invite(t)) for t in config.INVITE_BANLIST)
                or any(t in texts for t in substrings)
                or any(re.search(rf"\b{re.escape(w)}\b", texts) for w in words)):
            return "This ad is not allowed. Contact a moderator if this is a mistake."

        # check_timers removes rows older than 14 days only once per hour
        now = datetime.now(tz_TX).replace(tzinfo=None)
        recent = []
        for row in self.database.getJac():
            try:
                again = datetime.strptime(row['date'], TIME_FORMAT) + timedelta(days=JAC_DAYS)
            except (TypeError, ValueError):
                again = None
            if again is None or again >= now:
                recent.append((row, again))

        # Checks that need no API call first
        for row, again in recent:
            if row['user_id'] == str(user_id):
                when = f" You can post again after {again.strftime(TIME_FORMAT)} (US/Central)." if again else ""
                return f"You can post one ad every {JAC_DAYS} days.{when}"
            if same_invite(parse_invite(row['link']), code):
                return f"This invite was already posted in the last {JAC_DAYS} days."

        try:
            invite = await self.bot.fetch_invite(code)
        except discord.NotFound:
            return "This invite is invalid or expired."
        if invite.guild is None:
            return "The invite must be to a Discord server, not to a group DM."
        if invite.guild.id == config.GUILD:
            return "Post an invite to your clan server, not to this server."

        # Same server with another invite code. Rows from before the guild_id
        # column (or from the web UI) have no server id: the code check covers them.
        guild_id = str(invite.guild.id)
        if any(str(row.get('guild_id')) == guild_id for row, _ in recent if row.get('guild_id')):
            return f"This server was already posted in the last {JAC_DAYS} days."
        post.guild_id = guild_id
        return None

    async def submit(self, interaction: discord.Interaction, post: JacPost):
        """Check the ad, then post it and store it, or tell the user why not."""
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.lock:
                reply = await self.publish(interaction.user, post)
        except Exception:
            log.exception("Clan ad of %s failed", interaction.user.id)
            reply = "Something went wrong while posting your ad. Try again later."
        await interaction.followup.send(reply, ephemeral=True)

    async def publish(self, user, post: JacPost) -> str:
        """Validate, post and store the ad. Returns the answer for the user."""
        error = await self.validate(user.id, post)
        if error:
            return error

        link = invite_url(parse_invite(post.link))
        embed = discord.Embed(title=post.name, description=post.description, colour=config.GREEN)
        embed.add_field(name="Invite", value=link)
        embed.add_field(name="Platform", value=", ".join(post.platforms) or "Not specified")
        embed.add_field(name="Posted by", value=user.mention)
        embed.set_footer(text=config.FOOTER)

        channel = (self.bot.get_channel(config.CLAN_CHAN)
                   or await self.bot.fetch_channel(config.CLAN_CHAN))
        message = await channel.send(embed=embed)

        try:
            self.database.addJac(str(user.id), link, datetime.now(tz_TX).strftime(TIME_FORMAT),
                                 guild_id=post.guild_id)
        except Exception:
            log.exception("Clan ad of %s posted but not stored", user.id)
        log.info("Clan ad posted by %s: %s", user.id, link)
        return f"Your clan ad is posted: {message.jump_url}"


def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Jac(bot))
