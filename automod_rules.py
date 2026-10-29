# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""AutoMod rules that replace the content filters of cogs/events.py.

Discord denied the MESSAGE_CONTENT intent, so the bot cannot read messages.
Discord AutoMod reads them for us: this script creates one rule per filter
from the lists in config.py, and cogs/automod.py acts on the rule executions.

Run it once, outside the bot (the bot needs the Manage Server permission):

    python automod_rules.py --check                  # print the rules, no API calls
    python automod_rules.py                          # create/update, alert only
    python automod_rules.py --enforce scam invites   # also block the messages
    python automod_rules.py --alert-only scam        # stop blocking again
    python automod_rules.py --disable                # rollback: disable all bot rules

It is idempotent: rules are found by name (PREFIX + rule name). New rules only
send an alert. An existing rule keeps its block action unless --alert-only
names it, so re-running the script after a config change does not undo
--enforce. Every run without --disable re-enables the bot rules and resets
their keywords and exemptions to config.py: manual edits in Discord are lost.
"""
import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass, field

import discord

PREFIX = "LF "
AUDIT_REASON = "Lord Franklin AutoMod migration"
BLOCK_MESSAGE = "Your message was blocked by the server filters. Contact a moderator if this is a mistake."

# Rule names
INVITE_BANLIST = "invite-banlist"
INVITES = "invites"
SCAM = "scam"
BLACKLIST = "blacklist"
EVERYONE_SPAM = "everyone-spam"

# What cogs/automod.py does when a rule fires
BAN = "ban"
REVIEW = "review"
WARN = "warn"

RULE_KIND = {
    INVITE_BANLIST: BAN,
    INVITES: REVIEW,
    SCAM: REVIEW,
    BLACKLIST: WARN,
    EVERYONE_SPAM: REVIEW,
}

# Discord limits
MAX_KEYWORDS = 1000
MAX_KEYWORD_LEN = 60
MAX_REGEX = 10
MAX_REGEX_LEN = 260
MAX_ALLOW_LIST = 100
MAX_KEYWORD_RULES = 6

# Same links as the old check_invites. discord.com/channels (message links) is
# not an invite, so it is not in the list.
INVITE_PATTERNS = ["discord.gg/", "discord.com/invite/", "discordapp.com/invite/"]

# Characters with a special meaning in Rust regex syntax
_REGEX_META = set("\\.+*?()|[]{}^$#&-~")
_EVERYONE = r"@(?:everyone|here)"


@dataclass
class RuleSpec:
    """One AutoMod KEYWORD rule, as plain data."""
    name: str
    keywords: list = field(default_factory=list)
    regex_patterns: list = field(default_factory=list)
    allow_list: list = field(default_factory=list)
    exempt_roles: list = field(default_factory=list)
    exempt_channels: list = field(default_factory=list)


def wildcards(words) -> list:
    """Keywords that match anywhere in a word, like the old substring checks.

    AutoMod is case-insensitive, so lowercase and duplicates go away.
    """
    result = []
    for word in words:
        if "*" in word:
            raise ValueError(f"'*' is an AutoMod wildcard, remove it from the config entry {word!r}")
        keyword = f"*{word.strip().lower()}*"
        if keyword != "**" and keyword not in result:
            result.append(keyword)
    return result


def rust_escape(text: str) -> str:
    """Escape only the Rust regex metacharacters (re.escape also escapes spaces)."""
    return "".join("\\" + c if c in _REGEX_META else c for c in text)


def everyone_spam_patterns(nsfw) -> list:
    """Regexes for the old check_spam_v2.

    @everyone with a link, or @everyone/@here with a NSFW word, in any order.
    Long NSFW lists are split so that each pattern stays under MAX_REGEX_LEN.
    """
    patterns = [
        r"(?i)@everyone[\s\S]*https?://",
        r"(?i)https?://[\s\S]*@everyone",
    ]
    words = [rust_escape(w.strip().lower()) for w in nsfw if w.strip()]
    templates = [
        "(?i)" + _EVERYONE + r"[\s\S]*(?:{})",
        r"(?i)(?:{})[\s\S]*" + _EVERYONE,
    ]
    overhead = max(len(t.format("")) for t in templates)
    groups, current = [], []
    for word in words:
        if current and overhead + len("|".join(current + [word])) > MAX_REGEX_LEN:
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    for group in groups:
        for template in templates:
            patterns.append(template.format("|".join(group)))
    return patterns


def build_rules(cfg) -> list:
    """Rule specs from config.py. Raises ValueError if a Discord limit is exceeded."""
    mods = [cfg.MOD_ID, cfg.ADMIN_ID]
    banlist = wildcards(cfg.INVITE_BANLIST)
    specs = [
        RuleSpec(INVITE_BANLIST, keywords=banlist,
                 exempt_roles=mods, exempt_channels=[cfg.CLAN_CHAN]),
        # Banlisted invites are in the allow list: only their own rule acts on them.
        RuleSpec(INVITES, keywords=wildcards(INVITE_PATTERNS),
                 allow_list=wildcards(cfg.INVITE_WHITELIST) + banlist,
                 exempt_roles=mods, exempt_channels=[cfg.CLAN_CHAN]),
        RuleSpec(SCAM, keywords=wildcards(list(cfg.SCAMURLS) + list(cfg.SCAMTEXT))),
        RuleSpec(BLACKLIST, keywords=wildcards(cfg.BLACKLIST), exempt_roles=[cfg.MOD_ID]),
        RuleSpec(EVERYONE_SPAM, regex_patterns=everyone_spam_patterns(cfg.NSFW),
                 exempt_roles=mods),
    ]
    for spec in specs:
        _validate(spec)
    return specs


def _validate(spec: RuleSpec):
    too_long = [k for k in spec.keywords + spec.allow_list if len(k) > MAX_KEYWORD_LEN]
    if too_long:
        raise ValueError(f"{spec.name}: keywords over {MAX_KEYWORD_LEN} characters: {too_long}")
    if len(spec.keywords) > MAX_KEYWORDS:
        raise ValueError(f"{spec.name}: more than {MAX_KEYWORDS} keywords")
    if len(spec.allow_list) > MAX_ALLOW_LIST:
        raise ValueError(f"{spec.name}: more than {MAX_ALLOW_LIST} allow_list entries")
    if len(spec.regex_patterns) > MAX_REGEX:
        raise ValueError(f"{spec.name}: more than {MAX_REGEX} regex patterns")
    if any(len(p) > MAX_REGEX_LEN for p in spec.regex_patterns):
        raise ValueError(f"{spec.name}: regex pattern over {MAX_REGEX_LEN} characters")
    if len(spec.exempt_roles) > 20 or len(spec.exempt_channels) > 50:
        raise ValueError(f"{spec.name}: too many exempt roles or channels")


def build_actions(enforce: bool, alert_channel_id: int) -> list:
    """Every rule sends an alert. Enforced rules also block the message."""
    actions = [discord.AutoModAction(
        discord.AutoModActionType.send_alert_message,
        discord.AutoModActionMetadata(channel_id=alert_channel_id),
    )]
    if enforce:
        actions.insert(0, discord.AutoModAction(
            discord.AutoModActionType.block_message,
            discord.AutoModActionMetadata(custom_message=BLOCK_MESSAGE),
        ))
    return actions


def _is_blocking(rule) -> bool:
    return any(a.type == discord.AutoModActionType.block_message for a in rule.actions)


def _names(names) -> set:
    names = set(names or ())
    if "all" in names:
        return set(RULE_KIND)
    unknown = names - set(RULE_KIND)
    if unknown:
        raise ValueError(f"Unknown rule names: {sorted(unknown)}. Valid: {sorted(RULE_KIND)}")
    return names


async def sync_rules(guild, specs, alert_channel_id, enforce=(), alert_only=(),
                     disable=False, log=print):
    """Create or update the bot rules in the guild, or disable them all."""
    enforce, alert_only = _names(enforce), _names(alert_only)
    if enforce & alert_only:
        raise ValueError(f"Both --enforce and --alert-only name: {sorted(enforce & alert_only)}")
    existing = {r.name: r for r in await guild.fetch_auto_moderation_rules()}

    if disable:
        for spec in specs:
            rule = existing.get(PREFIX + spec.name)
            if rule is not None and rule.enabled:
                await rule.edit(enabled=False, reason=AUDIT_REASON)
                log(f"disabled {rule.name}")
        return

    others = [r for name, r in existing.items()
              if not name.startswith(PREFIX)
              and r.trigger_type == discord.AutoModTriggerType.keyword]
    if len(others) + len(specs) > MAX_KEYWORD_RULES:
        raise ValueError(
            f"The guild has {len(others)} other KEYWORD rules: adding {len(specs)} "
            f"exceeds the limit of {MAX_KEYWORD_RULES}."
        )

    for spec in specs:
        name = PREFIX + spec.name
        rule = existing.get(name)
        if spec.name in alert_only:
            blocking = False
        else:
            blocking = spec.name in enforce or (rule is not None and _is_blocking(rule))
        kwargs = dict(
            trigger_metadata=discord.AutoModTriggerMetadata(
                keyword_filter=spec.keywords,
                regex_patterns=spec.regex_patterns,
                allow_list=spec.allow_list,
            ),
            actions=build_actions(blocking, alert_channel_id),
            enabled=True,
            exempt_roles=[discord.Object(id=i) for i in spec.exempt_roles],
            exempt_channels=[discord.Object(id=i) for i in spec.exempt_channels],
            reason=AUDIT_REASON,
        )
        mode = "block + alert" if blocking else "alert only"
        if rule is None:
            await guild.create_auto_moderation_rule(
                name=name,
                event_type=discord.AutoModEventType.message_send,
                trigger_type=discord.AutoModTriggerType.keyword,
                **kwargs,
            )
            log(f"created {name} ({mode})")
        else:
            await rule.edit(**kwargs)
            log(f"updated {name} ({mode})")


async def _run(args, cfg):
    from dotenv import load_dotenv
    load_dotenv()
    client = discord.Client(intents=discord.Intents.none())
    try:
        # HTTP only: no gateway connection is needed to manage rules
        await client.login(os.getenv("DISCORD_TOKEN"))
        guild = await client.fetch_guild(cfg.GUILD)
        await sync_rules(
            guild, build_rules(cfg),
            getattr(cfg, "AUTOMOD_ALERT_CHAN", cfg.LOG_CHAN),
            enforce=args.enforce, alert_only=args.alert_only, disable=args.disable,
        )
    finally:
        await client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="validate config.py and print the rules, no API calls")
    parser.add_argument("--enforce", nargs="+", metavar="RULE", default=(),
                        help=f"add the block action ('all' or: {', '.join(RULE_KIND)})")
    parser.add_argument("--alert-only", nargs="+", metavar="RULE", default=(),
                        help="remove the block action")
    parser.add_argument("--disable", action="store_true",
                        help="disable every rule created by this script")
    args = parser.parse_args(argv)

    import config  # pylint: disable=import-outside-toplevel
    specs = build_rules(config)
    if args.check:
        print(json.dumps([asdict(s) for s in specs], indent=2))
        return
    asyncio.run(_run(args, config))


if __name__ == "__main__":
    main()
