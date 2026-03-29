"""
Hosted Twitch OAuth helpers for !Clipit
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Any, Dict
from urllib.parse import urlencode

import aiohttp

from logs import get_logger

log = get_logger(__name__)


class OAuthStateStore:
    """In-memory OAuth state store with TTL-based validation."""

    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._states: dict[str, float] = {}

    def issue(self) -> str:
        self._prune()
        state = secrets.token_urlsafe(32)
        self._states[state] = time.time() + self.ttl_seconds
        return state

    def validate(self, state: str | None) -> bool:
        if not state:
            return False

        self._prune()
        expires_at = self._states.pop(state, None)
        return bool(expires_at and expires_at >= time.time())

    def _prune(self):
        now = time.time()
        expired = [state for state, expires_at in self._states.items() if expires_at < now]
        for state in expired:
            self._states.pop(state, None)


class SessionManager:
    """Issue and validate signed session cookies."""

    def __init__(
        self,
        secret: str,
        cookie_name: str = "clipit_session",
        max_age_seconds: int = 60 * 60 * 24 * 30,
    ):
        if not secret:
            raise ValueError("SESSION_SECRET must be configured for authenticated sessions.")
        self.secret = secret.encode("utf-8")
        self.cookie_name = cookie_name
        self.max_age_seconds = max_age_seconds

    def issue(self, broadcaster_id: str, login: str) -> str:
        payload = {
            "broadcaster_id": broadcaster_id,
            "login": login,
            "exp": int(time.time()) + self.max_age_seconds,
        }
        raw_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        encoded_payload = base64.urlsafe_b64encode(raw_payload).decode("ascii")
        signature = self._sign(encoded_payload)
        return f"{encoded_payload}.{signature}"

    def validate(self, token: str | None) -> dict[str, Any] | None:
        if not token or "." not in token:
            return None

        encoded_payload, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, self._sign(encoded_payload)):
            return None

        try:
            raw_payload = base64.urlsafe_b64decode(encoded_payload.encode("ascii"))
            payload = json.loads(raw_payload.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        if "broadcaster_id" not in payload or "login" not in payload:
            return None
        return payload

    def _sign(self, encoded_payload: str) -> str:
        digest = hmac.new(
            self.secret,
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii")


class TwitchAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = "https://id.twitch.tv/oauth2"
        self.api_url = "https://api.twitch.tv/helix"

    def get_auth_url(
        self,
        scopes: list[str] | None = None,
        redirect_uri: str | None = None,
        state: str | None = None,
    ) -> str:
        """Generate a hosted OAuth authorization URL."""
        if scopes is None:
            scopes = ["clips:edit", "chat:read", "chat:edit", "moderator:read:chatters"]

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
        }
        if state:
            params["state"] = state

        return f"{self.base_url}/authorize?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, auth_code: str, redirect_uri: str | None = None
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        url = f"{self.base_url}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri or self.redirect_uri,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    expires_at = int(datetime.now().timestamp()) + token_data["expires_in"]
                    return {
                        "access_token": token_data["access_token"],
                        "refresh_token": token_data["refresh_token"],
                        "expires_at": expires_at,
                    }

                error_text = await response.text()
                log.error(
                    "Token exchange failed: %s - %s",
                    response.status,
                    error_text,
                )
                raise RuntimeError(f"Failed to exchange code for tokens: {error_text}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using a refresh token."""
        url = f"{self.base_url}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    expires_at = int(datetime.now().timestamp()) + token_data["expires_in"]
                    return {
                        "access_token": token_data["access_token"],
                        "refresh_token": token_data.get("refresh_token", refresh_token),
                        "expires_at": expires_at,
                    }

                error_text = await response.text()
                log.error("Token refresh failed: %s - %s", response.status, error_text)
                raise RuntimeError(f"Failed to refresh token: {error_text}")

    async def validate_token(self, access_token: str) -> bool:
        """Validate if access token is still valid."""
        url = f"{self.base_url}/validate"
        headers = {"Authorization": f"OAuth {access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                return response.status == 200

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get authenticated user information."""
        url = f"{self.api_url}/users"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": self.client_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [{}])[0] if data.get("data") else {}

                error_text = await response.text()
                log.error(
                    "Failed to get user info: %s - %s",
                    response.status,
                    error_text,
                )
                return {}
