# Review follow-ups: honeypot, duplicate logs, persistent buttons, async DB, web session

Follow-up of the full-repo code review (commit `161fb74`, branch
`dev/full-repo-code-review-683c3e`). The five findings that the review skipped,
with the decisions of the owner. Order of work is fixed by the owner: Task 1 → 5.

**Astra critique:** criteria 2 (cross-cutting: `cogs/`, `support.py`/`timers.py`,
`webui/backend/`), 3 (web auth session), 4 (live production bot, irreversible
moderation actions), 5 (6 tasks, 4 with chained `blockedBy`).

## Context and constraints

- Single-guild production bot (py-cord 2.8.1, Python 3.10), no test guild.
  `cogs/` hot-reloads in production on the unRAID host; this worktree is on a
  dev machine, so edits here are not live. Deploy needs a bot restart anyway
  (`support.py`, `timers.py`, `franky.py` are not hot-reloaded).
- No privileged intents: no member cache (`guild.fetch_member`), no message content.
- Two DB clients share MariaDB: the bot (`cogs/database.py`, connection pool
  `pool_size=5`, sync `mariadb` driver) and the web API (`webui/backend/app.py`).
- Tests: `python -m pytest -q tests` (174 passing at `161fb74`). `tests/conftest.py`
  stubs `config` and `cogs.database`; `real_db_module` fixture loads the real DB cog.
  CLAUDE.md requires a test for every handler or command touched.
- Verified in the installed py-cord 2.8.1: there is **no `DynamicItem`**, so a
  persistent button has a fixed `custom_id`; `bot.add_view(view)` without
  `message_id` matches that `custom_id` on any message. `tasks.Loop` does not
  retry `discord.HTTPException`. `asyncio.to_thread` exists (3.9+).
- The disabled cogs (`poll.py`, `modalpoll.py`, `giveaway.py`) and the views they
  use (`support.Confirm`, `support.StopPoll`, `support.BanButton`) are out of scope.

## Acceptance for every task

- Tests first (red), then code (green); full suite passes.
- Each task ends in one commit. No partial states in `cogs/`.
- No behaviour change outside the task's scope.

### Task 1: Honeypot review without message content

**Files:** `cogs/honeypot.py`, `tests/` (new `tests/test_honeypot.py` if none covers it).
**blockedBy:** none.

The bot cannot read `message.content` (no MESSAGE_CONTENT intent): the review
embed always shows "(no text)" and the purge log lines are empty.

- Remove the "Message" field from the review embed and from the completed embed.
- No "Message link" replacement: the non-autoban path deletes the message before
  the review. Keep the Channel and Author fields.
- `purge_user_messages`: log the count per channel only, not `msg.content`.
- Fix the docstrings that promise the content in the log file.

Tests: the review embed has no "Message" field; the purge does not log content.

### Task 2: No duplicate log embeds for the bot's own review timeouts and /ban

**Files:** `support.py`, `cogs/events.py`, `cogs/automod.py`, `cogs/honeypot.py`,
`cogs/moderation_slash.py`, tests.
**blockedBy:** Task 1 (same files: honeypot).

Every moderation action of the bot has the bot as the audit-log author, also
when a mod runs `/timeout`, `/rr` or `/ban`. So "skip the bot's own entries" is
narrowed to the cases that already have their own embed:

- Timeouts: `support.REVIEW_TIMEOUT_REASONS` holds the audit reasons of the
  review timeouts (automod scam review, honeypot non-autoban). `automod.py` and
  `honeypot.py` use these constants. `events.log_timeout` skips an entry when
  `payload.user_id == bot.user.id` **and** the reason is in that set.
  `/timeout`, `/rr` and AutoMod's own timeout action keep their log embed.
- Bans: `on_member_ban` stays the single ban log (it writes the DB row and holds
  the Unban button). `/ban` stops posting its "User ban issued!" embed in the log
  channel and passes `reason=f"{reason} (by {ctx.author})"` to `guild.ban`, so
  the ban embed and the DB reason name the mod. `/tempban` keeps its embed (it
  holds duration and end time) — out of scope.
