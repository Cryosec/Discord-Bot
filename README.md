# Discord-Bot

[![Espresso License :coffee:](https://img.shields.io/badge/license-Espresso%20☕-7890F0.svg)](https://github.com/jack23247/espresso-license)

### This bot is full of small bugs here and there, use at your own mental health risk

This is the code for the Discord bot Lord Franklin used in the [community server](https://discord.gg/drewski) of [Youtuber](https://www.youtube.com/user/DrewskiTheAdventurer) and [Streamer](https://www.twitch.tv/operatordrewski/) OperatorDrewski.
The code is mostly specific to the structure and use-case in said server, but can be easily modified and adapted for a moltitude of servers. This bot is not meant to be run on multiple servers at the same time, instead being coded to best work with a single guild per instance.

## Requirements
The bot requires the following python requirements to run correctly:

* python-dotenv
* pytz
* asyncio
* cogwatch
* sqlalchemy
* mariadb
* py-cord

You can find these in the requirements.txt file.

## Setting up

First of all, it's necessary to have a valid bot token for the bot to work and connect to the Discord API. This token is private and should never be published or shared, as it may result in possible hijacking.

This bot loads the token from a `.env` file in the same directory as the main `franky.py` file, under the name `DISCORD_TOKEN`.

This token will be auto-loaded when executing the main python script, hence the `python-dotenv` dependency.

The bot uses a `config.py` file with the necessary global variables. By default the bot needs:

* Persistence files:
    * `WARNINGS` set to a filename for the warnings list.
    * `TIMED` set to a filename for the list of timed events.
    * `JAC` set to a filename for the list of users who posted in the join-a-clan channel.
* `GUILD` set with the integer ID of the Guild the bot will run in.
* Roles:
    * `MOD_ID` set to the integer ID of the moderator role.
    * `ADMIN_ID` set to the integer ID of the administrator role.
    * `BOT_ID` set to the integer ID of the bot.
    * `MUTE_ID` set to the integer ID of the *muted* role.
* Channels:
    * `LOG_CHAN` set to the integer ID of the channel the bot will use for logging.
    * `UCMD_CHAN` set to the integer ID of the channel the users will type commands in.
    * `MCMD_CHAN` set to the integer ID of the channel the mods will type commands in.
    * `CLAN_CHAN` set to the integer ID of the channel where users will post clan invites.
    * `RULE_CHAN` set to the integer ID of the channel where rules are posted.
* `FOOTER` set to a string to personalize the footer of the bot's embeds.
* Colors:
    * `RED` set to `0xe74c3c`
    * `GREEN` set to `0x27ae60`
    * `YELLOW` set to `0xf1c40f`
    * `BLUE` set to `0x3498db`
    * `ORANGE` set to `0xf39c12`
    * `PURPLE` set to `0x8e44ad`
* `BLACKLIST` set to a list of strings, each being a word to censor.
* `SCAMURLS` set to a list of strings to search for and filter from possible scam URLs.
* `SCAMTEXT` set to a list of strings to search for and filter from possible scam messages.
* `SCAM` empty list that will support the execution of scam messages filtering.
* `INVITE_WHITELIST` set to a list of discord invite URLs that will not be filtered.
* `INVITE_BANLIST` set to a list of discord invites that will cause an immediate ban of the poster.
* `GA_ACCESS` set to a list of integer IDs of the users allowed to post giveaways.
* `GA_CHANNELS`set to a list of integer IDs of channels where giveaways can be posted.

There are other variables used for commands meant as inside jokes between some community members, these are not part of the official scope of the bot. These variables are as follow:

* `LUNDY_ID` set to the integer ID of a user for the `!lundy` command.
* `TOXY_ID` set to the integer ID of a user for the `!toxy` command.
* `INSULTS` set to a list of strings, each being a light-hearted joke towards the user set for the `LUNDY_ID` variable.
* `GOOZ_ID`
* `AVYY_ID`
* `CRYO_ID`
* `LOTTO_ID`

Moreover, short and long descriptions for commands are stored in their own constant string in the `config.py` file.
The list is as follows:

```python
# BRIEF descriptors of commands
BRIEF_MUTE = 'Give "Muted" role to specified user'
BRIEF_UNMUTE = 'Remove "Muted" role from specified user'
BRIEF_WARN = 'Issue a warning to specified user'
BRIEF_UNWARN = 'Remove last warning from specified user'
BRIEF_WARNINGS = 'Show a paginator with all warnings'
BRIEF_CLEAR = 'Remove all warnings from specified user'
BRIEF_STATUS = 'View status report on specified user'
BRIEF_TIMERS = 'View all current timers for bans and mutes'
BRIEF_DELETE = 'Delete last n messages from current chat'
BRIEF_KICK = 'Kick specified user from the server'
BRIEF_BAN = 'Ban specified user from the server'
BRIEF_TEMPBAN = 'Temporarly ban user for set time'
BRIEF_JAC = 'Get information on a user JAC log'
BRIEF_SLOW = 'Set a slowmode timer in the specified channel'
BRIEF_POLL = 'Create a poll in the specified channel'

# users.py | users-slash.py strings

# Help messages by command
ROLES_BRIEF = 'Get information about roles used in the server'
TWITCH_BRIEF = 'Get information about the Twitch integration'
PATREON_BRIEF = 'Get information about the Patreon integration'
FAQ_BRIEF = 'Get information about the most frequently asked questions'
JOINED_BRIEF = 'Get information about when you last joined the server'
ME_BRIEF = 'Get information on your Account in the server. Once per day.'
MERCH_BRIEF = 'Get information on OperatorDrewski\'s merch'
RR_BRIEF = '1 in 6 chance to get yourself banned permanently. Use at your own risk.'
```

Longer descriptors are in the following list, not including the string content (for length purposes):

```plaintext
HELP_MUTE
HELP_UNMUTE
HELP_UNWARN
HELP_WARNINGS
HELP_CLEAR
HELP_STATUS
HELP_DELETE
HELP_KICK
HELP_BAN
HELP_TEMPBAN
HELP_JAC
HELP_TIMERS
HELP_POLL
HELP_INFO_MOD

ROLES_INFO
TWITCH_INFO
TWITCH_URL
FAQ
DAYZ_ANNOUNCE
DAYZ_BRIEF
DAYZ_DESC
```

Other variables used throughout the code are not listed here as they are part of temporary commands or events.

## Deployment

I run this bot inside a Docker container, on ~~a Raspberry Pi 4 connected through ethernet~~ (bot has been moved) an unRAID server. The container used by the bot is a Debian Bookworm image, with some necessary changes done at creation time:

```Dockerfile
FROM debian:bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libmariadb3 libmariadb-dev

RUN apt-get install -y python3-pip python3.11-venv

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY ./ /app/

CMD ["python", "-u", "franky.py"]
```


