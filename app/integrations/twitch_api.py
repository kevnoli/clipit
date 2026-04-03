import asyncio
from typing import Any

import aiohttp

from app.core.logs import get_logger
from app.domain.clip import TwitchClip

log = get_logger(__name__)


class TwitchAPI:
    """Twitch API client for clip generation and stream status."""

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = "https://api.twitch.tv/helix"

    def _get_headers(self) -> dict[str, str]:
        """Get standard API headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

    async def is_stream_live(self, broadcaster_id: str) -> bool:
        """Check if broadcaster is currently live."""
        url = f"{self.base_url}/streams"
        params = {"user_id": broadcaster_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._get_headers(), params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    streams = data.get("data", [])
                    return len(streams) > 0 and streams[0].get("type") == "live"
                log.error("Failed to check stream status: %s", response.status)
                return False

    async def create_clip(self, broadcaster_id: str) -> dict[str, Any] | None:
        """Create a clip for the broadcaster."""
        url = f"{self.base_url}/clips"
        params = {"broadcaster_id": broadcaster_id}
        headers = self._get_headers()

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params) as response:
                if response.status == 202:
                    data = await response.json()
                    clip_data = data.get("data", [])
                    if clip_data:
                        clip_id = clip_data[0].get("id")
                        log.info(f"Clip creation initiated: {clip_id}")
                        return clip_data[0]
                    else:
                        log.error("Clip creation response missing data")
                        return None
                else:
                    error_text = await response.text()
                    log.error(
                        f"Failed to create clip: {response.status} - {error_text}"
                    )
                    return None

    async def get_clip_url(
        self, clip_id: str, max_retries: int = 10, delay: float = 2.0
    ) -> str | None:
        """Get a clip URL by polling for clip data."""
        url = f"{self.base_url}/clips"
        params = {"id": clip_id}

        for attempt in range(max_retries):
            await asyncio.sleep(delay)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=self._get_headers(), params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        clips = data.get("data", [])
                        if clips:
                            clip_url = clips[0].get("url")
                            if clip_url:
                                log.info(f"Clip URL retrieved: {clip_url}")
                                return clip_url
                            else:
                                log.debug(
                                    f"Clip {clip_id} not ready yet (attempt {attempt + 1}/{max_retries})"
                                )
                        else:
                            log.debug(
                                f"Clip {clip_id} not found (attempt {attempt + 1}/{max_retries})"
                            )
                    else:
                        log.warning(f"Failed to get clip data: {response.status}")

        log.error("Failed to get clip URL after %s attempts", max_retries)
        return None

    async def get_clip_data(self, clip_id: str) -> TwitchClip | None:
        """Get complete clip data for a given clip ID."""
        url = f"{self.base_url}/clips"
        params = {"id": clip_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._get_headers(), params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    clips = data.get("data", [])
                    if clips:
                        clip_data = clips[0]
                        return TwitchClip.from_api_response(clip_data)
                    return None
                error_text = await response.text()
                log.error(
                    "Failed to get clip data: %s - %s",
                    response.status,
                    error_text,
                )
                return None

    async def get_twitch_game_name_by_id(self, game_id: str) -> str | None:
        """Get the name of a Twitch game by its ID."""
        url = f"{self.base_url}/games"
        params = {"id": game_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._get_headers(), params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    games = data.get("data", [])
                    if games:
                        return games[0].get("name")
                    return None
                error_text = await response.text()
                log.error(
                    "Failed to get game name: %s - %s",
                    response.status,
                    error_text,
                )
                return None

    async def create_clip_and_get_url(self, broadcaster_id: str) -> str | None:
        """Create a clip and wait for the URL to be available."""
        clip_data = await self.create_clip(broadcaster_id)
        if not clip_data:
            return None

        clip_id = clip_data.get("id")
        if not clip_id:
            return None

        # Wait for clip to be processed and get URL
        clip_url = await self.get_clip_url(clip_id)
        return clip_url
