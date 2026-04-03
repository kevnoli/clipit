"""
Hosted Twitch OAuth helpers for !Clipit
"""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import aiohttp
from cryptography.fernet import Fernet, InvalidToken

from app.core.logs import get_logger

log = get_logger(__name__)


class OAuthStateStore:
    """In-memory OAuth state store with TTL-based validation."""

    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._states: dict[str, tuple[float, str]] = {}

    def issue(self, browser_binding: str) -> str:
        self._prune()
        state = secrets.token_urlsafe(32)
        self._states[state] = (
            time.time() + self.ttl_seconds,
            self._binding_digest(browser_binding),
        )
        return state

    def validate(self, state: str | None, browser_binding: str | None) -> bool:
        if not state or not browser_binding:
            return False

        self._prune()
        record = self._states.pop(state, None)
        if record is None:
            return False
        expires_at, binding_digest = record
        return expires_at >= time.time() and hmac.compare_digest(
            binding_digest,
            self._binding_digest(browser_binding),
        )

    def _binding_digest(self, browser_binding: str) -> str:
        return hashlib.sha256(browser_binding.encode("utf-8")).hexdigest()

    def _prune(self):
        now = time.time()
        expired = [
            state for state, (expires_at, _) in self._states.items() if expires_at < now
        ]
        for state in expired:
            self._states.pop(state, None)


class SecretBox:
    marker = "enc:"

    def __init__(self, secret: str):
        if not secret:
            raise ValueError("A secret is required to encrypt broadcaster credentials.")
        derived_key = base64.urlsafe_b64encode(
            hashlib.sha256(secret.encode("utf-8")).digest()
        )
        self.fernet = Fernet(derived_key)

    def encrypt(self, value: str) -> str:
        if not value or value.startswith(self.marker):
            return value
        encrypted = self.fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{self.marker}{encrypted}"

    def decrypt(self, value: str) -> str:
        if not value or not value.startswith(self.marker):
            return value
        try:
            return self.fernet.decrypt(
                value.removeprefix(self.marker).encode("ascii")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored secret could not be decrypted.") from exc

    def is_encrypted(self, value: str) -> bool:
        return bool(value) and value.startswith(self.marker)


class SessionManager:
    """Issue and validate revocable database-backed app sessions."""

    def __init__(
        self,
        database: Any,
        secret: str,
        cookie_name: str = "clipit_session",
        max_age_seconds: int = 60 * 60 * 24 * 30,
    ):
        if not secret:
            raise ValueError("SESSION_SECRET must be configured for authenticated sessions.")
        self.database = database
        self.secret = secret.encode("utf-8")
        self.cookie_name = cookie_name
        self.max_age_seconds = max_age_seconds

    def issue(self, broadcaster_id: str, login: str) -> tuple[str, str]:
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + self.max_age_seconds
        self.database.save_session(
            session_token=session_token,
            broadcaster_id=broadcaster_id,
            login=login,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        return session_token, csrf_token

    def validate(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        session = self.database.get_session(token)
        if session is None:
            return None
        if int(session.expires_at) < int(time.time()):
            self.database.delete_session(token)
            return None
        if self.database.get_broadcaster(session.broadcaster_id) is None:
            self.database.delete_session(token)
            return None
        return {
            "broadcaster_id": session.broadcaster_id,
            "login": session.login,
            "csrf_token": session.csrf_token,
            "exp": session.expires_at,
        }

    def invalidate(self, token: str | None):
        if token:
            self.database.delete_session(token)

    def invalidate_broadcaster(self, broadcaster_id: str):
        self.database.delete_sessions_for_broadcaster(broadcaster_id)


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
    ) -> dict[str, Any]:
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

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
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

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
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
