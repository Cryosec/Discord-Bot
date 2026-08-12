# pylint: disable=F0401, W0702, W0703, W0105, W0613, W1203, E1101, E0401, W0603
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import unquote, urlencode
from functools import wraps
import uuid

# Flask and Extensions
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, abort
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix

# Environment and HTTP Requests
from dotenv import load_dotenv
import requests

# Database & Redis
import mariadb
import redis

load_dotenv() # Load environment variables from .env file

# --- Logging Setup (Keep Existing) ---
log = logging.getLogger('api')
log.setLevel(logging.INFO)
log_formatter = logging.Formatter("%(name)s - %(asctime)s:%(levelname)s: %(message)s")
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = RotatingFileHandler(
    filename="logs/api.log", mode="a", maxBytes=20000, backupCount=5, encoding="utf-8")
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
log.addHandler(file_handler)
log.addHandler(console_handler)

# --- Flask Application Initialization ---
app = Flask(__name__)

# --- Apply ProxyFix ---
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

# --- Configuration ---
# Load essential configuration from environment variables
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY') # MUST set a strong secret key in .env for production
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN') # Bot token needed for role check
DISCORD_GUILD_ID = os.getenv('DISCORD_GUILD_ID')
DISCORD_MOD_IDS_RAW = os.getenv('DISCORD_MOD_ID', '') # Expecting comma-separated string or single ID
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', '/') # URL to redirect back to after login
FLASK_BASE_URL = os.getenv('FLASK_BASE_URL') # Base URL of this Flask app

# Explicitly set the preferred scheme if needed (good practice with ProxyFix)
if FLASK_BASE_URL.startswith('https'):
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# Parse moderator role IDs
if not DISCORD_MOD_IDS_RAW:
    log.warning("DISCORD_MOD_ID environment variable is not set or empty.")
    REQUIRED_MOD_ROLE_IDS = set()
else:
    REQUIRED_MOD_ROLE_IDS = set(role_id.strip() for role_id in DISCORD_MOD_IDS_RAW.split(','))

# Validate essential Discord config
if not all([DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_BOT_TOKEN, DISCORD_GUILD_ID]):
    log.critical("Missing one or more Discord environment variables (CLIENT_ID, CLIENT_SECRET, TOKEN, GUILD_ID)")
    sys.exit("Error: Missing Discord configuration in .env file.")
if not REQUIRED_MOD_ROLE_IDS:
     log.warning("No moderator roles configured in DISCORD_MOD_ID. Authorization checks might fail.")

# Discord API Endpoints
DISCORD_API_BASE_URL = 'https://discord.com/api/v10' # Using API v10
AUTHORIZATION_BASE_URL = DISCORD_API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = DISCORD_API_BASE_URL + '/oauth2/token'


# --- Redis Configuration ---
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None) # Will be None if not set

if not REDIS_PASSWORD:
    log.warning("REDIS_PASSWORD environment variable not set. Attempting to connect to Redis without a password.")
else:
    log.debug(f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT} using a password.")

