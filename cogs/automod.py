# pylint: disable=F0401, W0702, W0703, W0105, W0613
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Act on the Discord AutoMod rules created by automod_rules.py.

The bot has no MESSAGE_CONTENT intent, so it cannot read messages. AutoMod
reads them and sends AUTO_MODERATION_ACTION_EXECUTION (not a privileged
intent; Discord sends it only to bots with the Manage Server permission). The payload has no content: the bot works with the rule, the user,
the channel and the matched keyword.
"""
import time
from datetime import timedelta
import discord
from discord.ext import commands
import config
import support
import automod_rules as ar
import cogs.database as db

#Setup module logging
log = support.get_logger(__name__)

TIME_FORMAT = "%b-%d-%Y %H:%M:%S"

# Two rules (for example scam and everyone-spam) can match the same message.
# Act once per user and kind of action in this window.
DEDUP_SECONDS = 30

WOULD = {
    ar.BAN: "would ban the user",
    ar.REVIEW: "would time out the user for 1 day and post a scam review",
    ar.WARN: "would warn the user",
}


def dry_run() -> bool:
    """True unless config.AUTOMOD_DRY_RUN is exactly False. !reconf changes it live."""
    return getattr(config, "AUTOMOD_DRY_RUN", True) is not False


def alert_link(payload) -> str:
    """Link to the AutoMod alert message, which shows the blocked content to mods."""
    if payload.alert_system_message_id is None:
        return "Not available"
    return (f"https://discord.com/channels/{payload.guild_id}/"
            f"{payload.action.metadata.channel_id}/{payload.alert_system_message_id}")


class AutoMod(commands.Cog):

    database = None

    def __init__(self, bot):
        """Initialize AutoMod cog."""
        self.bot = bot
        self.database = db.Database(self.bot)
        self.rule_names = {}  # rule id -> rule name without PREFIX, None if not a bot rule
        self.recent = {}      # (kind, user id) -> monotonic time of the last action

    @commands.Cog.listener()
    async def on_auto_moderation_action_execution(self, payload):
        """Map an AutoMod rule execution to the action of the old content filter."""
        # Every bot rule has exactly one alert action. Block and alert of the same
        # message arrive as two events: act only on the alert.
        if payload.action.type != discord.AutoModActionType.send_alert_message:
            return

        guild = payload.guild or self.bot.get_guild(payload.guild_id)
        if guild is None:
            log.error("AutoMod execution for uncached guild %s ignored", payload.guild_id)
            return
        name = await self.rule_name(guild, payload.rule_id)
        kind = ar.RULE_KIND.get(name)
        if kind is None:
            return

        if dry_run():
            if not self.is_duplicate(kind, payload.user_id):
                await self.dry_run_embed(guild, payload, name, kind)
            return

        # Every matching message goes, also when the action below is a duplicate
        await self.remove_message(guild, payload)
        if self.is_duplicate(kind, payload.user_id):
            return
        try:
            if kind == ar.BAN:
                # The user is gone: skip the review or warning of the same message
                self.is_duplicate(ar.REVIEW, payload.user_id)
                self.is_duplicate(ar.WARN, payload.user_id)
                await guild.ban(discord.Object(id=payload.user_id), reason="Blacklisted invite")
            elif kind == ar.REVIEW:
                await self.scam_review(guild, payload, name)
            elif kind == ar.WARN:
                await self.warn(guild, payload)
        except Exception:
            log.exception("AutoMod action %s for user %s failed", kind, payload.user_id)

    async def rule_name(self, guild, rule_id):
        """Rule name from its ID. The rule list is fetched again only for unknown IDs."""
        if rule_id not in self.rule_names:
            try:
                rules = await guild.fetch_auto_moderation_rules()
            except discord.HTTPException as err:
                log.error("Cannot read the AutoMod rules (Manage Server permission?): %s", err)
                return None
            self.rule_names = {
                r.id: r.name[len(ar.PREFIX):] if r.name.startswith(ar.PREFIX) else None
                for r in rules
            }
            self.rule_names.setdefault(rule_id, None)
        return self.rule_names[rule_id]

    def is_duplicate(self, kind, user_id) -> bool:
        """Record an action; True if the same action for the user is recent."""
        now = time.monotonic()
        self.recent = {k: t for k, t in self.recent.items() if now - t < DEDUP_SECONDS}
        if (kind, user_id) in self.recent:
            return True
        self.recent[(kind, user_id)] = now
        return False

    async def remove_message(self, guild, payload):
        """Delete the message if the rule did not block it, and count the kill."""
        if payload.message_id is not None:
            # Alert-only rule: the message is still in the channel
            channel = guild.get_channel_or_thread(payload.channel_id)
            try:
                await channel.get_partial_message(payload.message_id).delete()
            except discord.NotFound:
                pass  # already deleted
            except (AttributeError, discord.HTTPException) as err:
                log.error("Unable to delete message %s: %s", payload.message_id, err)
                return
        self.database.addKillCount(str(payload.user_id))

    async def fetch_member(self, guild, user_id):
        """Member from the API (no GUILD_MEMBERS cache), None if the user left."""
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            return None

    async def dry_run_embed(self, guild, payload, name, kind):
        """Report what the bot would do, without doing it."""
        embed = discord.Embed(
            title="AutoMod dry run",
            description=f"Rule `{name}` matched: the bot {WOULD[kind]}.",
            colour=config.YELLOW,
        )
        embed.add_field(name="User", value=f"<@{payload.user_id}>")
        embed.add_field(name="Channel", value=f"<#{payload.channel_id}>")
        embed.add_field(name="Matched keyword", value=f"`{payload.matched_keyword}`")
        embed.add_field(name="AutoMod alert", value=alert_link(payload), inline=False)
        embed.set_footer(text=config.FOOTER)
        await guild.get_channel(config.LOG_CHAN).send(embed=embed)

    def review_embed(self, payload, name, member, title, description, colour):
        """Embed of a scam review. The message content is in the AutoMod alert."""
        embed = discord.Embed(title=title, description=description, colour=colour)
        embed.add_field(name="Rule", value=name)
        embed.add_field(name="Matched keyword", value=f"`{payload.matched_keyword}`")
        embed.add_field(name="Channel", value=f"<#{payload.channel_id}>")
        embed.add_field(name="Author", value=f"<@{payload.user_id}>")
        if member is not None and member.joined_at is not None:
            embed.add_field(name="Join date", value=member.joined_at.strftime(TIME_FORMAT))
        embed.add_field(
            name="Creation date",
            value=discord.utils.snowflake_time(payload.user_id).strftime(TIME_FORMAT),
        )
        embed.add_field(name="AutoMod alert", value=alert_link(payload), inline=False)
        embed.set_footer(text=config.FOOTER)
        return embed

    async def scam_review(self, guild, payload, name):
        """Time out the author for 1 day and let a mod ban or cancel."""
        member = await self.fetch_member(guild, payload.user_id)
        if member is not None:
            try:
                await member.timeout_for(duration=timedelta(days=1),
                                         reason=support.AUTOMOD_REVIEW_REASON)
            except Exception as err:
                log.error("Couldn't timeout user for spam review: %s", err)

        ban_button = support.Scam(payload.matched_keyword)
        embed = self.review_embed(
            payload, name, member, "Possible scam - manual review",
            "Review the blocked message in the AutoMod alert.", config.RED,
        )
        channel = guild.get_channel(config.LOG_CHAN)
        await channel.send(embed=embed, view=ban_button)

        # Wait for a mod to press a button
        await ban_button.wait()

        done = self.review_embed(
            payload, name, member, "Possible scam - manual review completed",
            f"Review of the blocked message was done by {ban_button.user}", config.GREEN,
        )
        await ban_button.inter.message.edit(embed=done, view=None)

        if ban_button.value:
            log.info("Spam confirmed by %s", ban_button.user)
            modrole = guild.get_role(config.MOD_ID)
            if member is not None and modrole in member.roles:
                return
            await guild.ban(
                discord.Object(id=payload.user_id),
                reason=f"Spam message confirmed by {ban_button.user}",
                delete_message_seconds=43200, # 12 hours
            )
        else:
            log.info("Spam negated by %s", ban_button.user)
            if member is not None:
                try:
                    await member.remove_timeout(reason="Spam review completed. Timeout removed")
                except Exception as err:
                    log.error("Couldn't remove the review timeout: %s", err)

    async def warn(self, guild, payload):
        """Warn the user for a blacklisted word, as the old check_blacklist."""
        channel = guild.get_channel_or_thread(payload.channel_id)
        user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)

        if channel is not None:
            await channel.send(
                f"**WARNING:** <@{payload.user_id}>, Use of offensive terms is prohibited."
            )

        reason = f"User sent prohibited word in {channel}"
        self.database.addWarning(str(payload.user_id), str(user.name), reason)

        # Generate log embed
        embed = discord.Embed(
            title="Warning issued!",
            description=f"Reason: {reason}",
            colour=config.YELLOW,
        )
        embed.add_field(name="User:", value=f"{user}")
        embed.add_field(name="Issued by:", value=f"{self.bot.user.name}")
        embed.add_field(name="Matched keyword:", value=f"||{payload.matched_keyword}||")
        embed.add_field(name="AutoMod alert", value=alert_link(payload), inline=False)
        embed.set_footer(text=config.FOOTER)
        await guild.get_channel(config.LOG_CHAN).send(content=None, embed=embed)


def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(AutoMod(bot))