- `log_timeout_removed` is unchanged (a release is real information).

Tests: bot-authored review timeout → no embed; bot-authored `/timeout` → embed;
mod-authored timeout → embed; `/ban` posts no log embed and passes the mod in the reason.

### Task 3: Persistent log buttons

**Files:** `support.py`, `cogs/events.py`, `cogs/automod.py`, `cogs/honeypot.py`, tests.
**blockedBy:** Task 2.

Today `on_member_ban`, `log_timeout`, `scam_review` and `honeypot_review_embed`
post a `View(timeout=None)` with auto-generated custom_ids and `await view.wait()`
forever: one task per unanswered embed stays in memory, and the buttons die on
restart or cog reload.

Design (no `DynamicItem` in py-cord 2.8.1):

- One persistent view class per action, fixed custom_ids:
  `lf:unban`, `lf:untimeout`, `lf:scam:ban`, `lf:scam:cancel`,
  `lf:honeypot:ban`, `lf:honeypot:release`.
- **State in the embed.** Every embed with one of these views carries:
  `User ID` (raw ID); for bans `Reason` = the exact text stored by `addBan`
  (`ban_entry.reason or "Ban: No reason Specified"` — today the embed shows the
  raw reason, which is `None` without a reason: fix it); for timeouts
  `Timeout until` = the ISO `new_value` of `communication_disabled_until` from
  the audit change (or the end set by the review timeout).
- **Relevance check before acting** (an old button must not revoke a newer sanction):
  - Unban: `guild.fetch_ban(user)`; `NotFound` → answer "not banned any more",
    no DB change. Ban reason different from the embed's `Reason` → answer
    "a newer ban replaced this one", no action.
  - Undo timeout / scam Cancel / honeypot Release: `guild.fetch_member`;
    `NotFound` → "user left"; `member.communication_disabled_until` different
    from `Timeout until` (or `None`) → "timeout already changed", no action.
  - Scam Ban / honeypot Ban: no relevance check (a mod decision); keep the
    existing mod-role exemption for the scam ban.
- **Per-message critical section.** The cog holds `self.review_locks`
  (message ID → `asyncio.Lock`) shared by all buttons of one message (Ban vs
  Cancel). The callback defers, takes the lock, then checks that the message
  is still open: re-fetch it (`channel.fetch_message`) and stop with "already
  handled" if it has no components. Locks are dropped after the message is
  closed.
- **Order and partial failure:** Discord action → edit the message to the
  "completed" embed with `view=None` (this closes it) → DB update. If the
  Discord action fails (other than the cases above), answer the error, keep the
  buttons. If the edit fails after the action, log it and answer the mod; the
  next press sees the state through the relevance check. If the DB update fails
  (`delBan`), log it and tell the mod to fix the counter in the dashboard: the
  message is already closed, so no retry can delete a second infraction.
- **Error mapping per action** (no blanket NotFound = success): ban
  `NotFound` (unknown user) = failure, never marked "Banned"; unban `NotFound`
  = not banned (see above); remove-timeout after `fetch_member` `NotFound` =
  user left.
- Only members with `config.MOD_ID` or `config.ADMIN_ID` can press: others get
  an ephemeral refusal (today anyone who sees the log channel can press).
- Registration: each cog registers its views in `on_ready` and in `__init__`
  when `bot.is_ready()` (the pattern of `cogs/jac.py`), so they survive restart
  and cogwatch reload. The views get the cog (for `self.database`, `self.bot`).
- The handlers no longer `await view.wait()`.
- Embeds already posted with the old non-persistent buttons stay dead: accepted,
  noted in the commit message.

Tests (real `discord.Embed` with the state fields): each button: right action,
DB call, edited embed, view removed; non-mod refused; concurrent presses on the
same message (Ban vs Cancel, Unban twice) act once; old Unban after a newer ban
with another reason does nothing; old Undo after a newer timeout does nothing;
ban without a reason → `delBan` gets "Ban: No reason Specified"; unban
`NotFound` → no DB change; DB error after unban → message closed, mod told,
no second `delBan`; edit error after action; views `is_persistent()` and
registered on `on_ready`; handlers return without waiting.

