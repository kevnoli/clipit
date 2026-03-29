"""
Twitch API client for !Clipit
Handles clip generation, stream status, and user information
"""

import aiohttp
from logs import get_logger
import asyncio
from typing import Optional, Dict, Any

from clip import TwitchClip  # Import the new clips module

log = get_logger(__name__)


class TwitchAPI:
    """Twitch API client for clip generation and stream status"""

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = "https://api.twitch.tv/helix"

    def _get_headers(self) -> Dict[str, str]:
        """Get standard API headers"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

    async def is_stream_live(self, broadcaster_id: str) -> bool:
        """Check if broadcaster is currently live"""
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
                else:
                    log.error(f"Failed to check stream status: {response.status}")
                    return False

    async def get_broadcaster_id(self, broadcaster_name: str) -> Optional[str]:
        """Get broadcaster user ID from username"""
        url = f"{self.base_url}/users"
        params = {"login": broadcaster_name.lower()}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._get_headers(), params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    users = data.get("data", [])
                    if users:
                        return users[0].get("id")
                elif response.status == 401:
                    # Unauthorized - token is invalid
                    error_text = await response.text()
                    log.error(
                        f"Unauthorized (401) - Invalid access token: {error_text}"
                    )
                    raise ValueError("INVALID_TOKEN_401")
                else:
                    log.error(f"Failed to get broadcaster ID: {response.status}")
                return None

    async def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get authenticated user information"""
        url = f"{self.base_url}/users"
        headers = self._get_headers()

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    users = data.get("data", [])
                    if users:
                        return users[0]
                elif response.status == 401:
                    # Unauthorized - token is invalid
                    error_text = await response.text()
                    log.error(
                        f"Unauthorized (401) - Invalid access token: {error_text}"
                    )
                    raise ValueError("INVALID_TOKEN_401")
                else:
                    error_text = await response.text()
                    log.error(
                        f"Failed to get user info: {response.status} - {error_text}"
                    )
                return None

    async def create_clip(self, broadcaster_id: str) -> Optional[Dict[str, Any]]:
        """Create a clip for the broadcaster"""
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
    ) -> Optional[str]:
        """
        Get clip URL by polling for clip data
        Clips take time to process, so we need to poll
        """
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

        log.error(f"Failed to get clip URL after {max_retries} attempts")
        return None

    async def get_clip_thumbnail(self, clip_id: str) -> Optional[str]:
        """Get clip thumbnail URL from clip data"""
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
                        # Return the thumbnail URL from the first clip
                        thumbnail_url = clips[0].get("thumbnail_url")
                        if thumbnail_url:
                            log.info(f"Clip thumbnail URL retrieved: {thumbnail_url}")
                            return thumbnail_url
                else:
                    log.error(f"Failed to get clip thumbnail: {response.status}")
                return None

    async def get_clip_data(self, clip_id: str) -> Optional[TwitchClip]:
        """
        Get complete clip data for a given clip ID

        Args:
            clip_id (str): The ID of the clip to retrieve

        Returns:
            Optional[TwitchClip]: A TwitchClip instance with all clip data, or None if failed
        """
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
                        # Create and return TwitchClip instance from the first clip
                        clip_data = clips[0]
                        return TwitchClip.from_api_response(clip_data)
                    else:
                        log.error(f"No clip data found for ID: {clip_id}")
                        return None
                else:
                    error_text = await response.text()
                    log.error(
                        f"Failed to get clip data: {response.status} - {error_text}"
                    )
                    return None

    async def get_twitch_game_name_by_id(self, game_id: str) -> Optional[str]:
        """
        Get the name of a Twitch game by its ID

        Args:
            game_id (str): The ID of the Twitch game

        Returns:
            Optional[str]: The name of the game, or None if not found
        """
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
                    else:
                        log.error(f"No game data found for ID: {game_id}")
                        return None
                else:
                    error_text = await response.text()
                    log.error(
                        f"Failed to get game name: {response.status} - {error_text}"
                    )
                    return None

    async def create_clip_and_get_url(self, broadcaster_id: str) -> Optional[str]:
        """Create a clip and wait for URL to be available"""
        clip_data = await self.create_clip(broadcaster_id)
        if not clip_data:
            return None

        clip_id = clip_data.get("id")
        if not clip_id:
            return None

        # Wait for clip to be processed and get URL
        clip_url = await self.get_clip_url(clip_id)
        return clip_url
