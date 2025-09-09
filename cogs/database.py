# pylint: disable=F0401, W0702, W0703, W0105, W0613, W1203
import os
import sys # For sys.exit on critical errors
from dotenv import load_dotenv
import mariadb
from discord.ext import commands
import logging
from logging.handlers import RotatingFileHandler

# --- Logging Setup ---
log = logging.getLogger(__name__)
log.setLevel(logging.INFO) # Or DEBUG for more verbose pool info
log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")

# Ensure logs directory exists
log_dir = "logs"
if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir)
    except OSError as e:
        # Use root logger temporarily if module logger fails early
        logging.basicConfig(level=logging.ERROR)
        logging.critical(f"Failed to create log directory {log_dir}: {e}")
        sys.exit("Error: Could not create log directory.")

file_handler = RotatingFileHandler(
    filename=os.path.join(log_dir, f"{__name__}.log"),
    mode="a",
    maxBytes=20000,
    backupCount=5,
    encoding="utf-8")
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

log.addHandler(file_handler)
log.addHandler(console_handler)

# --- Load Environment Variables ---
load_dotenv()
DB_USER = os.getenv("DB_USERNAME")
DB_PASS = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT_STR = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# --- Validate DB Configuration ---
if not all([DB_USER, DB_PASS, DB_HOST, DB_PORT_STR, DB_NAME]):
    log.critical("Missing one or more database environment variables (DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)")
    sys.exit("Error: Missing database configuration in .env file.")

try:
    DB_PORT = int(DB_PORT_STR)
except ValueError:
    log.critical(f"Invalid DB_PORT value: '{DB_PORT_STR}'. Must be an integer.")
    sys.exit("Error: Invalid DB_PORT.")

# --- Connection Pool Configuration ---
# Stored globally for access by the Database class instance
# Adjust pool_size based on expected concurrent DB operations from the bot
POOL_CONFIG = {
    'user': DB_USER,
    'password': DB_PASS,
    'host': DB_HOST,
    'port': DB_PORT,
    'database': DB_NAME,
    'pool_name': 'discord_bot_pool', # Name the pool
    'pool_size': 5, # Start with 5, adjust as needed
    'autocommit': False # Explicitly manage commits
    # 'pool_reset_session': True # Optional: Reset session variables when connection is returned
}