### Task 4: DB calls off the event loop

**Files:** `cogs/database.py`, `cogs/events.py`, `cogs/automod.py`, `cogs/jac.py`,
`cogs/moderation_slash.py`, `cogs/honeypot.py` (if Task 3 added DB use),
`timers.py`, `franky.py`, tests.
**blockedBy:** Task 3 (it rewrites the same handlers).

All `Database` methods are sync and block the gateway loop (39 call sites).

- Keep the sync implementation in `Database` (the web API is not affected).
- Add an async facade `AsyncDatabase(bot)` in `cogs/database.py`: every public
  method of `Database` is awaitable and runs in a worker thread. Explicit
  methods, not `__getattr__`, so a typo fails at import.
- **One limiter for the whole process.** Each cog and `franky.py` build their
  own `Database` today, all on the same named mariadb pool (which lives in the
  `mariadb` module and survives cog reloads). The limiter is an
  `asyncio.Semaphore(POOL_CONFIG['pool_size'])` stored on the bot
  (`bot.db_limiter`, created on first use with `getattr`), so every facade,
  also after a cogwatch reload of any cog, shares it.
- **Cancellation does not free capacity early.** The facade acquires the
  semaphore, starts the call with `loop.run_in_executor`, and releases the
  semaphore in the future's done callback (when the thread finishes), not in
  the awaiting coroutine. A cancelled await leaves the query running and the
  slot taken until it ends.
- Every cog and `timers.py`/`franky.py` use the facade and `await` each call.
- `jac.validate` and `check_jac` keep their logic; only the calls are awaited.
- The `Jac.publish` lock keeps serialising validate + store (an `asyncio.Lock`).
- Tests: the conftest stub returns an `AsyncMock`-based database; cog tests
  switch `MagicMock()` databases to `AsyncMock()`. Facade tests: the call runs
  in another thread; two facades on the same bot share one limit (with
  `pool_size` slots taken, a further call waits); a cancelled await keeps its
  slot until the thread ends; exceptions propagate.

### Task 5: Web dashboard re-checks the mod role

**Files:** `webui/backend/app.py`, `webui/frontend/src/` (new `api.js`,
`AuthProvider.jsx`, `Home.jsx`, `JacManagement.jsx`, `TimerManagement.jsx`,
`InfractionManagement.jsx`, `InfractionDetailModal.jsx`, `NewUsersManagement.jsx`),
tests.
**blockedBy:** none (independent of Tasks 1–4; can run in parallel).

`mod_required` trusts `session['is_authorized']` set at login; the session is
permanent and refreshed on each request, so a demoted mod keeps access.

Backend:
- Extract `fetch_member_roles(user_id)` (bot-token GET
  `/guilds/{guild}/members/{user}`), used by the OAuth callback and by the
  re-check. Returns the role set, `None` for 404 (not a member), raises a
  `TransientRoleCheckError` (with `retry_after` for 429) on other errors.
- Session keys: `roles_checked_at` (last successful check),
  `roles_retry_at` (no new attempt before this time).
- `mod_required` and `/api/auth/status`, through one function `ensure_mod()`:
  - session without `roles_checked_at` (sessions from before the deploy) →
    check now;
  - `now - roles_checked_at >= 15 min` and `now >= roles_retry_at` → check;
  - no mod role or 404 → `session.clear()`, 401;
  - transient error (network, 5xx, 429, 401/403 from Discord = bot token or
    permission problem): keep the session only while
    `now - roles_checked_at < 60 min` (maximum unverified window); set
    `roles_retry_at = now + max(Retry-After, 60 s)`; log a warning. Past the
    60 minutes → `session.clear()`, 401 (fail closed).
- The callback sets `roles_checked_at` at login.

Frontend:
- New `src/api.js` with `apiFetch(url, options)`: on 401 it calls the
  `logout` of `AuthContext` (through a handler that `AuthProvider` registers)
  and throws. Every component uses it, including `Home.jsx` (stats, search)
  and the POST/DELETE handlers that today show a generic error.
