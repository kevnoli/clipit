"""
Main Twitch bot for !Clipit
Handles chat connection, message processing, and clip generation for one broadcaster
"""

import time
from typing import Awaitable, Callable

from twitchio.ext import commands

from app.db import Database
from app.core.logs import get_logger
from app.domain.permissions import PermissionChecker
from app.domain.voting import VotingSystem
from app.integrations.discord import DiscordWebhook
from app.integrations.twitch_api import TwitchAPI
from app.models import BroadcasterSettings

log = get_logger(__name__)

ApiFactory = Callable[[], Awaitable[TwitchAPI]]
RuntimeFailureCallback = Callable[[str], Awaitable[None]]


class ClipitBot(commands.Bot):
    """Bot runtime for a single broadcaster installation."""

    def __init__(
        self,
        config: BroadcasterSettings,
        database: Database,
        access_token: str,
        broadcaster_id: str,
        bot_id: str,
        twitch_client_id: str,
        twitch_client_secret: str,
        bot_username: str | None = None,
        broadcaster_name: str | None = None,
        api_factory: ApiFactory | None = None,
        runtime_failure_callback: RuntimeFailureCallback | None = None,
    ):
        irc_token = access_token[6:] if access_token.startswith("oauth:") else access_token
        channel_name = (broadcaster_name or bot_username or "").lower()

        if not channel_name:
            raise ValueError("ClipitBot requires a broadcaster channel name")

        log.info("Connecting to channel: %s", channel_name)
        super().__init__(
            token=irc_token,
            client_id=twitch_client_id,
            client_secret=twitch_client_secret,
            bot_id=bot_id,
            prefix="!",
            initial_channels=[channel_name],
        )

        self.config = config
        self.database = database
        self.broadcaster_id = broadcaster_id
        self.broadcaster_name = channel_name
        self.bot_username = bot_username
        self._api_factory = api_factory
        self._runtime_failure_callback = runtime_failure_callback

        self.permission_checker = PermissionChecker(config)
        self.voting_system = VotingSystem(config, self.permission_checker)
        self.discord_webhook = DiscordWebhook(config.discord_webhook_url)
        self._channel_cache = None

    async def _get_twitch_api(self) -> TwitchAPI:
        if not self._api_factory:
            raise RuntimeError("No Twitch API factory configured for broadcaster bot")
        return await self._api_factory()

    async def event_ready(self):
        if self.bot_username:
            log.info("Bot ready for %s as %s", self.broadcaster_name, self.bot_username)
        else:
            log.info("Bot ready for %s", self.broadcaster_name)

    async def event_channel_join_failure(self, channel: str):
        log.error(
            "Failed to join channel %s for broadcaster %s",
            channel,
            self.broadcaster_name,
        )
        if self._runtime_failure_callback is not None:
            await self._runtime_failure_callback(
                f'channel "{channel}" could not be joined'
            )

    async def event_error(self, error, data=None):
        log.error("TwitchIO error occurred for %s: %s", self.broadcaster_name, error)
        if data:
            log.error("Error data: %s", data)

    async def event_message(self, message):
        if message.echo:
            return

        user_name = message.author.name if message.author else "unknown"
        content = (message.content or "").strip()
        if not content:
            return

        log.debug(
            "[%s] Message from %s: %s",
            self.broadcaster_name,
            user_name,
            content[:100],
        )

        if not self._channel_cache and hasattr(message, "channel"):
            self._channel_cache = message.channel

        if content.lower() == "!clipitstatus":
            is_mod = getattr(message.author, "is_mod", False) if message.author else False
            is_broadcaster = (
                getattr(message.author, "is_broadcaster", False) if message.author else False
            )
            if is_mod or is_broadcaster:
                await self._send_message(
                    f"/me @{user_name} Clipit is online for {self.broadcaster_name}."
                )
            return

        words = content.split(maxsplit=1)
        if not words:
            return

        first_word = words[0].lower()
        command_prefix = next(
            (cmd for cmd in self.config.commands if cmd.lower().strip() == first_word),
            None,
        )
        if not command_prefix:
            return

        comment = words[1].strip() if len(words) > 1 else ""
        log.info("Processing vote from %s in %s", user_name, self.broadcaster_name)
        await self._process_vote(message.author, comment)

    async def _process_vote(self, user, comment: str):
        try:
            vote_result = self.voting_system.add_vote(user, comment, self.broadcaster_name)

            if vote_result["should_trigger"]:
                api = await self._get_twitch_api()
                is_live = await api.is_stream_live(self.broadcaster_id)
                if not is_live:
                    await self._send_message(
                        f"@{user.name} The broadcaster must be live to create clips!"
                    )
                    log.info(
                        "Clip request denied for %s: broadcaster not live",
                        self.broadcaster_name,
                    )
                    return

                await self._generate_clip(vote_result["votes"], vote_result["is_override"])
                return

            reason = vote_result.get("reason", "unknown")
            if reason == "vote_added":
                await self._send_message(
                    f"@{user.name} Vote recorded! ({vote_result['vote_count']}/{self.config.minimum_votes} votes needed)"
                )
            elif reason == "cooldown":
                remaining = vote_result.get("cooldown_remaining", 0.0)
                await self._send_message(
                    f"@{user.name} Clip cooldown active for another {remaining:.0f}s."
                )
        except Exception as exc:
            log.error(
                "Error processing vote for %s: %s",
                self.broadcaster_name,
                exc,
                exc_info=True,
            )

    async def _generate_clip(self, votes, is_override: bool):
        try:
            api = await self._get_twitch_api()
            log.info(
                "Generating clip for %s (votes: %s, override: %s)",
                self.broadcaster_name,
                len(votes),
                is_override,
            )
            start_time = time.time()
            clip_url = await api.create_clip_and_get_url(self.broadcaster_id)
            if not clip_url:
                await self._send_message("Failed to generate clip. Please try again later.")
                log.error("Failed to generate clip for %s", self.broadcaster_name)
                return

            generation_time = time.time() - start_time
            comments = self.voting_system.get_concatenated_comments(votes)
            voters = self.voting_system.get_voter_list(votes)

            clip_id = clip_url.split("/")[-1] if "/" in clip_url else ""
            clip_data = await api.get_clip_data(clip_id) if clip_id else None
            thumbnail_url = clip_data.thumbnail_url if clip_data else ""
            game_directory = (
                await api.get_twitch_game_name_by_id(clip_data.game_id)
                if clip_data and clip_data.game_id
                else None
            )

            message = f"Clip generated: {clip_url}"
            if comments:
                message += f" | Comments: {comments}"

            await self._send_message(message)
            await self.discord_webhook.send_clip_notification(
                clip_url=clip_url,
                comments=comments,
                broadcaster_name=self.broadcaster_name,
                clip_title=clip_data.title if clip_data else "Clip Generated via Chat",
                directory=game_directory or "Unknown",
                voters=voters,
                time_to_generate=generation_time,
                time_into_broadcast=clip_data.created_at if clip_data else "N/A",
                thumbnail_url=thumbnail_url,
            )

            self.database.save_clip_statistics(
                clip_id=clip_id,
                clip_url=clip_url,
                voters=voters,
                comments=comments,
                created_by=voters[0] if voters else "unknown",
                time_to_generate=generation_time,
                time_into_broadcast=clip_data.created_at if clip_data else "N/A",
                broadcaster_id=self.broadcaster_id,
                broadcaster_name=self.broadcaster_name,
                clip_title=clip_data.title if clip_data else "Clip Generated via Chat",
                directory=game_directory or "Twitch Chat",
                thumbnail_url=thumbnail_url,
            )
            self.voting_system.mark_clip_generated()
            log.info("Clip generated successfully for %s: %s", self.broadcaster_name, clip_url)
        except Exception as exc:
            log.error(
                "Error generating clip for %s: %s",
                self.broadcaster_name,
                exc,
                exc_info=True,
            )
            await self._send_message("An error occurred while generating the clip.")

    async def _send_message(self, message: str):
        try:
            channel = self._channel_cache
            if channel:
                await channel.send(message)
                return

            channels = await self.fetch_channels([self.broadcaster_name])
            if channels:
                self._channel_cache = channels[0]
                await self._channel_cache.send(message)
                return

            log.warning(
                "Could not find channel %s to send message: %s",
                self.broadcaster_name,
                message,
            )
        except Exception as exc:
            log.error(
                "Error sending message to %s: %s",
                self.broadcaster_name,
                exc,
                exc_info=True,
            )
