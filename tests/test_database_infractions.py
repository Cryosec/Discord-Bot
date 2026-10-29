"""Tests for the warning/kick/ban methods of the real cogs/database.py, with a fake driver.

warn_reasons holds the reasons of warnings, kicks and bans; warn_user holds the
counters. A delete removes one reason row and decrements one counter, like the
web API (webui/backend/app.py).
"""
from unittest.mock import MagicMock

import pytest

from conftest import FakeDbError


class FakeCursor:
    """Records the statements; rowcount comes from a list, 1 by default."""

    def __init__(self, rowcounts=()):
        self.statements = []
        self.rowcounts = list(rowcounts)
        self.rowcount = 0

    def execute(self, statement, params=None):
        self.statements.append((" ".join(statement.split()), params))
        result = self.rowcounts.pop(0) if self.rowcounts else 1
        if isinstance(result, Exception):
            raise result
        self.rowcount = result

    def close(self):
        pass


@pytest.fixture
def db(real_db_module):
    def make(*rowcounts):
        cursor = FakeCursor(rowcounts)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        real_db_module.mariadb.connect.return_value = conn
        return real_db_module.Database(MagicMock()), cursor, conn
    return make


def test_del_ban_deletes_by_reason_not_by_id(db):
    database, cursor, conn = db()
    assert database.delBan("5", "Spam") == 1
    (delete, delete_params), (update, update_params) = cursor.statements
    assert "WHERE user_id=%s AND reason=%s" in delete and " id=%s" not in delete
    assert delete_params == ("5", "Spam")
    assert "bans = GREATEST(bans - 1, 0)" in update and update_params == ("5",)
    conn.commit.assert_called_once()


@pytest.mark.parametrize("method, counter", [
    ("delWarning", "warnings"), ("delKick", "kicks"), ("delBan", "bans")])
def test_delete_removes_one_row_only(db, method, counter):
    """The same reason can be stored more than once: remove the newest one."""
    database, cursor, _ = db()
    getattr(database, method)("5", "Same reason")
    delete, update = (s for s, _ in cursor.statements)
    assert delete.endswith("ORDER BY id DESC LIMIT 1")
    assert f"{counter} = GREATEST({counter} - 1, 0)" in update


def test_del_warning_without_reason_removes_the_newest_row_of_the_user(db):
    database, cursor, _ = db()
    database.delWarning("5")
    (delete, params), _ = cursor.statements
    assert delete == "DELETE FROM warn_reasons WHERE user_id=%s ORDER BY id DESC LIMIT 1"
    assert params == ("5",)


def test_delete_of_a_missing_reason_keeps_the_counter(db):
    database, cursor, _ = db(0)
    assert database.delWarning("5", "nope") == 0
    assert len(cursor.statements) == 1  # no UPDATE of warn_user


@pytest.mark.parametrize("method, counter", [
    ("addWarning", "warnings"), ("addKick", "kicks"), ("addBan", "bans")])
def test_add_increments_one_counter_and_stores_the_reason(db, method, counter):
    database, cursor, conn = db()
    getattr(database, method)("5", "tag", "reason")
    (upsert, upsert_params), (insert, insert_params) = cursor.statements
    initial = {"warnings": "0", "kicks": "0", "bans": "0", counter: "1"}
    assert f"VALUES (%s, {initial['warnings']}, {initial['kicks']}, {initial['bans']}, %s)" in upsert
    assert f"{counter} = {counter} + 1" in upsert and upsert_params == ("5", "tag")
    assert insert == "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"
    assert insert_params == ("5", "reason")
    conn.commit.assert_called_once()


def test_errors_roll_back_and_are_raised(db):
    database, _, conn = db(1, FakeDbError("boom"))
    with pytest.raises(FakeDbError):
        database.addKick("5", "tag", "reason")
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