- `AuthProvider` polls `/api/auth/status` every 5 minutes while logged in, so
  an idle dashboard logs out within 15 + 5 minutes of the role removal.

Testability: `app.py` connects to Redis and validates env at import. The tests
import it with `redis.Redis` and the env stubbed through `monkeypatch` and use
the Flask test client with a dict-backed session (`SESSION_TYPE` overridden).

Tests (Flask test client, `fetch_member_roles` mocked): protected route and
`/api/auth/status` with role / without role / 404 / 429 with Retry-After /
5xx / network error; session without `roles_checked_at`; repeated transient
errors past 60 minutes → 401; no second Discord call before `roles_retry_at`;
callback sets the timestamp. Frontend: `npm run lint` and `npm run build`
(install dependencies first).

### Task 6: Verification and docs

**blockedBy:** Tasks 1–5.

- Full suite green; `py_compile` on `webui/backend/app.py`.
- Security review of Task 5 with the `security-auditor` agent.
- Astra critique (2026-10-29): REVISE, 2 blockers (button idempotency, per-process DB limiter); both resolved above. Its note on a missing `AGENTS.md` does not apply: `CLAUDE.md` is this repo's convention file.
- Update `CLAUDE.md`: persistent log buttons (custom_ids, `User ID` field), the
  async DB facade (call sites must `await`), the review-timeout reasons.
- Manual test list for the owner after deploy (no test guild): press each
  button type once (Unban, Undo, Scam Ban/Cancel, Honeypot Ban/Release), also
  after a bot restart; non-mod press refused; `/ban` single embed naming the
  mod; `/timeout` still logged; dashboard logout within 15 min after removing a
  test account's mod role.

## Rollback

Each task is one commit: `git revert` per task. Task 3 changes the button
format: embeds posted after deploy carry the new custom_ids, so reverting Task 3
makes those buttons dead (same as today's behaviour after a restart).

## Manual test list (before and right after the deploy)

There is no test guild: run these on production, right after the restart, with a test account.

Regression suite first: `python -m pytest -q tests` (all green), `cd webui/frontend && npm run build`.

1. **Restart, not hot reload.** Tasks 3 and 4 change `support.py`, `timers.py` and `franky.py`, which cogwatch does not reload. Restart the container.
2. **Old embeds.** Log embeds posted before the restart have dead buttons ("This interaction failed"). Handle those by hand.
3. **Unban.** Ban the test account with `/ban` (with a reason, then once without one). Check: one log embed only, with `Reason`, `User ID` and the mod name in the audit log. Press Unban: user unbanned, embed "User ban - canceled", buttons gone, ban counter decremented in the dashboard. Press as a non-mod: refused.
4. **Unban after restart.** Ban, restart the bot, press Unban on that embed: it works.
5. **Stale Unban.** Ban (reason A), unban by hand, ban again (reason B). Press Unban on the first embed: "A newer ban replaced this one", nothing changes.
6. **Undo timeout.** `/timeout` the test account. Press Undo: timeout removed, embed "User timeout - removed". Time out again, then with another length, press Undo on the first embed: refused.
7. **Double press.** Two mods press the same button at once: one action, the other gets "already handled".
8. **Scam review** (only once AutoMod is enforcing `scam`/`invites`): one review embed, no extra timeout log. Cancel removes the timeout; Ban bans with 12 h of messages deleted.
9. **Honeypot** (with `HONEYPOT_AUTOBAN = False`): one review embed, no extra timeout log. Release and Ban work.
10. **Async DB.** `/warn`, `/unwarn`, `/mute` with a duration, `/tempban`, `/timers`, `/kc`, `/jac post` and the hourly timer job behave as before. No "coroutine was never awaited" in `logs/`.
11. **Web UI.** Log in as a mod: works. Remove the mod role from a test mod: within 15 min (at the next request or the 5-min status poll) the dashboard logs out. Give the role back: login works again.
