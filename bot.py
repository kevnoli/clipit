"""
Main Twitch bot for !Clipit
Handles chat connection, message processing, and coordinates all components
"""
import asyncio
import time
from typing import Optional
from twitchio.ext import commands

from config import Config
from database import Database
from auth import TwitchAuth
from permissions import PermissionChecker
from voting import VotingSystem
from twitch_api import TwitchAPI
from discord import DiscordWebhook
from clip import TwitchClip 
from logs import get_logger; log = get_logger(__name__)


class ClipitBot(commands.Bot):
    """Main bot class for !Clipit"""

    def __init__(self, config: Config, database: Database, auth: TwitchAuth, 
                 access_token: str, broadcaster_id: str, bot_id: str, bot_username: str = None):
        # Initialize TwitchIO client
        # TwitchIO requires client_id, client_secret, and bot_id
        # IMPORTANT: For IRC chat, twitchio expects the token WITHOUT the "oauth:" prefix
        # The library adds it internally
        # Remove oauth: prefix if present
        irc_token = access_token
        if irc_token.startswith("oauth:"):
            irc_token = irc_token[6:]  # Remove "oauth:" prefix
            log.debug("Removed 'oauth:' prefix from token (twitchio adds it internally)")
        log.debug(f"Initializing bot with token (length: {len(irc_token)})")
        log.info(f"Connecting to channel: {config.broadcaster_channel}")
        
        super().__init__(
            token=irc_token,
            client_id=config.twitch_client_id,
            client_secret=config.twitch_client_secret,
            bot_id=bot_id,
            prefix='!',
            initial_channels=[config.broadcaster_channel]
        )

        self.config = config
        self.database = database
        self.auth = auth
        self.broadcaster_id = broadcaster_id
        self.broadcaster_name = config.broadcaster_channel
        self.bot_username = bot_username
        self._bot_id = bot_id  # Store bot_id for our use

        # Initialize components
        self.permission_checker = PermissionChecker(config)
        self.voting_system = VotingSystem(config, self.permission_checker)
        self.twitch_api = TwitchAPI(config.twitch_client_id, access_token)
        self.discord_webhook = DiscordWebhook(config.discord_webhook_url)

        # Track if broadcaster is live
        self.is_live = False
        
        # Cache for channel object (will be set when first message is received)
        self._channel_cache = None

    async def event_ready(self):
        """Called when bot is ready"""
        if self.bot_username:
            log.info(f"Bot ready! Logged in as {self.bot_username}")
        else:
            log.info("Bot ready!")
        log.info(f"Connected to channel: {self.broadcaster_name}")
        
        # Verbose connection details
        bot_id_display = getattr(self, 'bot_id', None) or getattr(self, '_bot_id', 'unknown')
        log.debug(f"Bot ID: {bot_id_display}")
            
        # Check connection status
        try:
            is_conn = self._connection.is_alive
            log.debug(f"IRC Connection status: {is_conn}")
        except:
            pass
    

        # Start background task to check stream status (removed for now)
        # asyncio.create_task(self._check_stream_status_periodically())

    async def event_error(self, error, data=None):
        """Handle errors from twitchio"""
        log.error(f"TwitchIO error occurred: {error}")
        if data:
            log.error(f"Error data: {data}")
        import traceback
        log.error(f"Error traceback: {traceback.format_exc()}")

    async def _check_stream_status_periodically(self):
        """Periodically check if broadcaster is live"""
        while True:
            try:
                self.is_live = await self.twitch_api.is_stream_live(self.broadcaster_id)
                if self.is_live:
                    log.debug("Broadcaster is live")
                else:
                    log.debug("Broadcaster is offline")
            except Exception as e:
                log.error(f"Error checking stream status: {e}")

            # Check every 30 seconds
            await asyncio.sleep(30)

    async def event_message(self, message):
        """Handle incoming chat messages"""
        # Ignore messages from bot itself
        if message.echo:
            return

        # Verbose logging of all messages
        user_name = message.author.name if message.author else 'unknown'
        log.debug(f"Message from {user_name}: {message.content[:100] if message.content else 'None'}")

        # Cache the channel from the message context for future use
        if not self._channel_cache and hasattr(message, 'channel'):
            self._channel_cache = message.channel
            log.debug(f"Cached channel object from message")

        # Extract user information
        user_name = message.author.name if message.author else 'unknown'
        user_id = getattr(message.author, 'id', None) if message.author else None
        is_mod = getattr(message.author, 'is_mod', False) if message.author else False
        is_subscriber = getattr(message.author, 'is_subscriber', False) if message.author else False
        is_vip = getattr(message.author, 'is_vip', False) if message.author else False
        is_broadcaster = getattr(message.author, 'is_broadcaster', False) if message.author else False
        #subscriber_months = getattr(message.author, 'subscriber_months', None) if message.author else None
        msgtags = getattr(message.author, '_tags', None) if message.author else None
        # get badge info and subscriber months since subscriber_months doesn't seem to be populated as an attribute
        badge_info = msgtags.get('@badge-info') if msgtags else None
        
        # Extract subscriber months if badge-info exists
        subscriber_months = None
        if badge_info and isinstance(badge_info, str):
            # Check if it contains 'subscriber/' 
            if badge_info.startswith('subscriber/'):
                # Extract the number after 'subscriber/'
                try:
                    subscriber_months = int(badge_info.split('/')[1])
                except (ValueError, IndexError):
                    subscriber_months = None

        # Build user attributes (used for verbose logging and command detection)
        user_attrs = []
        if is_broadcaster:
            user_attrs.append("Broadcaster")
        if is_mod:
            user_attrs.append("Mod")
        if is_vip:
            user_attrs.append("VIP")
        if is_subscriber:
            sub_info = f"Sub"
            if subscriber_months is not None:
                sub_info += f"({subscriber_months}mo)"
            user_attrs.append(sub_info)
        if not user_attrs:
            user_attrs.append("Viewer")
        user_attrs_str = ", ".join(user_attrs)
        

        log.debug(
            f"Chat message - User: {user_name} (ID: {user_id}, Roles: {user_attrs_str}) | "
            f"Message: {message.content}" )

        # Check if message starts with any configured command
        message_content = message.content.strip()
        command_found = False
        command_prefix = ""

        # Create a clean list of words from content for command detection
        words = message_content.split(maxsplit=1)
        if not words:
            return
        first_word = words[0].lower()  # The first word (potential command)

        # Check if the first word is one of our commands (not just any prefix!)
        for cmd in self.config.commands:
            # Normalize both strings for comparison
            normalized_cmd = cmd.lower().strip()
            if normalized_cmd == first_word:
                # Found an exact match with our configured command
                command_found = True
                break

        # Check for status command specifically
        if message_content.lower().strip() == '!clipitstatus':
            # Check if user is broadcaster or moderator
            if is_broadcaster or is_mod:
                await self._send_message(f"/me @{user_name} Clipitbot is online. {self.database.get_total_clips_generated()} total clips generated")
                log.info(f"Status command used by {user_name}")
            return

        if not command_found:
            return

        # Extract comment (everything after the command)
        comment = message_content[len(command_prefix):].strip()

        # Process vote
        log.info(f"Processing vote from {user_name}")
        await self._process_vote(message.author, comment)


    async def _process_vote(self, user, comment: str):
        """Process a vote from a user"""
        try:
            # Add vote to voting system
            vote_result = self.voting_system.add_vote(
                user, comment, self.broadcaster_name
            )

            if vote_result['should_trigger']:
                # Check if broadcaster is live
                if not self.is_live:
                    await self._send_message(
                        f"@{user.name} The broadcaster must be live to create clips!"
                    )
                    log.info(f"Clip request denied: broadcaster not live")
                    return

                # Generate clip
                await self._generate_clip(vote_result['votes'], vote_result['is_override'])
            else:
                reason = vote_result.get('reason', 'unknown')
                if reason == 'vote_added':
                    vote_count = vote_result['vote_count']
                    min_votes = self.config.minimum_votes
                    await self._send_message(
                        f"@{user.name} Vote recorded! ({vote_count}/{min_votes} votes needed)"
                    )

        except Exception as e:
            log.error(f"Error processing vote: {e}", exc_info=True)

    async def _generate_clip(self, votes, is_override: bool):
        """Generate a clip and handle the result"""
        try:
            log.info(f"Generating clip (votes: {len(votes)}, override: {is_override})")
            
            # Start timing for statistics
            start_time = time.time()

            # Create clip
            clip_url = await self.twitch_api.create_clip_and_get_url(self.broadcaster_id)

            if not clip_url:
                await self._send_message("Failed to generate clip. Please try again later.")
                log.error("Failed to generate clip")
                return

            # Calculate time to generate
            generation_time = time.time() - start_time

            # Get comments and voters
            comments = self.voting_system.get_concatenated_comments(votes)
            voters = self.voting_system.get_voter_list(votes)
            
            # Get complete clip data using the new TwitchClip class
            clip_id = clip_url.split('/')[-1] if '/' in clip_url else ""
            clip_data: Optional[TwitchClip] = await self.twitch_api.get_clip_data(clip_id)
            
            # Get thumbnail URL for Discord embed
            thumbnail_url = clip_data.thumbnail_url
            

            # Get Directory/Game Name for Discord Embed
            game_directory = await self.twitch_api.get_twitch_game_name_by_id(clip_data.game_id)

            # Format message
            message_parts = [f"🎬 Clip generated: {clip_url}"]
            if comments:
                message_parts.append(f"Comments: {comments}")

            message = " ".join(message_parts)

            # Send to Twitch chat
            await self._send_message(message)

            # Send to Discord with enhanced embed
            await self.discord_webhook.send_clip_notification(
                clip_url=clip_url,
                comments=comments,
                broadcaster_name=self.broadcaster_name,
                clip_title=clip_data.title if clip_data else "Clip Generated via Chat",
                directory=game_directory,
                voters=voters,
                time_to_generate=generation_time,
                time_into_broadcast="N/A",  # This would require additional API calls
                thumbnail_url=thumbnail_url
            )

            # Save to database with additional details
            self.database.save_clip_statistics(
                clip_id=clip_id,
                clip_url=clip_url,
                voters=voters,
                comments=comments,
                created_by=voters[0] if voters else "unknown",
                time_to_generate=generation_time,
                time_into_broadcast=clip_data.created_at if clip_data else "N/A",
                broadcaster_name=self.broadcaster_name,
                clip_title=clip_data.title if clip_data else "Clip Generated via Chat",
                directory="Twitch Chat",
                thumbnail_url=thumbnail_url
            )

            # Mark clip as generated (starts cooldown)
            self.voting_system.mark_clip_generated()

            log.info(f"Clip generated successfully: {clip_url}")

        except Exception as e:
            log.error(f"Error generating clip: {e}", exc_info=True)
            await self._send_message("An error occurred while generating the clip.")

    async def _send_message(self, message: str):
        """Send a message to the channel"""
        try:
            # Use cached channel if available
            channel = self._channel_cache
            
            # If no cached channel, try to get it from message context or adapter
            if not channel:
                # Try to get from adapter
                if hasattr(self, 'adapter') and hasattr(self.adapter, 'get_channel'):
                    try:
                        channel = await self.adapter.get_channel(self.broadcaster_name)
                        if channel:
                            self._channel_cache = channel
                    except Exception:
                        pass
            
            if channel:
                await channel.send(message)
            else:
                log.warning(f"Could not find channel: {self.broadcaster_name} to send message: {message}")
        except Exception as e:
            log.error(f"Error sending message to channel: {e}")