# Create Redis client instance
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD
    )
    # Test the connection
    redis_client.ping()
    log.debug(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.AuthenticationError:
    log.critical(f"CRITICAL: Redis authentication failed for {REDIS_HOST}:{REDIS_PORT}. Check REDIS_PASSWORD.", exc_info=True)
    sys.exit("Error: Redis authentication failed.")
except redis.exceptions.ConnectionError as e:
    log.critical(f"CRITICAL: Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT} - {e}", exc_info=True)
    sys.exit("Error: Could not connect to Redis for session storage.")
except Exception as e: # Catch other potential errors
    log.critical(f"CRITICAL: Error configuring Redis client for {REDIS_HOST}:{REDIS_PORT} - {e}", exc_info=True)
    sys.exit("Error: Could not configure Redis client.")



# --- Session Configuration ---
# Configure server-side sessions
# Options: 'filesystem', 'redis', 'mongodb', 'sqlalchemy', etc.
# Filesystem is simple for dev, use Redis or similar for production
app.config['SESSION_TYPE'] ='redis'
app.config['SESSION_PERMANENT'] = True # Make session last longer
app.config['SESSION_USE_SIGNER'] = True # Sign session cookies
app.config['SESSION_KEY_PREFIX'] = 'session:lfd-dev:'
app.config['SESSION_REDIS'] = redis_client

app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production' # Use secure cookies in production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


# Initialize the session extension
Session(app)

# --- Database Connection Handling (Keep Existing) ---
DB_USER = str(os.getenv("DB_USERNAME"))
DB_PASS = str(os.getenv("DB_PASSWORD"))
DB_HOST = str(os.getenv("DB_HOST"))
DB_PORT_STR = os.getenv("DB_PORT")
DB_NAME = str(os.getenv("DB_NAME"))

# Validate essential environment variables
if not all([DB_USER, DB_PASS, DB_HOST, DB_PORT_STR, DB_NAME]):
    log.critical("Missing one or more database environment variables (DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)")
    sys.exit("Error: Missing database configuration in .env file.")

try:
    DB_PORT = int(DB_PORT_STR)
except ValueError:
    log.critical(f"Invalid DB_PORT value: '{DB_PORT_STR}'. Must be an integer.")
    sys.exit("Error: Invalid DB_PORT.")

# Global connection and cursor (manage carefully in production)
# Consider using connection pooling for more robust applications
conn = None
cur = None

def get_db_connection():
    """Establishes or returns the existing database connection."""
    global conn, cur
    try:
        # Check if connection is alive, otherwise reconnect
        if conn is None or not conn.is_connected():
            log.debug("Connecting to MariaDB...")
            conn = mariadb.connect(
                user=DB_USER,
                password=DB_PASS,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                autocommit=False # Explicitly manage commits/rollbacks per request
            )
            # conn.auto_reconnect = True # auto_reconnect is often handled by the pool or framework
            cur = conn.cursor(dictionary=True) # Use dictionary cursor for easier JSON conversion
            log.debug("Connection to database successful.")
        # Ensure cursor is valid
        elif cur is None or cur.closed:
            cur = conn.cursor(dictionary=True)
            log.debug("Re-established cursor.")
        return conn, cur
    except mariadb.Error as db_error:
        log.exception("Error connecting to MariaDB platform: %s", db_error)
        return None, None
    except Exception as e:
        log.exception("An unexpected error occurred during DB connection: %s", e)
        return None, None

def close_db_connection(exception=None):
    """Closes the database connection (if open)."""
    global conn, cur
    # Note: Closing should ideally happen after commit/rollback decision
    # The teardown context handles this generally
    db_conn_to_close = conn
    db_cur_to_close = cur
    conn = None # Reset globals immediately
    cur = None

    if db_cur_to_close is not None and not db_cur_to_close.closed:
        try:
            db_cur_to_close.close()
            log.debug("DB cursor closed.")
        except mariadb.Error as db_error:
            log.error("Error closing cursor: %s", db_error)
    if db_conn_to_close is not None:
        try:
            # Rollback any pending transaction if closing due to exception
            if exception:
                log.warning("Rolling back transaction due to exception: %s", exception)
                db_conn_to_close.rollback()
            db_conn_to_close.close()
            log.debug("DB connection closed.")
        except mariadb.Error as db_error:
            log.error("Error during connection close/rollback: %s", db_error)


@app.teardown_appcontext
def teardown_db(exception=None):
    """Ensures DB connection is closed after each request."""
    close_db_connection(exception)

# --- Helper Function for Commits/Rollbacks ---
def handle_db_transaction(conn, cur, success_message, failure_message_prefix, log_context):
    """Commits or rolls back transaction and returns appropriate response."""
    try:
        conn.commit()
        log.debug(f"{log_context}: Transaction committed successfully.")
        return jsonify({"message": success_message}), 200 # Or 201 for creations
    except mariadb.Error as db_error:
        log.exception(f"{log_context}: Error during commit: %s", db_error)
        try:
            conn.rollback()
            log.warning(f"{log_context}: Transaction rolled back due to commit error.")
        except mariadb.Error as rb_error:
            log.error(f"{log_context}: Error during rollback after commit failure: %s", rb_error)
        return jsonify({"error": f"{failure_message_prefix}: Commit failed", "details": str(db_error)}), 500 # Avoid details in prod

def handle_db_error(conn, error, failure_message_prefix, log_context, status_code=500):
    """Logs error, rolls back transaction, and returns error response."""
    log.exception(f"{log_context}: Database operation failed: %s", error)
    try:
        if conn and conn.is_connected():
            conn.rollback()
            log.warning(f"{log_context}: Transaction rolled back due to operation error.")
    except mariadb.Error as rb_error:
        log.error(f"{log_context}: Error during rollback after operation failure: %s", rb_error)
    # Avoid sending detailed errors to client in production
    error_detail = str(error) if app.debug else "Internal server error."
    return jsonify({"error": f"{failure_message_prefix}: Operation failed", "details": error_detail}), status_code


# --- Authorization Decorator ---
def mod_required(f):
    """Decorator to ensure the user is logged in and authorized via session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or not session.get('is_authorized'):
            log.warning(f"Unauthorized access attempt to {request.path}")
            abort(401) # Unauthorized - User needs to log in or lacks permissions
        # User is logged in and authorized
        return f(*args, **kwargs)
    return decorated_function


# --- Helper Function to Get Client IP ---
def get_client_ip(request_obj):
    """
    Gets the client IP address, prioritizing Cloudflare headers
    and falling back to ProxyFix-corrected remote_addr.
    """
    # Check Cloudflare header first
    cf_ip = request_obj.headers.get('CF-Connecting-IP')
    if cf_ip:
        # TODO: Optionally add validation here to ensure cf_ip is a valid IP format
        return cf_ip

    # Check True-Client-IP as another common proxy/CDN header
    true_client_ip = request_obj.headers.get('True-Client-IP')
    if true_client_ip:
        return true_client_ip

    # Fallback to request.remote_addr (should be corrected by ProxyFix)
    # This relies on ProxyFix and X-Forwarded-For being set correctly
    # by BOTH Cloudflare and your own proxy.
    # The number of proxies trusted by ProxyFix (x_for=N) might need adjustment.
    # If ProxyFix trusts too many, it might pick up an internal IP.
    # If it trusts too few, it might pick up Cloudflare's IP.
    # Hence, prioritizing CF-Connecting-IP is often safer.
    return request_obj.remote_addr


# --- Authentication Routes ---

@app.route('/api/auth/discord/login')
def discord_login():
    """Redirects user to Discord for authentication."""

    ip_addr = get_client_ip(request)# Get IP address (corrected by ProxyFix)
    log.info(f"Login initiated by IP: {ip_addr}") # <<< Log IP starting login

    state = str(uuid.uuid4())
    session['oauth_state'] = state # Store state in session for CSRF protection
    log.debug(f"State set in session for IP {ip_addr}: {session.get('oauth_state')}")

    redirect_uri = url_for('discord_callback', _external=True)
    # Ensure redirect_uri uses HTTPS in production if FLASK_BASE_URL is HTTPS
    if FLASK_BASE_URL.startswith('https') and redirect_uri.startswith('http://'):
        redirect_uri = redirect_uri.replace('http://', 'https://', 1)

    log.debug(f"Generated state: {state}, Redirect URI: {redirect_uri}")

    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'identify guilds', # Request user ID/name and list of guilds
        'state': state
    }
    login_url = f"{AUTHORIZATION_BASE_URL}?{urlencode(params)}"
    return redirect(login_url)

@app.route('/api/auth/discord/callback')
def discord_callback():
    """Handles the callback from Discord after authorization."""

    ip_addr = get_client_ip(request) # Get IP address
    log.info(f"Callback received from IP: {ip_addr}") # <<< Log IP on callback entry
    log.debug(f"Current session object in /callback from IP {ip_addr}: {dict(session)}")

    # --- 1. State Verification (CSRF Protection) ---
    code = request.args.get('code')
    state = request.args.get('state')
    stored_state = session.pop('oauth_state', None) # Get and remove state from session

    if state is None or state != stored_state:
        log.error(f"Invalid OAuth state. Received: {state}, Expected: {stored_state}")
        abort(403, "Invalid state parameter. CSRF attempt?") # Forbidden

    if code is None:
        log.error(f"Discord callback missing 'code' parameter for IP: {ip_addr}") # <<< Log IP on code failure
        # Handle error - maybe redirect to frontend with error message
        return redirect(f"{FRONTEND_BASE_URL}?error=auth_failed")

    # --- 2. Token Exchange ---
    redirect_uri = url_for('discord_callback', _external=True)
    # Ensure redirect_uri uses HTTPS in production if FLASK_BASE_URL is HTTPS
    if FLASK_BASE_URL.startswith('https') and redirect_uri.startswith('http://'):
        redirect_uri = redirect_uri.replace('http://', 'https://', 1)

    token_data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    try:
        log.info("Exchanging code for token...")
        token_response = requests.post(TOKEN_URL, data=token_data, headers=headers, timeout=10)
        token_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        if not access_token:
            log.error(f"Failed to get access token from Discord response: {token_json}")
            raise ValueError("Access token not found in Discord response")
        log.info("Token received successfully.")
    except requests.exceptions.RequestException as e:
        log.exception(f"Error exchanging code with Discord: {e}")
        return redirect(f"{FRONTEND_BASE_URL}?error=token_exchange_failed")
    except ValueError as e:
        log.error(e)
        return redirect(f"{FRONTEND_BASE_URL}?error=token_exchange_failed")

    # --- 3. Fetch User Info ---
    user_headers = {'Authorization': f'Bearer {access_token}'}
    try:
        log.info("Fetching user info (/users/@me)...")
        user_response = requests.get(f'{DISCORD_API_BASE_URL}/users/@me', headers=user_headers, timeout=10)
        user_response.raise_for_status()
        user_info = user_response.json()
        user_id = user_info.get('id')
        username = user_info.get('username')
        discriminator = user_info.get('discriminator')
        full_username = f"{username}#{discriminator}"
        if not user_id or not username:
            log.error(f"Could not extract user ID or username from /users/@me response: {user_info}")
            raise ValueError("User ID or username missing from Discord user info")
        log.info(f"User info received: ID={user_id}, Username={full_username}")
    except requests.exceptions.RequestException as e:
        log.exception(f"Error fetching user info from Discord: {e}")
        return redirect(f"{FRONTEND_BASE_URL}?error=user_fetch_failed")
    except ValueError as e:
        log.error(e)
        return redirect(f"{FRONTEND_BASE_URL}?error=user_fetch_failed")

    # --- 4. Check Guild Membership ---
    try:
        log.info("Fetching user guilds (/users/@me/guilds)...")
        guilds_response = requests.get(f'{DISCORD_API_BASE_URL}/users/@me/guilds', headers=user_headers, timeout=10)
        guilds_response.raise_for_status()
        guilds = guilds_response.json()

        # Check if the user is in the target guild
        is_in_guild = any(guild['id'] == DISCORD_GUILD_ID for guild in guilds)
        if not is_in_guild:
            log.warning(f"User {user_id} ({full_username}) is not a member of the target guild {DISCORD_GUILD_ID}.")
            # Redirect with specific error? Or just fail auth.
            return redirect(f"{FRONTEND_BASE_URL}?error=not_in_guild")
        log.info(f"User {user_id} is a member of the target guild {DISCORD_GUILD_ID}.")

    except requests.exceptions.RequestException as e:
        log.exception(f"Error fetching user guilds from Discord: {e}")
        return redirect(f"{FRONTEND_BASE_URL}?error=guild_fetch_failed")

    # --- 5. Check Roles within Target Guild (using Bot Token) ---
    member_url = f'{DISCORD_API_BASE_URL}/guilds/{DISCORD_GUILD_ID}/members/{user_id}'
    bot_headers = {'Authorization': f'Bot {DISCORD_BOT_TOKEN}'}
    try:
        log.info(f"Fetching member roles for user {user_id} in guild {DISCORD_GUILD_ID} using Bot Token...")
        member_response = requests.get(member_url, headers=bot_headers, timeout=10)
        member_response.raise_for_status() # Check for 404 (not member) or 403 (bot lacks perms)
        member_info = member_response.json()
        user_roles = set(member_info.get('roles', [])) # Get the list of role IDs the user has

        # Check if user has any of the required moderator roles
        has_mod_role = any(role_id in REQUIRED_MOD_ROLE_IDS for role_id in user_roles)

        if not has_mod_role:
            log.warning(f"User {user_id} ({full_username}) does not have required roles in guild {DISCORD_GUILD_ID}. User roles: {user_roles}, Required: {REQUIRED_MOD_ROLE_IDS}")
            return redirect(f"{FRONTEND_BASE_URL}?error=unauthorized_role")
        log.info(f"User {user_id} has required moderator role(s). Authorizing.")

    except requests.exceptions.RequestException as e:
        if e.response is not None:
            log.exception(f"Error fetching member roles from Discord (Status {e.response.status_code}): {e}. Check Bot Token and permissions (Members Intent?). Response: {e.response.text}")
            if e.response.status_code == 404:
                # Should have been caught by guild check, but handle defensively
                return redirect(f"{FRONTEND_BASE_URL}?error=not_in_guild")
            if e.response.status_code == 403:
                return redirect(f"{FRONTEND_BASE_URL}?error=bot_permission_error")
        else:
            log.exception(f"Network or other error fetching member roles from Discord: {e}")
        return redirect(f"{FRONTEND_BASE_URL}?error=role_check_failed")

    # --- 6. Create Session ---
    session.clear() # Clear previous session data just in case
    session['user_id'] = user_id
    session['username'] = full_username
    session['is_authorized'] = True # Mark user as authorized moderator
    session.permanent = True # Use the app's permanent session lifetime

    log.info(f"Session created for user {user_id} ({full_username}). Redirecting to frontend.")
    return redirect(FRONTEND_BASE_URL) # Redirect to the main frontend page

@app.route('/api/auth/status')
def auth_status():
    """Checks if the user has a valid, authorized session."""
    if session.get('user_id') and session.get('is_authorized'):
        return jsonify({
            'is_logged_in': True,
            'user': {
                'id': session['user_id'],
                'username': session.get('username', 'Unknown')
            }
        }), 200
    else:
        return jsonify({'is_logged_in': False}), 200 # Return 200 OK, but indicate not logged in

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logs the user out by clearing the session."""
    log.info(f"Logging out user {session.get('user_id')}")
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

# --- Protected API Routes ---
# Apply the @mod_required decorator to all routes that need protection

@app.route('/api/jac', methods=['GET'])
@mod_required # Apply decorator
def get_all_jac():
    """Retrieves all entries from the jac table."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        statement = "SELECT user_id, link, date FROM jac ORDER BY date DESC"
        cur.execute(statement)
        jac_entries = cur.fetchall()
        for entry in jac_entries:
            if 'date' in entry and hasattr(entry['date'], 'isoformat'):
                entry['date'] = entry['date'].isoformat()
        return jsonify(jac_entries), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving JAC from DB: %s", db_error)
        return jsonify({"error": "Failed to retrieve JAC entries", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception("API Unexpected error in get_all_jac: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/jac/<string:user_id>', methods=['GET'])
@mod_required # Apply decorator
def get_jac_by_id(user_id):
    """Retrieves JAC entries for a specific user_id."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        statement = "SELECT user_id, link, date FROM jac WHERE user_id=%s"
        cur.execute(statement, (user_id,))
        jac_entries = cur.fetchall()
        for entry in jac_entries:
            if 'date' in entry and hasattr(entry['date'], 'isoformat'):
                entry['date'] = entry['date'].isoformat()
        return jsonify(jac_entries), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving JAC by ID: %s", db_error)
        return jsonify({"error": f"Failed to retrieve JAC entries for user {user_id}", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception("API Unexpected error in get_jac_by_id: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/jac', methods=['POST'])
@mod_required # Apply decorator
def add_jac_entry():
    """Adds a new entry to the jac table."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    user_id = data.get('user_id')
    link = data.get('link')
    date_str = data.get('date') # Expecting date as string, e.g., YYYY-MM-DD HH:MM:SS

    if not user_id or not link or not date_str:
        return jsonify({"error": "Missing required fields: user_id, link, date"}), 400
    # TODO: Add input validation for link format, date format etc.

    try:
        statement = "INSERT INTO jac (user_id, link, date) VALUES (%s, %s, %s)"
        cur.execute(statement, (user_id, link, date_str))
        conn.commit()
        log.info(f"Added JAC entry for user {user_id} by {session.get('user_id', 'Unknown User')}") # Log who did it
        cur.execute("SELECT user_id, link, date FROM jac WHERE user_id=%s AND link=%s AND date=%s", (user_id, link, date_str))
        new_entry = cur.fetchone()
        if new_entry and 'date' in new_entry and hasattr(new_entry['date'], 'isoformat'):
            new_entry['date'] = new_entry['date'].isoformat()
        return jsonify(new_entry or {"message": "JAC entry added successfully"}), 201 # 201 Created
    except mariadb.IntegrityError as db_error:
        return handle_db_error(conn, db_error, "Failed to add JAC entry", "Add JAC", 409) # 409 Conflict
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, "Failed to add JAC entry", "Add JAC")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in add_jac_entry: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/jac/<string:user_id>', methods=['DELETE'])
@mod_required # Apply decorator
def delete_jac_entry(user_id):
    """Deletes all JAC entries for a specific user_id."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500

    try:
        statement = "DELETE FROM jac WHERE user_id=%s"
        cur.execute(statement, (user_id,))
        deleted_count = cur.rowcount
        conn.commit() # Commit the transaction

        if deleted_count > 0:
            log.info(f"Deleted {deleted_count} JAC entry/entries for user {user_id} by {session.get('user_id', 'Unknown User')}")
            return jsonify({"message": f"Successfully deleted {deleted_count} JAC entries for user {user_id}", "deleted_count": deleted_count}), 200
        else:
            log.warning(f"Attempted to delete JAC for user {user_id} by {session.get('user_id', 'Unknown User')}, but no rows were found.")
            return jsonify({"message": f"No JAC entries found for user {user_id} to delete"}), 404
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, f"Failed to delete JAC entries for user {user_id}", "Delete JAC")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in delete_jac_entry: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

# --- Timers Routes ---
@app.route('/api/timers', methods=['GET'])
@mod_required # Apply decorator
def get_all_timers():
    """Retrieves all active timers."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        statement = "SELECT user_id, ban, mute, endBan, endMute FROM timers WHERE ban=true OR mute=true"
        cur.execute(statement)
        timers = cur.fetchall()
        for timer in timers:
            if 'endBan' in timer and hasattr(timer['endBan'], 'isoformat'): timer['endBan'] = timer['endBan'].isoformat()
            if 'endMute' in timer and hasattr(timer['endMute'], 'isoformat'): timer['endMute'] = timer['endMute'].isoformat()
        return jsonify(timers), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving Timers from DB: %s", db_error)
        return jsonify({"error": "Failed to retrieve timers", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception("API Unexpected error in get_all_timers: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/timers/mute', methods=['POST'])
@mod_required # Apply decorator
def add_mute_timer():
    """Adds or updates a mute timer for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json()
    user_id = data.get('user_id')
    endMute = data.get('endMute')
    if not user_id or not endMute: return jsonify({"error": "Missing required fields: user_id, endMute"}), 400
    # TODO: Validate endMute format
    try:
        statement = """
            INSERT INTO timers (user_id, ban, mute, endBan, endMute) VALUES (%s, false, true, NULL, %s)
            ON DUPLICATE KEY UPDATE mute=true, endMute=%s """
        cur.execute(statement, (user_id, endMute, endMute))
        conn.commit()
        log.info(f"Added/Updated mute timer for user {user_id} until {endMute} by {session.get('user_id', 'Unknown User')}")
        return jsonify({"message": "Mute timer added/updated successfully", "user_id": user_id, "endMute": endMute}), 200
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, "Failed to add/update mute timer", "Add Mute Timer")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in add_mute_timer: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/timers/ban', methods=['POST'])
@mod_required # Apply decorator
def add_ban_timer():
    """Adds or updates a ban timer for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json()
    user_id = data.get('user_id')
    endBan = data.get('endBan')
    if not user_id or not endBan: return jsonify({"error": "Missing required fields: user_id, endBan"}), 400
    # TODO: Validate endBan format
    try:
        statement = """
            INSERT INTO timers (user_id, ban, mute, endBan, endMute) VALUES (%s, true, false, %s, NULL)
            ON DUPLICATE KEY UPDATE ban=true, endBan=%s """
        cur.execute(statement, (user_id, endBan, endBan))
        conn.commit()
        log.info(f"Added/Updated ban timer for user {user_id} until {endBan} by {session.get('user_id', 'Unknown User')}")
        return jsonify({"message": "Ban timer added/updated successfully", "user_id": user_id, "endBan": endBan}), 200
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, "Failed to add/update ban timer", "Add Ban Timer")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in add_ban_timer: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/timers/<string:user_id>', methods=['DELETE'])
@mod_required # Apply decorator
def delete_timer(user_id):
    """Deletes all timer entries (mute and ban) for a specific user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        check_stmt = "SELECT 1 FROM timers WHERE user_id=%s LIMIT 1"
        cur.execute(check_stmt, (user_id,))
        exists = cur.fetchone()
        if not exists: return jsonify({"message": f"No timers found for user {user_id} to delete"}), 404

        statement = "DELETE FROM timers WHERE user_id=%s"
        cur.execute(statement, (user_id,))
        deleted_count = cur.rowcount
        conn.commit()
        log.info(f"Deleted timers for user {user_id} by {session.get('user_id', 'Unknown User')}")
        return jsonify({"message": f"Successfully deleted timers for user {user_id}", "deleted_count": deleted_count}), 200
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, f"Failed to delete timers for user {user_id}", "Delete Timer")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in delete_timer: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

# --- Infractions Routes ---
@app.route('/api/infractions', methods=['GET'])
@mod_required # Apply decorator
def get_all_infractions():
    """Retrieves all users with warnings, kicks, or bans."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        statement = "SELECT user_id, warnings, kicks, bans, tag FROM warn_user ORDER BY user_id"
        cur.execute(statement)
        users = cur.fetchall()
        return jsonify(users), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving warn_users from DB: %s", db_error)
        return jsonify({"error": "Failed to retrieve infraction summaries", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception("API Unexpected error in get_all_infractions: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/infractions/<string:user_id>', methods=['GET'])
@mod_required # Apply decorator
def get_user_infractions(user_id):
    """Retrieves detailed infraction info (summary + reasons) for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        summary_stmt = "SELECT user_id, warnings, kicks, bans, tag FROM warn_user WHERE user_id=%s"
        cur.execute(summary_stmt, (user_id,))
        user_summary = cur.fetchone()
        if not user_summary: return jsonify({"message": "No infraction records found for this user"}), 404

        # Assuming warn_reasons has 'id', 'reason', 'timestamp' columns
        reasons_stmt = "SELECT id, reason FROM warn_reasons WHERE user_id=%s ORDER BY id DESC"
        cur.execute(reasons_stmt, (user_id,))
        reasons_raw = cur.fetchall()
        reasons = []
        for r in reasons_raw:
            reasons.append({
                "id": r.get('id'), # Include reason ID if needed for deletion later
                "reason": r.get('reason')
            })
        user_summary['reasons'] = reasons
        return jsonify(user_summary), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving user infractions: %s", db_error)
        return jsonify({"error": f"Failed to retrieve infractions for user {user_id}", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception("API Unexpected error in get_user_infractions: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

# --- Add/Delete Warnings/Kicks/Bans ---
# Apply @mod_required to all POST/DELETE routes here
@app.route('/api/warnings', methods=['POST'])
@mod_required
def add_warning():
    """Adds a warning for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    user_id = data.get('user_id')
    tag = data.get('tag')
    reason = data.get('reason')

    if not user_id or not tag or not reason:
        return jsonify({"error": "Missing required fields: user_id, tag, reason"}), 400

    try:
        # Use INSERT ... ON DUPLICATE KEY UPDATE for warn_user
        user_stmt = """
            INSERT INTO warn_user (user_id, warnings, kicks, bans, tag)
            VALUES (%s, 1, 0, 0, %s)
            ON DUPLICATE KEY UPDATE warnings = warnings + 1, tag = VALUES(tag)
        """
        cur.execute(user_stmt, (user_id, tag))

        # Insert into warn_reasons (assuming timestamp is auto-generated or default)
        reason_stmt = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"
        cur.execute(reason_stmt, (user_id, reason))

        conn.commit()
        log.debug(f"Added warning for user {user_id} with reason: {reason}")
        return jsonify({"message": "Warning added successfully", "user_id": user_id, "reason": reason}), 201
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, "Failed to add warning", "Add Warning")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in add_warning: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

# Modify DELETE warning to potentially use reason ID if available from GET details
@app.route('/api/warnings/<string:user_id>/<path:reason>', methods=['DELETE']) # Keep path for now
@mod_required
def delete_warning(user_id, reason):
    """Deletes one instance of a specific warning reason for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500

    decoded_reason = unquote(reason) # Decode URL-encoded reason

    try:
        # Check how many instances of this reason exist for the user
        count_stmt = "SELECT COUNT(*) as count FROM warn_reasons WHERE user_id=%s AND reason=%s"
        cur.execute(count_stmt, (user_id, decoded_reason))
        count_result = cur.fetchone()
        reason_exists_count = count_result['count'] if count_result else 0

        if reason_exists_count == 0:
             return jsonify({"message": f"No warning with reason '{decoded_reason}' found for user {user_id} to delete"}), 404

        # Delete one instance of the reason (assuming timestamp helps order, or use LIMIT 1)
        # Make sure your warn_reasons table has a primary key or timestamp to order by for LIMIT
        # If no reliable order, LIMIT 1 might delete an arbitrary match.
        # Adding a unique ID to warn_reasons is the robust solution.
        # Assuming a 'timestamp' or 'id' column exists for ordering:
        # Replace 'id' with your actual primary key or timestamp column if different
        del_reason_stmt = """
            DELETE FROM warn_reasons
            WHERE user_id=%s AND reason=%s
            ORDER BY id DESC LIMIT 1
        """
        # If no ID/Timestamp: del_reason_stmt = "DELETE FROM warn_reasons WHERE user_id=%s AND reason=%s LIMIT 1"
        cur.execute(del_reason_stmt, (user_id, decoded_reason))
        deleted_reason_count = cur.rowcount

        if deleted_reason_count == 0:
            # Should not happen if count > 0, but handle defensively
            conn.rollback()
            log.warning(f"Warning reason delete query affected 0 rows for user {user_id}, reason '{decoded_reason}'. Rolling back.")
            return jsonify({"error": "Failed to delete warning reason instance, possibly due to concurrent modification."}), 500


        # Decrement warning count in warn_user, ensuring it doesn't go below zero
        update_user_stmt = "UPDATE warn_user SET warnings = GREATEST(warnings - 1, 0) WHERE user_id=%s"
        cur.execute(update_user_stmt, (user_id,))

        conn.commit()
        log.debug(f"Deleted warning reason '{decoded_reason}' for user {user_id}")
        return jsonify({"message": f"Successfully deleted warning reason '{decoded_reason}' for user {user_id}"}), 200

    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, f"Failed to delete warning reason '{decoded_reason}' for user {user_id}", "Delete Warning")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in delete_warning: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@app.route('/api/kicks', methods=['POST'])
@mod_required
def add_kick():
    """Adds a kick record for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    user_id = data.get('user_id')
    tag = data.get('tag')
    reason = data.get('reason') # Kick reason is stored in warn_reasons

    if not user_id or not tag or not reason:
        return jsonify({"error": "Missing required fields: user_id, tag, reason"}), 400

    try:
        # Update warn_user: Increment kicks count
        user_stmt = """
            INSERT INTO warn_user (user_id, warnings, kicks, bans, tag)
            VALUES (%s, 0, 1, 0, %s)
            ON DUPLICATE KEY UPDATE kicks = kicks + 1, tag = VALUES(tag)
        """
        cur.execute(user_stmt, (user_id, tag))

        # Insert the kick reason into warn_reasons
        reason_stmt = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"
        # Add a prefix/indicator to distinguish kick reasons if needed, e.g., f"[KICK] {reason}"
        cur.execute(reason_stmt, (user_id, reason)) # Store kick reason

        conn.commit()
        log.debug(f"Added kick for user {user_id} with reason: {reason}")
        return jsonify({"message": "Kick recorded successfully", "user_id": user_id, "reason": reason}), 201
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, "Failed to record kick", "Add Kick")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in add_kick: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/kicks/<string:user_id>/<path:reason>', methods=['DELETE'])
@mod_required
def delete_kick(user_id, reason):
    """Deletes one instance of a specific kick reason for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500

    decoded_reason = unquote(reason)

    try:
       # Check if the reason exists
        count_stmt = "SELECT COUNT(*) as count FROM warn_reasons WHERE user_id=%s AND reason=%s"
        cur.execute(count_stmt, (user_id, decoded_reason))
        count_result = cur.fetchone()
        reason_exists_count = count_result['count'] if count_result else 0

        if reason_exists_count == 0:
            return jsonify({"message": f"No kick with reason '{decoded_reason}' found for user {user_id} to delete"}), 404

        # Delete one instance of the reason
        # Replace 'id' with your actual primary key or timestamp column if different
        del_reason_stmt = """
            DELETE FROM warn_reasons
            WHERE user_id=%s AND reason=%s
            ORDER BY id DESC LIMIT 1
        """
        cur.execute(del_reason_stmt, (user_id, decoded_reason))
        deleted_reason_count = cur.rowcount

        if deleted_reason_count == 0:
            conn.rollback()
            log.warning(f"Kick reason delete query affected 0 rows for user {user_id}, reason '{decoded_reason}'. Rolling back.")
            return jsonify({"error": "Failed to delete kick reason instance, possibly due to concurrent modification."}), 500

        # Decrement kick count in warn_user
        update_user_stmt = "UPDATE warn_user SET kicks = GREATEST(kicks - 1, 0) WHERE user_id=%s"
        cur.execute(update_user_stmt, (user_id,))

        conn.commit()
        log.debug(f"Deleted kick reason '{decoded_reason}' for user {user_id}")
        return jsonify({"message": f"Successfully deleted kick reason '{decoded_reason}' for user {user_id}"}), 200

    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, f"Failed to delete kick reason '{decoded_reason}' for user {user_id}", "Delete Kick")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in delete_kick: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@app.route('/api/bans', methods=['POST'])
@mod_required
def add_ban():
    """Adds a ban record for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    user_id = data.get('user_id')
    tag = data.get('tag')
    reason = data.get('reason') # Ban reason stored in warn_reasons

    if not user_id or not tag or not reason:
        return jsonify({"error": "Missing required fields: user_id, tag, reason"}), 400

    try:
        # Update warn_user: Increment bans count
        user_stmt = """
            INSERT INTO warn_user (user_id, warnings, kicks, bans, tag)
            VALUES (%s, 0, 0, 1, %s)
            ON DUPLICATE KEY UPDATE bans = bans + 1, tag = VALUES(tag)
        """
        cur.execute(user_stmt, (user_id, tag))

        # Insert the ban reason into warn_reasons
        reason_stmt = "INSERT INTO warn_reasons (user_id, reason) VALUES (%s, %s)"
        # Add a prefix/indicator like f"[BAN] {reason}" if needed
        cur.execute(reason_stmt, (user_id, reason)) # Store ban reason

        conn.commit()
        log.debug(f"Added ban for user {user_id} with reason: {reason}")
        return jsonify({"message": "Ban recorded successfully", "user_id": user_id, "reason": reason}), 201
    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, "Failed to record ban", "Add Ban")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in add_ban: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@app.route('/api/bans/<string:user_id>/<path:reason>', methods=['DELETE'])
@mod_required
def delete_ban(user_id, reason):
    """Deletes one instance of a specific ban reason for a user."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500

    decoded_reason = unquote(reason)

    try:
        # Check if the reason exists
        count_stmt = "SELECT COUNT(*) as count FROM warn_reasons WHERE user_id=%s AND reason=%s"
        cur.execute(count_stmt, (user_id, decoded_reason))
        count_result = cur.fetchone()
        reason_exists_count = count_result['count'] if count_result else 0

        if reason_exists_count == 0:
            return jsonify({"message": f"No ban with reason '{decoded_reason}' found for user {user_id} to delete"}), 404

        # Delete one instance of the reason
        # Replace 'id' with your actual primary key or timestamp column if different
        del_reason_stmt = """
            DELETE FROM warn_reasons
            WHERE user_id=%s AND reason=%s
            ORDER BY id DESC LIMIT 1
        """
        cur.execute(del_reason_stmt, (user_id, decoded_reason))
        deleted_reason_count = cur.rowcount

        if deleted_reason_count == 0:
            conn.rollback()
            log.warning(f"Ban reason delete query affected 0 rows for user {user_id}, reason '{decoded_reason}'. Rolling back.")
            return jsonify({"error": "Failed to delete ban reason instance, possibly due to concurrent modification."}), 500


        # Decrement ban count in warn_user
        update_user_stmt = "UPDATE warn_user SET bans = GREATEST(bans - 1, 0) WHERE user_id=%s"
        cur.execute(update_user_stmt, (user_id,))

        conn.commit()
        log.debug(f"Deleted ban reason '{decoded_reason}' for user {user_id}")
        return jsonify({"message": f"Successfully deleted ban reason '{decoded_reason}' for user {user_id}"}), 200

    except mariadb.Error as db_error:
        return handle_db_error(conn, db_error, f"Failed to delete ban reason '{decoded_reason}' for user {user_id}", "Delete Ban")
    except Exception as e:
        if conn: conn.rollback()
        log.exception("API Unexpected error in delete_ban: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500


# --- Summary Stats & User Search ---
@app.route('/api/stats/summary', methods=['GET'])
@mod_required # Protect stats endpoint
def get_summary_stats():
    """Retrieves summary statistics from various tables."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    stats = {}
    try:
        cur.execute("SELECT COUNT(*) as count FROM jac")
        stats['jac_count'] = cur.fetchone()['count'] if cur.rowcount > 0 else 0
        cur.execute("SELECT COUNT(*) as count FROM timers WHERE mute = true")
        stats['active_mutes'] = cur.fetchone()['count'] if cur.rowcount > 0 else 0
        cur.execute("SELECT COUNT(*) as count FROM timers WHERE ban = true")
        stats['active_bans'] = cur.fetchone()['count'] if cur.rowcount > 0 else 0
        cur.execute("SELECT SUM(warnings) as total_warnings, SUM(kicks) as total_kicks, SUM(bans) as total_bans FROM warn_user")
        result = cur.fetchone()
        stats['total_warnings'] = int(result['total_warnings']) if result and result['total_warnings'] else 0
        stats['total_kicks'] = int(result['total_kicks']) if result and result['total_kicks'] else 0
        stats['total_bans_recorded'] = int(result['total_bans']) if result and result['total_bans'] else 0
        return jsonify(stats), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving summary stats: %s", db_error)
        return jsonify({"error": "Failed to retrieve summary statistics", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception("API Unexpected error in get_summary_stats: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500

@app.route('/api/search/user/<string:user_id>', methods=['GET'])
@mod_required # Protect search endpoint
def search_user_records(user_id):
    """Checks for records associated with a specific user_id across tables."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    if not user_id: return jsonify({"error": "User ID parameter is required"}), 400
    results = {}
    try:
        cur.execute("SELECT 1 FROM jac WHERE user_id = %s LIMIT 1", (user_id,))
        results['has_jac'] = cur.fetchone() is not None
        cur.execute("SELECT 1 FROM timers WHERE user_id = %s AND (mute = true OR ban = true) LIMIT 1", (user_id,))
        results['has_active_timer'] = cur.fetchone() is not None
        cur.execute("SELECT 1 FROM warn_user WHERE user_id = %s LIMIT 1", (user_id,))
        results['has_infractions'] = cur.fetchone() is not None
        return jsonify(results), 200
    except mariadb.Error as db_error:
        log.exception(f"API Error searching for user {user_id}: %s", db_error)
        return jsonify({"error": f"Failed to search for user {user_id}", "details": str(db_error)}), 500 # Avoid details in prod
    except Exception as e:
        log.exception(f"API Unexpected error in search_user_records for {user_id}: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500


# --- New Users Tracking Routes ---
@app.route('/api/new-users', methods=['GET'])
@mod_required
def get_all_new_users():
    """Retrieves all tracked new users."""
    conn, cur = get_db_connection()
    if not conn or not cur: return jsonify({"error": "Database connection failed"}), 500
    try:
        statement = "SELECT user_id, msg_count FROM new_users ORDER BY user_id"
        cur.execute(statement)
        new_users = cur.fetchall()
        return jsonify(new_users), 200
    except mariadb.Error as db_error:
        log.exception("API Error retrieving new_users from DB: %s", db_error)
        return jsonify({"error": "Failed to retrieve new users", "details": str(db_error)}), 500
    except Exception as e:
        log.exception("API Unexpected error in get_all_new_users: %s", e)
        return jsonify({"error": "An unexpected server error occurred"}), 500


# --- Static File Serving (No Auth Required) ---
# Keep existing routes for /assets/<path:filename>, /<path:filename>, /

REACT_BUILD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend/dist'))
if not os.path.exists(REACT_BUILD_DIR):
    log.warning(f"React build directory not found at {REACT_BUILD_DIR}. Frontend serving will fail.")

@app.route('/assets/<path:filename>')
def serve_static_assets(filename):
    return send_from_directory(os.path.join(REACT_BUILD_DIR, 'assets'), filename)

@app.route('/<path:filename>')
def serve_root_static(filename):
    # Basic check to prevent serving sensitive files or directory traversal
    if filename.startswith('.') or '/' in filename or '\\' in filename or filename == 'app_py.txt' or filename == '.env':
        abort(404)

    file_path = os.path.join(REACT_BUILD_DIR, filename)
    if os.path.isfile(file_path):
        return send_from_directory(REACT_BUILD_DIR, filename)
    else:
        # Fallback to index.html for client-side routing (React Router etc.)
        index_path = os.path.join(REACT_BUILD_DIR, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(REACT_BUILD_DIR, 'index.html')
        else:
            log.error(f"index.html not found in {REACT_BUILD_DIR}")
            return jsonify({"error": "Frontend entry point not found."}), 404

@app.route('/')
def serve_index():
    """Serves the main index.html file."""
    index_path = os.path.join(REACT_BUILD_DIR, 'index.html')
    if not os.path.exists(index_path):
        log.error(f"index.html not found in {REACT_BUILD_DIR}")
        return jsonify({"error": "Frontend entry point not found."}), 404
    return send_from_directory(REACT_BUILD_DIR, 'index.html')


# --- Main Execution ---
if __name__ == '__main__':
    # Ensure 'logs' directory exists before starting
    if not os.path.exists('logs'):
        try: os.makedirs('logs'); log.debug("Created 'logs' directory.")
        except OSError as e: log.critical(f"Failed to create 'logs' directory: {e}"); sys.exit("Error: Could not create 'logs' directory.")

    log.info("Starting Flask API server with Discord Auth...")
    # Use waitress or gunicorn for production
    # Debug mode should be OFF in production
    app.run(debug=os.getenv('FLASK_ENV') != 'production', host='0.0.0.0', port=5000)
