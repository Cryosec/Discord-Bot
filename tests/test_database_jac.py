"""Tests for the jac methods of the real cogs/database.py, with a fake mariadb driver.

The guild_id column comes from migrations/2026-10-29_jac_guild_id.sql. The bot
must keep working if it is deployed before the migration runs.
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
def database(monkeypatch):
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
    db = module.Database(MagicMock())
    db._execute_query = MagicMock(return_value=1)
    return db


def _statements(db):
    return [" ".join(c.args[0].split()) for c in db._execute_query.call_args_list]


def test_add_jac_stores_the_server_id(database):
    database.addJac("5", "https://discord.gg/abc", "Oct-29-2026 10:00:00", guild_id="1234")
    (statement,) = _statements(database)
    assert "guild_id" in statement
    assert database._execute_query.call_args.kwargs["params"] == (
        "5", "https://discord.gg/abc", "Oct-29-2026 10:00:00", "1234")


def test_add_jac_without_server_id_keeps_the_old_insert(database):
    database.addJac("5", "Not available", "Oct-29-2026 10:00:00")
    (statement,) = _statements(database)
    assert "guild_id" not in statement


def test_add_jac_before_the_migration_falls_back(database):
    database._execute_query.side_effect = [FakeDbError("Unknown column 'guild_id'", errno=1054), 1]
    database.addJac("5", "https://discord.gg/abc", "Oct-29-2026 10:00:00", guild_id="1234")
    first, second = _statements(database)
    assert "guild_id" in first and "guild_id" not in second


def test_add_jac_other_db_errors_are_raised(database):
    database._execute_query.side_effect = FakeDbError("Lost connection", errno=2013)
    with pytest.raises(FakeDbError):
        database.addJac("5", "https://discord.gg/abc", "Oct-29-2026 10:00:00", guild_id="1234")


def test_get_jac_works_with_and_without_the_column(database):
    database.getJac()
    (statement,) = _statements(database)
    assert statement.startswith("SELECT * FROM jac")
