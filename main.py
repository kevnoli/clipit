"""
Main entry point for !Clipit
Handles authentication, initialization, and bot startup
"""
import asyncio
import argparse
from logs import get_logger; log = get_logger(__name__)
import logs
import sys
from datetime import datetime
from typing import Tuple, Optional

from config import Config
from database import Database
from auth import TwitchAuth
from bot import ClipitBot
from twitch_api import TwitchAPI

import sys
import io
import signal
import platform


# Set stdout to handle Unicode properly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Helper routine to handle SIGINT from user – module level
async def _shutdown(sig: signal.Signals, bot: ClipitBot):
    log.info(f"Received Shutdown sig - {sig} – shutting down gracefully")
    await bot.close()
    await asyncio.sleep(0.1)

    # Grab the *current* running loop and stop it
    loop = asyncio.get_running_loop()
    loop.stop()


async def authenticate(config: Config, database: Database, force_reauth: bool = False) -> str:
    """Handle Twitch authentication
    
    Args:
        config: Configuration object
        database: Database object
        force_reauth: If True, clear existing tokens and force reauthentication
    """
    auth = TwitchAuth(
        client_id=config.twitch_client_id,
        client_secret=config.twitch_client_secret
    )

    # If force reauth is requested, clear existing tokens
    if force_reauth:
        log.info("Force reauthentication requested - clearing existing tokens")
        database.clear_tokens()
        tokens = None
    else:
        # Check for existing tokens
        tokens = database.get_tokens()
    
    access_token = None

    if tokens:
        # Check if token is still valid
        expires_at = tokens['expires_at']
        current_time = int(datetime.now().timestamp())

        if current_time < expires_at - 300:  # Refresh if expires in less than 5 minutes
            # Token is still valid
            access_token = tokens['access_token']
            log.info("Using existing access token")
        else:
            # Token expired or expiring soon, refresh it
            log.info("Refreshing access token")
            try:
                new_tokens = await auth.refresh_access_token(tokens['refresh_token'])
                database.save_tokens(
                    new_tokens['access_token'],
                    new_tokens['refresh_token'],
                    new_tokens['expires_at']
                )
                access_token = new_tokens['access_token']
                log.info("Access token refreshed successfully")
            except Exception as e:
                log.error(f"Failed to refresh token: {e}")
                tokens = None

    if not access_token:
        # Need to authenticate
        log.info("No valid tokens found, starting authentication flow")
        auth_code = await auth.get_auth_code()

        if not auth_code:
            log.error("Authentication failed or was cancelled")
            sys.exit(1)

        # Exchange code for tokens
        tokens = await auth.exchange_code_for_tokens(auth_code)
        database.save_tokens(
            tokens['access_token'],
            tokens['refresh_token'],
            tokens['expires_at']
        )
        access_token = tokens['access_token']
        log.info("Authentication successful")

    return access_token


async def get_user_ids(config: Config, access_token: str) -> Tuple[str, str, Optional[str]]:
    """Get broadcaster ID and bot user ID"""
    api = TwitchAPI(config.twitch_client_id, access_token)
    
    # Get broadcaster ID
    broadcaster_id = await api.get_broadcaster_id(config.broadcaster_channel)
    if not broadcaster_id:
        log.error(f"Failed to get broadcaster ID for {config.broadcaster_channel}")
        sys.exit(1)

    # Get bot user ID (the authenticated user)
    bot_user_info = await api.get_user_info()
    if not bot_user_info or 'id' not in bot_user_info:
        log.error("Failed to get bot user ID")
        sys.exit(1)
    
    bot_id = bot_user_info['id']
    bot_username = bot_user_info.get('login', None)
    
    log.info(f"Broadcaster ID: {broadcaster_id}")
    log.info(f"Bot User ID: {bot_id}")
    if bot_username:
        log.info(f"Bot Username: {bot_username}")
    return broadcaster_id, bot_id, bot_username

async def main():
    """Main application entry point"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='!Clipit - Twitch clip generation bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Start bot with existing tokens, ERROR level
  python main.py --force-auth       # Force reauthentication
  python main.py -v                 # Verbose (DEBUG) logging
  python main.py --log-level INFO   # Explicitly set to INFO
        """
    )
    parser.add_argument(
        '--force-auth', '--reauth',
        action='store_true',
        help='Force reauthentication by clearing existing tokens'
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default INFO if not supplied)."
    )
    
    args = parser.parse_args()
    
    # Resolve log level  --log-level
    level=args.log_level or "INFO"
    logs.init_logging(level=level,include_ascii_art=True)
    
    try:
        
        if args.force_auth:
            log.info("Force reauthentication flag detected")
        
        # Load configuration
        config = Config()
        log.info("Configuration loaded")

        # Initialize database
        database = Database()
        log.info("Database initialized")

        # Authenticate
        access_token = await authenticate(config, database, force_reauth=args.force_auth)

        # Get broadcaster ID, bot ID, and bot username
        # If we get a 401 error, clear tokens and re-authenticate
        try:
            broadcaster_id, bot_id, bot_username = await get_user_ids(config, access_token)
        except ValueError as e:
            if str(e) == "INVALID_TOKEN_401":
                log.warning("Access token is invalid (401), clearing tokens and re-authenticating...")
                database.clear_tokens()
                # Re-authenticate
                access_token = await authenticate(config, database)
                # Try again with new token
                broadcaster_id, bot_id, bot_username = await get_user_ids(config, access_token)
            else:
                raise

        # Create and run bot
        bot = ClipitBot(
            config,
            database,
            TwitchAuth(
                config.twitch_client_id,
                config.twitch_client_secret
            ),
            access_token,
            broadcaster_id,
            bot_id,
            bot_username
        )

        # Register signal handlers (note diffs in UNIX vs Windows environemts)
        if platform.system() == "Windows":
            # Windows fallback – use the standard signal module
            def _signal_handler(signum, frame):
                # Schedule the shutdown coroutine on the event loop
                asyncio.get_running_loop().call_soon_threadsafe(
                    asyncio.create_task, _shutdown(signum, bot)
                )

            signal.signal(signal.SIGINT,  _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        else:
            # Unix – asyncio supports add_signal_handler
            loop = asyncio.get_running_loop()
            for s in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    s,
                    lambda s=s: asyncio.create_task(_shutdown(s, bot))
                )

        await bot.start()

    except KeyboardInterrupt:
        log.info("Bot stopped by user")
    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

