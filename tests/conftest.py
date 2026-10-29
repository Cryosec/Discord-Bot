"""Test setup: stubs for the gitignored config.py and for the database cog.

config.py is gitignored, so supply a stub when it is missing. cogs.database
needs the mariadb driver and DB_* variables (it calls sys.exit without them).
"""
import sys
import types
from unittest.mock import MagicMock

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
