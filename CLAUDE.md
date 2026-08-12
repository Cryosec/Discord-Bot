# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Lord Franklin" — a **single-guild** Discord moderation/community bot (py-cord) for OperatorDrewski's server, plus an optional web admin dashboard for moderators. The bot is a live production service that performs destructive actions (bans, kicks, message deletion, timeouts), so treat changes accordingly (see Testing & rollout).

> ⚠️ **CRITICAL — `cogs/` is live-editing production.** The running bot watches `cogs/` with **cogwatch** and hot-reloads on save. Any edit you write to a file under `cogs/` is applied to the **production bot immediately**, with no build, restart, or deploy step and no confirmation. There is no staging boundary between the working tree and prod for cog code. Do not edit files in `cogs/` as scratch/experimentation, do not save partial or intermediate states, and never leave a cog in a broken state — a syntax error or exception at import time takes that cog (and its moderation coverage) offline the moment you save. Make changes only when they are complete and correct, or work on a copy outside `cogs/` first.

## Big picture: two processes, one database

There are two independently-running programs that **share a MariaDB database but do not talk to each other**:

1. **The Discord bot** — `franky.py` + `cogs/` (py-cord). DB access goes through the `Database` cog in [cogs/database.py](cogs/database.py).
2. **The web UI** — `webui/backend/app.py` (Flask REST API) + `webui/frontend/` (React SPA). The backend is a *second, independent client* of the same MariaDB, with its own connection logic in `get_db_connection()`.

Consequence: **DB write logic is duplicated.** A schema change or new table usually needs mirroring in both [cogs/database.py](cogs/database.py) and [webui/backend/app.py](webui/backend/app.py). The web UI has no live channel to the running bot — it only reads/writes the shared tables.

## Running & building

The bot requires a `.env` (secrets: `DISCORD_TOKEN`, `DB_USERNAME/PASSWORD/HOST/PORT/NAME`) and a `config.py` — **both are gitignored** and must exist before the bot starts.

- **Run the bot:** `python -u franky.py`
- **Run the web backend:** `gunicorn --bind 0.0.0.0:5000 webui.backend.app:app --worker-class gevent --workers 4` (needs its own `.env` in `webui/backend/`, plus a Redis server for sessions)
- **Frontend dev server:** `cd webui/frontend && npm run dev`
- **Frontend build:** `cd webui/frontend && npm run build` (Vite → `dist/`, which Flask serves in production)
- **Frontend lint:** `cd webui/frontend && npm run lint`
- **Docker (both processes in one container):** the root [Dockerfile](Dockerfile) builds the frontend, then its `CMD` runs gunicorn in the background and the bot in the foreground. Deployment is via the unRAID template `lord-franklin-bot.xml`.

There is **no Python test suite** and no linter config for the Python code beyond inline `# pylint: disable=...` headers.

## Bot architecture

`franky.py` is the entry point: it loads the cogs listed in `init_extensions`, configures intents (`presences`, `members`, `message_content`), sets the `!`/mention prefix and owner, then runs two `@tasks.loop` background jobs — `check_timers` (every 60 min: expires temp mutes/bans and prunes JAC entries older than 14 days) and `war_channel` (every 15 min). On `on_ready` it starts the **cogwatch** hot-reloader watching `cogs/` and registers the persistent `Survivor` button view.

Cogs live in `cogs/`, each exporting `setup(bot)`:

