# Discord-Bot

[![Espresso License :coffee:](https://img.shields.io/badge/license-Espresso%20☕-7890F0.svg)](https://github.com/jack23247/espresso-license)

### This bot is full of small bugs here and there, use at your own mental health risk

This is the code for the Discord bot Lord Franklin used in the [community server](https://discord.gg/drewski) of [Youtuber](https://www.youtube.com/user/DrewskiTheAdventurer) and [Streamer](https://www.twitch.tv/operatordrewski/) OperatorDrewski.
The code is mostly specific to the structure and use-case in said server, but can be easily modified and adapted for a moltitude of servers. This bot is not meant to be run on multiple servers at the same time, instead being coded to best work with a single guild per instance.

## Requirements
The bot requires the following python requirements to run correctly:

* Python 3.10.4
* py-cord
* python-dotenv
* pytz
* asyncio
* cogwatch

## Setting up

First of all, it's necessary to have a valid bot token for the bot to work and connect to the Discord API. This token is private and should never be published or shared, as it may result in possible hijacking.

This bot loads the token from a `.env` file in the same directory as the main `franky.py` file. Within this file a single variable is set:
> DISCORD_TOKEN={your_token}

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
* `FOOTER` set to a string to personalize the footer of the bot's embeds.
* Colors:
    * `RED` set to `0xe74c3c`
    * `GREEN` set to `0x27ae60`
    * `YELLOW` set to `0xf1c40f`
    * `BLUE` set to `0x3498db`
    * `ORANGE` set to `0xf39c12`
    * `PURPLE` set to `0x8e44ad`
* `BLACKLIST` set to a list of strings, each being a word to censor.
* `SCAMURLS` set to a list of strings to search for and filter from possible scam URLs
* `SCAMTEXT` set to a list of strings to search for and filter from possible scam messages
* `SCAM` empty list that will support the execution of scam messages filtering
* `INVITE_WHITELIST` set to a list of discord invite URLs that will not be filtered.

There are three other variables used for commands meant as inside jokes between some community members, these are not part of the official scope of the bot. These variables are as follow:

* `LUNDY_ID` set to the integer ID of a user for the `!lundy` command.
* `TOXY_ID` set to the integer ID of a user for the `!toxy` command.
* `INSULTS` set to a list of strings, each being a light-hearted joke towards the user set for the `LUNDY_ID` variable.

Other variables used throughout the code are not listed here as they are part of temporary commands or events.

## Deployment

I run this bot inside a Docker container, on ~~a Raspberry Pi 4 connected through ethernet~~ (bot has been moved) an unRAID server. The container used by the bot is based on another container built to expedite container creation after updates to either the code base or dependencies. This base container is generated through the following Dockerfile script:

```Dockerfile
FROM python:3.10.4-slim-bullseye

WORKDIR /app

RUN python -m pip install python-dotenv pytz asyncio cogwatch
RUN python -m pip uninstall -y discord.py
RUN python -m pip install py-cord

```
> Note, Cogwatch installs discord.py as dependency, so it must be uninstalled before installing pycord

and the command in the same directory as the above Dockerfile:

> `docker build -t python-discord:3.1 .`

This image is available on [Docker Hub](https://hub.docker.com/r/cryosec/python-discord), for x86 environments.

The bot container is then generated through another Dockerfile script:

```Dockerfile
FROM python-discord:3.1

COPY ./ /app/

CMD ["python", "-u", "franky.py"]
```

and built with the command, in the same directory as the above Dockerfile:

> `docker build -t discord-bot:latest .`

