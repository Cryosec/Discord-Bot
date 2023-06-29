# pylint: disable=F0401, W0702, W0703, W0105, W0613
import os
from dotenv import load_dotenv
import mariadb
from discord.ext import commands
import logging
from logging.handlers import RotatingFileHandler


#Setup module logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")

file_handler = RotatingFileHandler(
    filename=f"logs/{__name__}.log",
    mode="a",
    maxBytes=20000,
    backupCount=5,
    encoding="utf-8")
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

log.addHandler(file_handler)
log.addHandler(console_handler)

load_dotenv()
DB_USER = str(os.getenv("DB_USERNAME"))
DB_PASS = str(os.getenv("DB_PASSWORD"))
DB_HOST = str(os.getenv("DB_HOST"))
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = str(os.getenv("DB_NAME"))


class Database(commands.Cog):

    cur = None
    conn = None

    def __init__(self, bot):
        self.bot = bot

    # Database connection
    try:
        conn = mariadb.connect(
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME
        )
        # Set autoreconnect to avoid losing connection for inactivity
        conn.auto_reconnect = True
        print("Connection to database completed.")
    except mariadb.Error as db_error:
        log.exception("Error connecting to MariaDB platform: %s", db_error)

    # Get DB cursor
    cur = conn.cursor()


    ### JAC DATABASE ###
    def getJac(self):
        try:
            statement = "SELECT * FROM jac"
            self.cur.execute(statement)
            return self.cur.fetchall()
        except mariadb.Error as db_error:
            log.exception("Error retrieving JAC from DB: %s", db_error)

    def getJacByID(self, user_id: str):
        try:
            statement = "SELECT * FROM jac WHERE user_id=%s"
            data = (user_id,)
            self.cur.execute(statement, data)
            return self.cur.fetchall()
        except mariadb.Error as db_error:
            log.exception("Error retrieving JAC from DB: %s", db_error)

    def addJac(self, user_id: str, link: str, date: str):
        try:
            statement = "INSERT INTO jac (user_id, link, date) VALUES (%s, %s, %s)"
            data = (user_id, link, date)
            self.cur.execute(statement, data)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error adding new entry to JAC: %s", db_error)

    def delJac(self, user_id: str):
        try:
            statement = "DELETE FROM jac WHERE user_id=%s"
            data = (user_id, )
            self.cur.execute(statement, data)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error deleting element from JAC table: %s", db_error)

    def getLink(self, link: str):
        try:
            statement = "SELECT user_id, link FROM jac WHERE link=%s"
            data = (link, )
            self.cur.execute(statement, data)
            return self.cur.fetchall()
        except mariadb.Error as db_error:
            log.exception("Error retrieving elements from JAC: %s", db_error)

    ### TIMERS DATABASE ###
    def addTimerMute(self, user_id: str, endMute: str):
        try:
            statement = """INSERT INTO timers (user_id, ban, mute, endBan, endMute)
            VALUES (%s, false, true, '', %s)
            ON DUPLICATE KEY UPDATE mute=true, endMute=%s"""
            data = (user_id, endMute, endMute)
            self.cur.execute(statement, data)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error adding mute timer: %s", db_error)

    def addTimerBan(self, user_id: str, endBan: str):
        try:
            statement = """INSERT INTO timers (user_id, ban, mute, endBan, endMute)
            VALUES (%s, true, false, %s, '')
            ON DUPLICATE KEY UPDATE ban=true, endBan=%s"""
            data = (user_id, endBan, endBan)
            self.cur.execute(statement, data)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error adding mute timer: %s", db_error)

    def getTimers(self):
        try:
            statement = "SELECT * FROM timers"
            self.cur.execute(statement)
            return self.cur.fetchall()
        except mariadb.Error as db_error:
            log.exception("Error retrieving Timers from DB: %s", db_error)

    def delTimer(self, user_id):
        # Deleting a row with both ban and mute could lead to removing all timers for user
        try:
            statement = "DELETE FROM timers WHERE user_id=%s"
            data = (user_id, )
            self.cur.execute(statement, data)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error deleting member from timers DB: %s", db_error)

    ### WARNINGS DATABASE ###
    def getWarnUsers(self):
        try:
            statement = "SELECT * FROM warn_user"
            self.cur.execute(statement)
            return self.cur.fetchall()
        except mariadb.Error as db_error:
            log.exception("Error retrieving warn_users from DB: %s", db_error)

    def getWarnUserByID(self, user_id: str):
        try:
            statement = "SELECT * FROM warn_user WHERE user_id=%s"
            data = (user_id,)
            self.cur.execute(statement, data)
            return self.cur.fetchall()
        except mariadb.Error as db_error:
            log.exception("Error retrieving warn_users from DB: %s", db_error)

    def getWarnReasons(self, user_id: str):
        try:
            statement = "SELECT reason FROM warn_reasons WHERE user_id=%s"
            data = (user_id,)
            self.cur.execute(statement, data)
            # Return only a list of reasons, no need for tuples
            tuples = self.cur.fetchall()
            values = []
            for k in tuples:
                values.append(k[0])
            return values
        except mariadb.Error as db_error:
            log.exception("Error retrieving warning reasons for user: %s", db_error)

    def getWarnCount(self, user_id: str, reason: str):
        try:
            statement = "SELECT * FROM warn_reasons WHERE reason=%s AND user_id=%s"
            data = (reason, user_id)
            self.cur.execute(statement, data)
            return self.cur.rowcount

        except mariadb.Error as db_error:
            log.exception("Error retrieving warning count for user: %s", db_error)

    def addWarning(self, user_id: str, tag:str, reason: str):
        try:
            # this is slow - find a better way
            statement = "SELECT * FROM warn_user WHERE user_id=%s"
            data = (user_id,)
            self.cur.execute(statement, data)

            if self.cur.rowcount >= 1:
                statement = "UPDATE warn_user SET warnings=warnings+1, tag=%s WHERE user_id=%s"
                data = (tag, user_id)
                self.cur.execute(statement, data)

                statement2 = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s,%s)"
                data2 = (user_id, reason)
                self.cur.execute(statement2, data2)
            else:
                statement = "INSERT INTO warn_user (user_id, warnings, kicks, bans, tag) VALUES (%s,1,0,0,%s)"
                data = (user_id, tag)
                self.cur.execute(statement, data)

                statement2 = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s,%s)"
                data2 = (user_id, reason)
                self.cur.execute(statement2, data2)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error adding warning to user in DB: %s", db_error)

    def delWarning(self, user_id: str, reason: str):
        try:
            statement = """DELETE FROM warn_reasons WHERE user_id=%s AND reason=%s
                ORDER BY reason DESC LIMIT 1"""
            data = (user_id, reason)
            self.cur.execute(statement, data)

            statement2 = "UPDATE warn_user SET warnings=GREATEST(warnings-1, 0) WHERE user_id=%s"
            data2 = (user_id,)
            self.cur.execute(statement2, data2)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception('Error deleting reason from table: %s', db_error)


    ### KICKS DATABASE ###
    def addKick(self, user_id: str, tag:str, reason: str):
        try:
            # this is slow - find a better way
            statement = "SELECT * FROM warn_user WHERE user_id=%s"
            data = (user_id,)
            self.cur.execute(statement, data)

            if self.cur.rowcount >= 1:
                statement = "UPDATE warn_user SET kicks=kicks+1, tag=%s WHERE user_id=%s"
                data = (tag, user_id)
                self.cur.execute(statement, data)

                statement2 = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s,%s)"
                data2 = (user_id, reason)
                self.cur.execute(statement2, data2)
            else:
                statement = "INSERT INTO warn_user (user_id, warnings, kicks, bans, tag) VALUES (%s,0,1,0,%s)"
                data = (user_id, tag)
                self.cur.execute(statement, data)

                statement2 = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s,%s)"
                data2 = (user_id, reason)
                self.cur.execute(statement2, data2)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error adding warning to user in DB: %s", db_error)

    def delKick(self, user_id: str, reason: str):
        try:
            statement = """DELETE FROM warn_reasons WHERE user_id=%s AND reason=%s
                ORDER BY reason DESC LIMIT 1"""
            data = (user_id, reason)
            self.cur.execute(statement, data)

            statement2 = "UPDATE warn_user SET kicks=GREATEST(kicks-1, 0) WHERE user_id=%s"
            data2 = (user_id,)
            self.cur.execute(statement2, data2)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception('Error deleting reason from table: %s', db_error)

    ### BANS DATABASE ###
    def addBan(self, user_id: str, tag:str, reason: str):
        try:
            # this is slow - find a better way
            statement = "SELECT * FROM warn_user WHERE user_id=%s"
            data = (user_id,)
            self.cur.execute(statement, data)

            if self.cur.rowcount >= 1:
                statement = "UPDATE warn_user SET bans=bans+1, tag=%s WHERE user_id=%s"
                data = (tag, user_id)
                self.cur.execute(statement, data)

                statement2 = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s,%s)"
                data2 = (user_id, reason)
                self.cur.execute(statement2, data2)
            else:
                statement = "INSERT INTO warn_user (user_id, warnings, kicks, bans, tag) VALUES (%s,0,0,1,%s)"
                data = (user_id, tag)
                self.cur.execute(statement, data)

                statement2 = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s,%s)"
                data2 = (user_id, reason)
                self.cur.execute(statement2, data2)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception("Error adding warning to user in DB: %s", db_error)

    def delBan(self, user_id: str, reason: str):
        try:
            statement = """DELETE FROM warn_reasons WHERE user_id=%s AND reason=%s
                ORDER BY reason DESC LIMIT 1"""
            data = (user_id, reason)
            self.cur.execute(statement, data)

            statement2 = "UPDATE warn_user SET bans = GREATEST(bans-1, 0) WHERE user_id=%s"
            data2 = (user_id,)
            self.cur.execute(statement2, data2)

            self.conn.commit()
        except mariadb.Error as db_error:
            log.exception('Error deleting reason from table: %s', db_error)



def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Database(bot))