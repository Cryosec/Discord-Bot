"""Test setup: stubs for the gitignored config.py and for the database cog.

config.py is gitignored, so supply a stub when it is missing. cogs.database
needs the mariadb driver and DB_* variables (it calls sys.exit without them).
The real_db_module fixture loads the real cogs/database.py with a fake driver.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

DB_FILE = Path(__file__).resolve().parents[1] / "cogs" / "database.py"


class FakeDbError(Exception):
    def __init__(self, msg="", errno=None):
        super().__init__(msg)
        self.errno = errno


@pytest.fixture
def real_db_module(monkeypatch):
    """The real cogs/database.py, with a fake mariadb module (mariadb.connect is a MagicMock)."""
    fake = types.ModuleType("mariadb")
    fake.Error = FakeDbError
    fake.connect = MagicMock()
    monkeypatch.setitem(sys.modules, "mariadb", fake)
    # No real .env: the fixture sets the DB_* variables
    monkeypatch.setitem(sys.modules, "dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
    for key, value in {"DB_USERNAME": "u", "DB_PASSWORD": "p", "DB_HOST": "h",
                       "DB_PORT": "3306", "DB_NAME": "n"}.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("real_cogs_database", DB_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_LISTS = {
    "BLACKLIST", "SCAMURLS", "SCAMTEXT", "INVITE_WHITELIST", "INVITE_BANLIST",
    "NSFW", "INSULTS", "WEIRD_MESSAGES",
}


def _stub_value(name):
    """Values for the config names that a test does not set itself."""
    if name.startswith("__"):
        raise AttributeError(name)
    if name in _LISTS:
        return []
    if name.endswith(("_ID", "_CHAN")) or name == "GUILD":
        return 1000
    if name in {"RED", "GREEN", "YELLOW", "BLUE", "PURPLE", "ORANGE"}:
        return 0
    return "stub"


try:
    import config  # noqa: F401
except ImportError:
    stub = types.ModuleType("config")
    stub.RED = stub.GREEN = stub.YELLOW = 0
    stub.LOG_CHAN = 0
    stub.HONEYPOT_AUTOBAN = False
    stub.__getattr__ = _stub_value
    sys.modules["config"] = stub

_db_stub = types.ModuleType("cogs.database")
_db_stub.Database = lambda bot: MagicMock()
_db_stub.AsyncDatabase = lambda bot: AsyncMock()
sys.modules.setdefault("cogs.database", _db_stub)


@pytest.fixture
def make_press():
    """Build the interaction of a persistent-button press on a log message.

    `build(guild, embed, mod=True)` returns an object with `.interaction`
    and `.message` (the message that `channel.fetch_message` returns: its
    `components` become empty after `edit`, as for a closed Discord message).
    `click(make_view, custom_id, *interactions)` builds the view inside the loop and runs the callbacks of one button,
    all together (concurrent presses).
    """
    import asyncio
    import config

    def build(guild, embed, mod=True):
        message = MagicMock()
        message.id = 4242
        message.embeds = [embed]
        message.components = [object()]

        async def edit(**kwargs):
            if kwargs.get("view") is None:
                message.components = []

        message.edit = AsyncMock(side_effect=edit)
        role = MagicMock()
        role.id = config.MOD_ID if mod else -1
        interaction = MagicMock()
        interaction.user.roles = [role]
        interaction.user.__str__ = lambda self: "mod#1"
        interaction.guild = guild
        interaction.message.id = message.id

        async def fetch(_message_id):
            await asyncio.sleep(0)  # yield, so concurrent presses really interleave
            return message

        interaction.channel.fetch_message = AsyncMock(side_effect=fetch)
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()
        return types.SimpleNamespace(interaction=interaction, message=message)

    def click(make_view, custom_id, *interactions):
        async def run():
            view = make_view()  # a View needs the running loop
            item = next(i for i in view.children if i.custom_id == custom_id)
            await asyncio.gather(*(item.callback(i) for i in interactions))

        asyncio.run(run())

    def answers(interaction):
        """Texts sent to the mod after the press (follow-ups and refusals)."""
        calls = (interaction.followup.send.await_args_list
                 + interaction.response.send_message.await_args_list)
        return [c.args[0] for c in calls]

    return types.SimpleNamespace(build=build, click=click, answers=answers)

