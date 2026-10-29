"""Tests for cogs/jac.py: the /jac post modal, its validation and the persistent button."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from cogs import jac

GUILD, CLAN_CHAN, USER = 99, 13, 5
CODE = "abcDEF12"


@pytest.fixture
def env(monkeypatch):
    for key, value in {
        "GUILD": GUILD, "CLAN_CHAN": CLAN_CHAN, "MOD_ID": 11, "ADMIN_ID": 12,
        "INVITE_BANLIST": ["discord.gg/badclan"], "SCAMURLS": ["dlscord-gift.com"],
        "SCAMTEXT": ["free nitro"], "BLACKLIST": ["badword"], "GREEN": 0, "FOOTER": "f",
    }.items():
        monkeypatch.setattr(jac.config, key, value, raising=False)

    channel = MagicMock()
    sent = MagicMock(jump_url="https://discord.com/channels/99/13/1")
    channel.send = AsyncMock(return_value=sent)
    invite = MagicMock()
    invite.guild.id = 1234
    bot = MagicMock()
    bot.is_ready.return_value = False
    bot.get_channel.side_effect = {CLAN_CHAN: channel}.get
    bot.fetch_invite = AsyncMock(return_value=invite)

    cog = jac.Jac(bot)
    cog.database = MagicMock()
    cog.database.getJac.return_value = []

    interaction = MagicMock()
    interaction.user.id = USER
    interaction.user.mention = f"<@{USER}>"
    interaction.response.defer = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup.send = AsyncMock()

    def submit(link=f"https://discord.gg/{CODE}", name="Wolves", description="Chill PvE clan",
               platforms=("PC",)):
        post = jac.JacPost(name=name, link=link, platforms=list(platforms), description=description)
        asyncio.run(cog.submit(interaction, post))

    return MagicMock(cog=cog, bot=bot, channel=channel, interaction=interaction, submit=submit)


def _recent():
    return (datetime.now(jac.tz_TX) - timedelta(days=1)).strftime(jac.TIME_FORMAT)


def _reply(env):
    call = env.interaction.followup.send.await_args
    assert call.kwargs.get("ephemeral") is True
    return call.args[0] if call.args else call.kwargs["content"]


def _rejected(env, *words):
    reply = _reply(env).lower()
    for word in words:
        assert word in reply
    env.channel.send.assert_not_awaited()
    env.cog.database.addJac.assert_not_called()


@pytest.mark.parametrize("link", [
    f"discord.gg/{CODE}", f"https://discord.gg/{CODE}", f"https://discord.gg/{CODE}/",
    f"https://discord.com/invite/{CODE}", f"discordapp.com/invite/{CODE}", f"  https://www.discord.gg/{CODE} ",
])
def test_parse_invite_accepts_invite_forms(link):
    assert jac.parse_invite(link) == CODE


@pytest.mark.parametrize("link", [
    "", "discord.gg/", "hello", f"https://evil.com/discord.gg/{CODE}",
    "https://discord.com/channels/1/2/3", f"https://discord.gg/{CODE} extra",
])
def test_parse_invite_rejects_other_text(link):
    assert jac.parse_invite(link) is None


def test_valid_post_is_published_and_stored(env):
    env.submit()
    embed = env.channel.send.await_args.kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert embed.title == "Wolves"
    assert embed.description == "Chill PvE clan"
    assert fields["Invite"] == f"https://discord.gg/{CODE}"
    assert fields["Platform"] == "PC"
    assert fields["Posted by"] == f"<@{USER}>"
    user_id, link, date = env.cog.database.addJac.call_args.args
    assert (user_id, link) == (str(USER), f"https://discord.gg/{CODE}")
    datetime.strptime(date, jac.TIME_FORMAT)
    assert "posted" in _reply(env).lower()
    env.interaction.response.defer.assert_awaited_once_with(ephemeral=True)


def test_link_that_is_not_an_invite_is_rejected(env):
    env.submit(link="https://example.com")
    _rejected(env, "invite")
    env.bot.fetch_invite.assert_not_awaited()


def test_banlisted_invite_is_rejected(env):
    env.submit(link="https://discord.gg/badclan")
    _rejected(env, "not allowed")


def test_scam_text_in_any_field_is_rejected(env):
    env.submit(description="get FREE NITRO here")
    _rejected(env, "not allowed")


def test_blacklisted_word_is_rejected(env):
    env.submit(name="badword clan")
    _rejected(env, "not allowed")


def test_author_can_post_once_in_14_days(env):
    posted = datetime.now(jac.tz_TX).replace(tzinfo=None, microsecond=0) - timedelta(days=1)
    env.cog.database.getJac.return_value = [
        {"user_id": str(USER), "link": "https://discord.gg/other", "date": posted.strftime(jac.TIME_FORMAT)}]
    env.submit()
    _rejected(env, "14 days", (posted + timedelta(days=14)).strftime(jac.TIME_FORMAT).lower())


def test_same_invite_from_another_user_in_14_days_is_rejected(env):
    # Rows written by the old check_jac have other link formats
    env.cog.database.getJac.return_value = [
        {"user_id": "77", "link": f"discord.gg/{CODE}", "date": _recent()}]
    env.submit(link=f"https://discord.com/invite/{CODE}")
    _rejected(env, "already")


def test_old_rows_without_link_do_not_block_other_users(env):
    env.cog.database.getJac.return_value = [
        {"user_id": "77", "link": "Not available", "date": _recent()}]
    env.submit()
    env.channel.send.assert_awaited_once()


def test_expired_invite_is_rejected(env):
    env.bot.fetch_invite.side_effect = discord.NotFound(MagicMock(status=404), "Unknown Invite")
    env.submit()
    _rejected(env, "expired")


def test_invite_to_this_server_is_rejected(env):
    env.bot.fetch_invite.return_value.guild.id = GUILD
    env.submit()
    _rejected(env, "this server")


def test_no_platform_selected(env):
    env.submit(platforms=())
    fields = {f.name: f.value for f in env.channel.send.await_args.kwargs["embed"].fields}
    assert fields["Platform"] == "Not specified"


# --- Modal and persistent view ------------------------------------------------

def _modal_payload(modal, name, link, platforms, description):
    """MODAL_SUBMIT components as Discord sends them: one Label (type 18) per field."""
    def text(item, value):
        return {"type": 18, "component": {"type": 4, "custom_id": item.custom_id, "value": value}}

    labels = [child.item for child in modal.children]
    return [
        text(labels[0], name),
        text(labels[1], link),
        {"type": 18, "component": {"type": 3, "custom_id": labels[2].custom_id, "values": platforms}},
        text(labels[3], description),
    ]


def test_modal_submit_passes_the_fields_to_submit(env):
    async def run():
        modal = jac.JacPostModal(env.cog)
        assert all(isinstance(c, discord.ui.Label) for c in modal.children)
        env.cog.submit = AsyncMock()
        modal._refresh(env.interaction, _modal_payload(
            modal, "Wolves", f"discord.gg/{CODE}", ["PC", "Xbox"], "desc"))
        await modal.callback(env.interaction)
        return env.cog.submit.await_args.args

    interaction, post = asyncio.run(run())
    assert interaction is env.interaction
    assert post == jac.JacPost("Wolves", f"discord.gg/{CODE}", ["PC", "Xbox"], "desc")


def test_button_view_is_persistent_and_registered_on_ready(env):
    asyncio.run(env.cog.on_ready())
    view = env.bot.add_view.call_args.args[0]
    assert view.is_persistent()
    assert [c.custom_id for c in view.children] == [jac.BUTTON_ID]


def test_button_opens_the_modal(env):
    async def run():
        view = jac.JacPostView(env.cog)
        await view.children[0].callback(env.interaction)

    asyncio.run(run())
    assert isinstance(env.interaction.response.send_modal.await_args.args[0], jac.JacPostModal)


def test_slash_group_has_public_post_and_mod_info(env):
    group = next(c for c in env.cog.get_commands() if c.name == "jac")
    assert {c.name for c in group.subcommands} == {"post", "info"}
    assert group.default_member_permissions is None  # /jac post is for everyone


def test_jac_post_command_opens_the_modal(env):
    ctx = MagicMock()
    ctx.send_modal = AsyncMock()
    post = next(c for c in env.cog.jac.subcommands if c.name == "post")

    async def run():
        await post.callback(env.cog, ctx)

    asyncio.run(run())
    assert isinstance(ctx.send_modal.await_args.args[0], jac.JacPostModal)


# --- Review fixes ---------------------------------------------------------------

@pytest.mark.parametrize("link", [f"Discord.GG/{CODE}", f"https://discord.gg/{CODE}?event=123"])
def test_parse_invite_more_forms(link):
    assert jac.parse_invite(link) == CODE


def test_banlist_ignores_case_and_host_form(env, monkeypatch):
    monkeypatch.setattr(jac.config, "INVITE_BANLIST", ["discord.gg/BadClan"], raising=False)
    env.submit(link="https://discord.com/invite/badclan")
    _rejected(env, "not allowed")


def test_dedup_ignores_case(env):
    env.cog.database.getJac.return_value = [
        {"user_id": "77", "link": "https://discord.gg/wolves", "date": _recent()}]
    env.submit(link="https://discord.gg/Wolves")
    _rejected(env, "already")


@pytest.mark.parametrize("text", [
    "join discord.gg/other", "see https://evil.example", "[free](http://x.y)", "www.example.com"])
def test_links_in_name_or_description_are_rejected(env, text):
    env.submit(description=text)
    _rejected(env, "link")


def test_blacklist_matches_whole_words_only(env):
    env.submit(description="we are badwordless")
    env.channel.send.assert_awaited_once()


def test_rows_older_than_14_days_do_not_block(env):
    old = (datetime.now(jac.tz_TX) - timedelta(days=15)).strftime(jac.TIME_FORMAT)
    env.cog.database.getJac.return_value = [
        {"user_id": str(USER), "link": f"https://discord.gg/{CODE}", "date": old}]
    env.submit()
    env.channel.send.assert_awaited_once()


def test_uncached_channel_is_fetched(env):
    env.bot.get_channel.side_effect = None
    env.bot.get_channel.return_value = None
    env.bot.fetch_channel = AsyncMock(return_value=env.channel)
    env.submit()
    env.channel.send.assert_awaited_once()


@pytest.mark.parametrize("failure", ["db", "invite_http", "send"])
def test_unexpected_errors_still_answer_the_user(env, failure):
    if failure == "db":
        env.cog.database.getJac.side_effect = RuntimeError("pool exhausted")
    elif failure == "invite_http":
        env.bot.fetch_invite.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    else:
        env.channel.send.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    env.submit()
    assert "try again later" in _reply(env).lower()
    env.cog.database.addJac.assert_not_called()


def test_concurrent_posts_by_the_same_user_publish_once(env):
    rows = []
    env.cog.database.getJac.side_effect = lambda: list(rows)
    env.cog.database.addJac.side_effect = lambda u, l, d: rows.append(
        {"user_id": u, "link": l, "date": d})

    async def slow_invite(code):
        await asyncio.sleep(0.01)
        return env.bot.fetch_invite.return_value

    env.bot.fetch_invite.side_effect = slow_invite

    async def run():
        post = jac.JacPost("Wolves", f"https://discord.gg/{CODE}", ["PC"], "desc")
        await asyncio.gather(env.cog.submit(env.interaction, post), env.cog.submit(env.interaction, post))

    asyncio.run(run())
    assert env.channel.send.await_count == 1


def test_modal_with_no_platform_selected(env):
    async def run():
        modal = jac.JacPostModal(env.cog)
        env.cog.submit = AsyncMock()
        payload = _modal_payload(modal, "Wolves", f"discord.gg/{CODE}", [], "desc")
        del payload[2]["component"]["values"]
        modal._refresh(env.interaction, payload)
        await modal.callback(env.interaction)
        return env.cog.submit.await_args.args[1], modal.timeout

    post, timeout = asyncio.run(run())
    assert post.platforms == []
    assert timeout is not None  # dismissed modals must leave the ModalStore


def test_non_mod_gets_an_answer_for_jac_info(env):
    ctx = MagicMock(spec=discord.ApplicationContext)
    ctx.respond = AsyncMock()
    asyncio.run(env.cog.cog_command_error(ctx, commands.MissingAnyRole([11, 12])))
    assert ctx.respond.await_args.kwargs["ephemeral"] is True


def test_jacsetup_posts_and_pins_the_button(env):
    message = MagicMock()
    message.pin = AsyncMock()
    env.channel.send.return_value = message
    env.bot.fetch_channel = AsyncMock(return_value=env.channel)

    async def run():
        await env.cog.jac_setup.callback(env.cog, MagicMock())

    asyncio.run(run())
    assert isinstance(env.channel.send.await_args.kwargs["view"], jac.JacPostView)
    message.pin.assert_awaited_once()
