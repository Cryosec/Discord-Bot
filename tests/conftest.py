"""Test setup: stubs for the gitignored config.py and for the database cog.

config.py is gitignored, so supply a stub when it is missing. cogs.database
needs the mariadb driver and DB_* variables (it calls sys.exit without them).
The real_db_module fixture loads the real cogs/database.py with a fake driver.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

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
sys.modules.setdefault("cogs.database", _db_stub)