# --- Database Class ---
class Database(commands.Cog):

    # REMOVED: Module/Class level conn and cur variables
    # REMOVED: Initial connection attempt here

    def __init__(self, bot):
        self.bot = bot
        # You could potentially test the pool connection here once if desired
        # self._test_pool_connection()
        log.info("Database Cog initialized, using connection pool '%s'", POOL_CONFIG['pool_name'])

    def _get_connection(self):
        """Gets a connection from the pool."""
        try:
            # The connector handles getting a connection from the named pool
            # using the configuration provided when the pool was likely first implicitly created.
            # It's important that mariadb.connect is called with these pool args somewhere,
            # often just implicitly by the first request for a pooled connection.
            # For safety, we can pass the config each time, though it should reuse the named pool.
            conn = mariadb.connect(**POOL_CONFIG)
            # log.debug("Acquired connection from pool '%s'.", POOL_CONFIG['pool_name'])
            return conn
        except mariadb.Error as e:
            log.error(f"Error getting connection from pool '{POOL_CONFIG['pool_name']}': {e}", exc_info=True)
            raise # Re-raise the exception to be handled by the calling method

    def _test_pool_connection(self):
        """Optional: Test pool connection on init."""
        conn = None
        try:
            conn = self._get_connection()
            conn.ping()
            log.info("Database connection pool test successful.")
        except mariadb.Error as e:
            log.critical(f"CRITICAL: Failed to connect to database pool on init: {e}", exc_info=True)
            # Depending on bot structure, might want to sys.exit or raise specific error
        finally:
            if conn:
                try: conn.close()
                except: pass

    # --- Refactored Database Methods ---

    ### JAC DATABASE ###
    def _execute_query(self, query, params=None, fetch=None, commit=False):
        """Helper method to execute queries using the connection pool."""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True) # Use dictionary cursor
            cursor.execute(query, params)

            if commit:
                conn.commit()
                log.debug(f"Query committed: {query[:100]}...") # Log snippet
                return cursor.rowcount # Return row count for modifications

            if fetch == 'one':
                return cursor.fetchone()
            elif fetch == 'all':
                return cursor.fetchall()
            else: # No fetch needed, and commit was false (likely SELECT without fetch?)
                 # Or could be an uncommitted write if commit=False was intentional
                return None # Or raise error if state is unexpected

        except mariadb.Error as db_error:
            log.exception(f"Database error executing query [{query[:100]}...]: {db_error}", exc_info=True)
            # Rollback on error if it was intended to be a transaction
            if conn and commit:
                try:
                    conn.rollback()
                    log.warning("Transaction rolled back due to error.")
                except mariadb.Error as rb_error:
                    log.error(f"Error during rollback: {rb_error}", exc_info=True)
            raise # Re-raise the exception to be handled by caller
        finally:
            if cursor:
                try: cursor.close()
                except mariadb.Error: pass
            if conn:
                try: conn.close() # IMPORTANT: Return connection to pool
                except mariadb.Error: pass
                # log.debug("Returned connection to pool.")

    def getJac(self):
        """Retrieves all JAC entries."""
        statement = "SELECT user_id, link, date FROM jac ORDER BY user_id DESC"
        return self._execute_query(statement, fetch='all')

    def getJacByID(self, user_id: str):
        """Retrieves JAC entries for a specific user_id."""
        statement = "SELECT user_id, link, date FROM jac WHERE user_id=%s"
        return self._execute_query(statement, params=(user_id,), fetch='all')

    def addJac(self, user_id: str, link: str, date: str):
        """Adds a new entry to the jac table."""
        statement = "INSERT INTO jac (user_id, link, date) VALUES (%s, %s, %s)"
        return self._execute_query(statement, params=(user_id, link, date), commit=True)

    def delJac(self, user_id: str):
        """Deletes all JAC entries for a specific user_id."""
        statement = "DELETE FROM jac WHERE user_id=%s"
        return self._execute_query(statement, params=(user_id,), commit=True)

    def getLink(self, link: str):
        """Retrieves user_id and link for a specific link."""
        statement = "SELECT user_id, link FROM jac WHERE link=%s"
        # Fetch only one, assuming link is unique or we only care about the first match
        return self._execute_query(statement, params=(link,), fetch='one')

    ### TIMERS DATABASE ###
    def addTimerMute(self, user_id: str, endMute: str):
        """Adds or updates a mute timer for a user."""
        # Using NULL for empty date fields is generally better than empty strings ''
        statement = """INSERT INTO timers (user_id, ban, mute, endBan, endMute)
        VALUES (%s, false, true, NULL, %s)
        ON DUPLICATE KEY UPDATE mute=true, endMute=%s"""
        return self._execute_query(statement, params=(user_id, endMute, endMute), commit=True)

    def addTimerBan(self, user_id: str, endBan: str):
        """Adds or updates a ban timer for a user."""
        statement = """INSERT INTO timers (user_id, ban, mute, endBan, endMute)
        VALUES (%s, true, false, %s, NULL)
        ON DUPLICATE KEY UPDATE ban=true, endBan=%s"""
        return self._execute_query(statement, params=(user_id, endBan, endBan), commit=True)

    def getTimers(self):
        """Retrieves all active timers."""
        # Select specific columns and filter for active timers
        statement = "SELECT user_id, ban, mute, endBan, endMute FROM timers WHERE ban=true OR mute=true"
        return self._execute_query(statement, fetch='all')

    def delTimer(self, user_id):
        """Deletes all timer entries for a specific user."""
        statement = "DELETE FROM timers WHERE user_id=%s"
        return self._execute_query(statement, params=(user_id,), commit=True)

    ### WARNINGS DATABASE ###
    def getWarnUsers(self):
        """Retrieves summary data for all users with infractions."""
        statement = "SELECT user_id, warnings, kicks, bans, tag FROM warn_user ORDER BY user_id"
        return self._execute_query(statement, fetch='all')

    def getWarnUserByID(self, user_id: str):
        """Retrieves summary data for a specific user."""
        statement = "SELECT user_id, warnings, kicks, bans, tag FROM warn_user WHERE user_id=%s"
        # Use fetch one as user_id should be unique in warn_user
        return self._execute_query(statement, params=(user_id,), fetch='one')

    def getWarnReasons(self, user_id: str):
        """Retrieves all warning reasons for a specific user."""
        statement = "SELECT id, reason FROM warn_reasons WHERE user_id=%s ORDER BY id DESC"
        return self._execute_query(statement, params=(user_id,), fetch='all')

    def getWarnCount(self, user_id: str, reason: str):
        try:
            # Use SQL COUNT(*) to get the count directly from the database
            statement = "SELECT COUNT(*) AS warning_count FROM warn_reasons WHERE reason=%s AND user_id=%s"
            data = (reason, user_id)

            # fetch='one' will return a single row (as a dictionary due to dictionary=True)
            # In this case, the dictionary will look like {'warning_count': count}
            result_row = self._execute_query(statement, params=data, fetch='one')

            if result_row is not None:
                # Extract the count from the dictionary
                return result_row.get('warning_count', 0) # Use .get for safety
            else:
                # This case should theoretically not happen with COUNT(*),
                # but good practice to handle.
                return 0

        except mariadb.Error as db_error:
            log.exception("Error retrieving warning count for user: %s", db_error)
            # Depending on desired behavior, return 0 or re-raise
            return 0
        except Exception as e:
            # Catch any other unexpected errors
            log.exception("Unexpected error in getWarnCount: %s", e)
            return 0

    def addWarning(self, user_id: str, tag:str, reason: str):
        """Adds a warning reason and increments the warning count for a user."""
        # Use INSERT ... ON DUPLICATE KEY UPDATE for atomicity
        user_update_statement = """
            INSERT INTO warn_user (user_id, warnings, kicks, bans, tag)
            VALUES (%s, 1, 0, 0, %s)
            ON DUPLICATE KEY UPDATE warnings = warnings + 1, tag = VALUES(tag)
        """
        reason_insert_statement = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"

        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Execute both statements within a transaction
            cursor.execute(user_update_statement, (user_id, tag))
            cursor.execute(reason_insert_statement, (user_id, reason))

            conn.commit() # Commit both changes together
            log.debug(f"Warning added for user {user_id}")
            return cursor.rowcount # Indicate success
        except mariadb.Error as db_error:
            log.exception(f"Database error adding warning for user {user_id}: {db_error}", exc_info=True)
            if conn:
                try: conn.rollback()
                except mariadb.Error: pass
            raise
        finally:
            if cursor:
                try: cursor.close()
                except mariadb.Error: pass
            if conn:
                try: conn.close()
                except mariadb.Error: pass

    def delWarning(self, user_id: str, reason: str):
        """Deletes a specific warning reason by its ID and decrements count."""
        # It's much safer to delete by a unique ID than by reason text
        reason_delete_statement = "DELETE FROM warn_reasons WHERE reason=%s AND user_id=%s"
        user_update_statement = "UPDATE warn_user SET warnings = GREATEST(warnings - 1, 0) WHERE user_id=%s"

        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # Execute both statements within a transaction
            cursor.execute(reason_delete_statement, (reason, user_id))
            deleted_count = cursor.rowcount # Check if the reason was actually deleted

            if deleted_count > 0:
                cursor.execute(user_update_statement, (user_id,))
                conn.commit() # Commit both changes together
                log.debug(f"Warning reason '{reason}' deleted for user {user_id}")
                return deleted_count
            else:
                log.warning(f"Warning reason '{reason}' not found for user {user_id}. No changes made.")
                conn.rollback() # Rollback if reason wasn't found
                return 0

        except mariadb.Error as db_error:
            log.exception(f"Database error deleting warning reason '{reason}' for user {user_id}: {db_error}", exc_info=True)
            if conn:
                try: conn.rollback()
                except mariadb.Error: pass
            raise
        finally:
            if cursor:
                try: cursor.close()
                except mariadb.Error: pass
            if conn:
                try: conn.close()
                except mariadb.Error: pass

    ### KICKS DATABASE ###
    # Assuming kicks/bans also just add a reason and update the counter atomically
    def addKick(self, user_id: str, tag:str, reason: str):
        """Adds a kick reason and increments the kick count for a user."""
        user_update_statement = """
            INSERT INTO warn_user (user_id, warnings, kicks, bans, tag)
            VALUES (%s, 0, 1, 0, %s)
            ON DUPLICATE KEY UPDATE kicks = kicks + 1, tag = VALUES(tag)
        """
        reason_insert_statement = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(user_update_statement, (user_id, tag))
            cursor.execute(reason_insert_statement, (user_id, reason))
            conn.commit()
            log.debug(f"Kick added for user {user_id}")
            return cursor.rowcount
        except mariadb.Error as db_error:
            log.exception(f"Database error adding kick for user {user_id}: {db_error}", exc_info=True)
            if conn:
                try: conn.rollback()
                except: pass
            raise
        finally:
            if cursor:
                try: cursor.close()
                except: pass
            if conn:
                try: conn.close()
                except: pass


    def delKick(self, user_id: str, reason: str):
        """Deletes a specific kick reason by its ID and decrements count."""
        reason_delete_statement = "DELETE FROM warn_reasons WHERE reason=%s AND user_id=%s"
        user_update_statement = "UPDATE warn_user SET kicks = GREATEST(kicks - 1, 0) WHERE user_id=%s"

        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(reason_delete_statement, (reason, user_id))
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                cursor.execute(user_update_statement, (user_id,))
                conn.commit()
                log.debug(f"Kick reason '{reason}' deleted for user {user_id}")
                return deleted_count
            else:
                log.warning(f"Kick reason '{reason}' not found for user {user_id}.")
                conn.rollback()
                return 0
        except mariadb.Error as db_error:
            log.exception(f"Database error deleting kick reason '{reason}' for user {user_id}: {db_error}", exc_info=True)
            if conn:
                try: conn.rollback()
                except: pass
            raise
        finally:
            if cursor:
                try: cursor.close()
                except: pass
            if conn:
                try: conn.close()
                except: pass

    ### BANS DATABASE ###
    def addBan(self, user_id: str, tag:str, reason: str):
        """Adds a ban reason and increments the ban count for a user."""
        user_update_statement = """
            INSERT INTO warn_user (user_id, warnings, kicks, bans, tag)
            VALUES (%s, 0, 0, 1, %s)
            ON DUPLICATE KEY UPDATE bans = bans + 1, tag = VALUES(tag)
        """
        reason_insert_statement = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"

        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(user_update_statement, (user_id, tag))
            cursor.execute(reason_insert_statement, (user_id, reason))
            conn.commit()
            log.debug(f"Ban added for user {user_id}")
            return cursor.rowcount
        except mariadb.Error as db_error:
            log.exception(f"Database error adding ban for user {user_id}: {db_error}", exc_info=True)
            if conn:
                try: conn.rollback()
                except: pass
            raise
        finally:
            if cursor:
                try: cursor.close()
                except: pass
            if conn:
                try: conn.close()
                except: pass

    def delBan(self, user_id: str, reason: str):
        """Deletes a specific ban reason by its ID and decrements count."""
        reason_delete_statement = "DELETE FROM warn_reasons WHERE id=%s AND user_id=%s"
        user_update_statement = "UPDATE warn_user SET bans = GREATEST(bans - 1, 0) WHERE user_id=%s"
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(reason_delete_statement, (reason, user_id))
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                cursor.execute(user_update_statement, (user_id,))
                conn.commit()
                log.debug(f"Ban reason '{reason}' deleted for user {user_id}")
                return deleted_count
            else:
                log.warning(f"Ban reason '{reason}' not found for user {user_id}.")
                conn.rollback()
                return 0
        except mariadb.Error as db_error:
            log.exception(f"Database error deleting ban reason '{reason}' for user {user_id}: {db_error}", exc_info=True)
            if conn:
                try: conn.rollback()
                except: pass
            raise
        finally:
            if cursor:
                try: cursor.close()
                except: pass
            if conn:
                try: conn.close()
                except: pass


    ### KILL BOARD DATABASE ###
    def getKillCount(self, user_id: str):
        """Gets total kill count for all users or a specific user."""
        if user_id == "*":
            statement = "SELECT user_id, counter FROM kill_board"
            results = self._execute_query(statement, fetch='all')
            total_counter = sum(item['counter'] for item in results) if results else 0
            # log.info(f"Total kill count: {total_counter}")
            return total_counter
        else:
            statement = "SELECT user_id, counter FROM kill_board WHERE user_id=%s"
            result = self._execute_query(statement, params=(user_id,), fetch='one')
            count = result['counter'] if result else 0
            # log.info(f"Kill count for user {user_id}: {count}")
            return count

    def addKillCount(self, user_id: str):
        """Increments kill count for a user, adding them if they don't exist."""
        statement = """
            INSERT INTO kill_board (user_id, counter) VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE counter = counter + 1
        """
        return self._execute_query(statement, params=(user_id,), commit=True)

    def delKillCount(self, user_id: str, amount: int):
        """Deletes user or decrements kill count by amount."""
        if amount == 0: # Special case: delete user entirely
            statement = "DELETE FROM kill_board WHERE user_id=%s"
            return self._execute_query(statement, params=(user_id,), commit=True)
        elif amount > 0:
            # Need to handle this carefully to avoid negative counts within a transaction
            conn = None
            cursor = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor(dictionary=True)

                # Lock row for update (optional, depends on concurrency needs)
                # cursor.execute("SELECT counter FROM kill_board WHERE user_id=%s FOR UPDATE", (user_id,))
                cursor.execute("SELECT counter FROM kill_board WHERE user_id=%s", (user_id,))
                result = cursor.fetchone()

                if result:
                    current_count = result['counter']
                    if current_count - amount < 0:
                        log.warning(f"Attempt to reduce kill count below zero for user {user_id}. Deleting user instead.")
                        # Fall through to delete if amount would make it negative
                        cursor.execute("DELETE FROM kill_board WHERE user_id=%s", (user_id,))
                    else:
                        cursor.execute("UPDATE kill_board SET counter = counter - %s WHERE user_id=%s", (amount, user_id))
                    conn.commit()
                    return cursor.rowcount
                else:
                    log.warning(f"User {user_id} not found in kill_board for deletion/decrement.")
                    return 0 # User not found

            except mariadb.Error as db_error:
                log.exception(f"Error reducing kill counter for user {user_id}: {db_error}", exc_info=True)
                if conn:
                    try: conn.rollback()
                    except: pass
                raise
            finally:
                if cursor:
                    try: cursor.close()
                    except: pass
                if conn:
                    try: conn.close()
                    except: pass
        else: # amount < 0
            log.error(f"Invalid amount ({amount}) passed to delKillCount for user {user_id}.")
            return 0


def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Database(bot))

