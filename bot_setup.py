"""Extensions and gateway intents of the bot, shared by franky.py and the tests."""
import discord

INIT_EXTENSIONS = [
    "cogs.admin",
    "cogs.moderation_slash",
    "cogs.users",
    "cogs.users-slash",
    "cogs.events",
    "cogs.automod",
    "cogs.jac",
    "cogs.honeypot",
    #"cogs.giveaway",
    #"cogs.poll",
    #"cogs.modalpoll",
]


def build_intents() -> discord.Intents:
    """Discord denied the privileged intents (presences, members, message_content).

    Kicks and timeouts come from the audit log (Intents.moderation), joins from
    the system join message, message filters from AutoMod
    (Intents.auto_moderation_execution). All of them are in Intents.default().
    """
    intents = discord.Intents.default()
    intents.presences = False
    intents.members = False
    intents.message_content = False
    return intents