- [cogs/events.py](cogs/events.py) — the automated moderation engine. `on_message` runs a filter pipeline (invite links, spam/scam/phishing, blacklisted words, Join-A-Clan 14-day dedup, message-link embedding); `on_member_join/ban/remove/update` post log embeds with **interactive button views** (undo timeout, unban, confirm-scam-ban) defined in `support.py`.
- [cogs/moderation.py](cogs/moderation.py) — prefix commands (`!mute`, `!ban`, `!tempban`, `!kick`, `!warn`, `!status`, `!delete`, …), gated by a `cog_check` on the mod role.
- [cogs/moderation_slash.py](cogs/moderation_slash.py) — the **same moderation features as slash commands** (`/mute`, `/ban`, …), registered with `guild_ids=[config.GUILD]`. Prefix and slash versions coexist; changes to one often belong in the other.
- [cogs/users.py](cogs/users.py) / [cogs/users-slash.py](cogs/users-slash.py) — public info commands (`roles`, `twitch`, `faq`, `me`, `rr`).
- [cogs/admin.py](cogs/admin.py) — owner-only (`@commands.is_owner()`) hidden commands: load/unload/reload extensions, `reconf` (hot-reload `config.py` and `support.py`), etc.
- [cogs/database.py](cogs/database.py) — the `Database` cog: MariaDB **connection-pool** wrapper (`POOL_CONFIG`, `_execute_query`). It is a stateless wrapper, so the code instantiates it in several places (module-level in `franky.py`, per-cog in `events.py`) — that is intentional and fine.
- `giveaway.py`, `poll.py`, `modalpoll.py` — present but **disabled** (commented out in `franky.py`'s `init_extensions`).

[support.py](support.py) holds shared helpers: the `discord.ui.View` button classes used by event embeds, the persistent `Survivor` role-button view, and `get_logger()` (rotating file logs under `logs/`).

[config.py](config.py) is **gitignored** and single-guild specific: it hardcodes all guild/role/channel IDs, embed colors, and the filter lists (`BLACKLIST`, `SCAMURLS`, `SCAMTEXT`, `INVITE_WHITELIST`, `INVITE_BANLIST`) plus command help strings. Porting the bot to another server means rewriting this file. `!reconf` reloads it without restarting.

## Data model

MariaDB tables (no ORM, no migration framework): `jac`, `timers`, `warn_user`, `warn_reasons`, `new_users`, `kill_board`. The schema is defined implicitly by the SQL in [cogs/database.py](cogs/database.py); the original `CREATE TABLE` statements and the one-time migration from the legacy Python `shelve` persistence live in [scripts/shelve2maria.py](scripts/shelve2maria.py). The `scripts/*.db` files are the old shelve dumps.

## Web UI

- **Backend** ([webui/backend/app.py](webui/backend/app.py)) — Flask. Discord **OAuth2** login (`/api/auth/discord/*`); authorization checks that the logged-in user holds a mod role in the guild via the bot token. Server-side sessions in **Redis**. A CRUD REST API under `/api/*` (jac, timers, warnings/kicks/bans "infractions", stats, new-users) operates directly on MariaDB. Serves the built SPA from the frontend `dist/`.
- **Frontend** (`webui/frontend/src/`) — React 19 + Vite + Tailwind. Components map to API resources (`InfractionManagement`, `JacManagement`, `TimerManagement`, `NewUsersManagement`); auth state via `AuthProvider`/`AuthContext`.

## Conventions & gotchas

- **py-cord, not discord.py.** The Docker build explicitly uninstalls `discord.py` and installs `py-cord`. Do not introduce discord.py-only APIs.
- **Timestamps are US/Central.** All persisted dates and timer comparisons use `tz_TX = pytz.timezone("US/Central")` with the format `"%b-%d-%Y %H:%M:%S"` (the community is US-based). Only `on_ready`'s console print uses Europe/Rome. Match the Central-time convention when touching timers or dates.
- **Cogs hot-reload on save via cogwatch — this means saving a file in `cogs/` edits production live** (see the critical warning at the top). The owner can also `!reload <cog>` or `!reconf`.
- Legacy/dead files to ignore: `database.old`, `webui/backend/oldapp.py`, `old_Dockerfile`, `scripts/*.db`.
- **git ownership:** on this unRAID host git may reject the repo with "dubious ownership"; fix once with `git config --global --add safe.directory /mnt/user/appdata/discord-bot/v4`.

## Testing & rollout

There is no automated test coverage, and this is a live single-guild production bot with irreversible moderation actions. Before deploying a change:

- Validate against a **separate test guild** (or a staged bot instance) rather than editing the production bot directly — update `config.py` IDs to point at the test guild.
- Manually exercise the affected path end-to-end (e.g. for a moderation change, run the command and confirm the DB row + log embed + button flow all behave).
- When a change touches the DB layer, verify **both** clients — the bot (`cogs/database.py`) and the web API (`webui/backend/app.py`) — still agree on the schema.
