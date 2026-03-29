"""
Configuration management for !Clipit
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv

from logs import get_logger

log = get_logger(__name__)

# Load .env variables if present
load_dotenv()


@dataclass(slots=True)
class BroadcasterConfig:
    commands: List[str]
    minimum_votes: int
    command_window: int
    command_cooldown: int
    vote_permissions: str
    subscriber_months: str
    override_permissions: str
    discord_webhook_url: str
    donotallowlist_enabled: bool
    donotallowlist_usernames: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BroadcasterConfig":
        commands = [
            str(cmd).strip() for cmd in data.get("commands", ["!clipit"]) if str(cmd).strip()
        ]
        return cls(
            commands=commands or ["!clipit"],
            minimum_votes=int(data.get("minimum_votes", 2)),
            command_window=int(data.get("command_window", 15)),
            command_cooldown=int(data.get("command_cooldown", 30)),
            vote_permissions=str(data.get("vote_permissions", "Everyone")),
            subscriber_months=str(data.get("subscriber_months", "SUB:3")),
            override_permissions=str(data.get("override_permissions", "Owner")),
            discord_webhook_url=str(data.get("discord_webhook_url", "")),
            donotallowlist_enabled=bool(data.get("donotallowlist_enabled", False)),
            donotallowlist_usernames=[
                str(username).strip().lower()
                for username in data.get("donotallowlist_usernames", [])
                if str(username).strip()
            ],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commands": self.commands,
            "minimum_votes": self.minimum_votes,
            "command_window": self.command_window,
            "command_cooldown": self.command_cooldown,
            "vote_permissions": self.vote_permissions,
            "subscriber_months": self.subscriber_months,
            "override_permissions": self.override_permissions,
            "discord_webhook_url": self.discord_webhook_url,
            "donotallowlist_enabled": self.donotallowlist_enabled,
            "donotallowlist_usernames": self.donotallowlist_usernames,
        }


class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please copy config.yaml.example to {self.config_path} and fill in your values."
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f) or {}

        self._validate_config()

    def _validate_config(self):
        required_fields = [
            "twitch.client_id",
            "twitch.client_secret",
            "commands",
            "donotallowlist.enabled",
            "donotallowlist.usernames",
            "voting.minimum_votes",
            "voting.command_window",
            "voting.command_cooldown",
            "permissions.vote_permissions",
            "permissions.override_permissions",
        ]

        for field in required_fields:
            if field in ("twitch.client_id", "twitch.client_secret"):
                env_key = field.split(".")[1].upper()
                if os.getenv(f"TWITCH_{env_key}"):
                    continue

            keys = field.split(".")
            value: Any = self.config
            for key in keys:
                if not isinstance(value, dict) or key not in value:
                    raise ValueError(f"Missing required configuration: {field}")
                value = value[key]

    def get(self, path: str, default: Any = None) -> Any:
        keys = path.split(".")
        value: Any = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def _get_bool(self, path: str, default: bool = False) -> bool:
        value = self.get(path, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def twitch_client_id(self) -> str:
        return os.getenv("TWITCH_CLIENT_ID", self.get("twitch.client_id"))

    @property
    def twitch_client_secret(self) -> str:
        return os.getenv("TWITCH_CLIENT_SECRET", self.get("twitch.client_secret"))

    @property
    def session_secret(self) -> str:
        value = os.getenv("SESSION_SECRET", self.get("app.session_secret", "")).strip()
        if not value:
            raise ValueError("SESSION_SECRET must be configured for authenticated sessions.")
        return value

    @property
    def app_base_url(self) -> str:
        value = os.getenv("APP_BASE_URL", self.get("app.base_url", "")).strip()
        return value.rstrip("/")

    @property
    def server_host(self) -> str:
        return os.getenv("HOST", self.get("app.host", "0.0.0.0"))

    @property
    def server_port(self) -> int:
        return int(os.getenv("PORT", self.get("app.port", 8000)))

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_base_url.startswith("https://")

    @property
    def twitch_redirect_path(self) -> str:
        return self.get("twitch.redirect_path", "/auth/twitch/callback")

    @property
    def twitch_redirect_uri(self) -> str:
        if not self.app_base_url:
            raise ValueError(
                "APP_BASE_URL must be configured for hosted Twitch OAuth callbacks."
            )
        return f"{self.app_base_url}{self.twitch_redirect_path}"

    @property
    def broadcaster_channel(self) -> str | None:
        channel = self.get("twitch.broadcaster_channel")
        return channel.lower() if isinstance(channel, str) and channel else None

    @property
    def commands(self) -> List[str]:
        return self.get("commands", ["!clipit"])

    @property
    def minimum_votes(self) -> int:
        return self.get("voting.minimum_votes", 2)

    @property
    def command_window(self) -> int:
        return self.get("voting.command_window", 15)

    @property
    def command_cooldown(self) -> int:
        return self.get("voting.command_cooldown", 30)

    @property
    def vote_permissions(self) -> str:
        return self.get("permissions.vote_permissions", "Everyone")

    @property
    def subscriber_months(self) -> str:
        return self.get("permissions.subscriber_months", "SUB:3")

    @property
    def override_permissions(self) -> str:
        return self.get("permissions.override_permissions", "Owner")

    @property
    def discord_webhook_url(self) -> str:
        return self.get("discord.webhook_url", "")

    @property
    def donotallowlist_enabled(self) -> bool:
        return self._get_bool("donotallowlist.enabled", False)

    @property
    def donotallowlist_usernames(self) -> List[str]:
        return self.get("donotallowlist.usernames", [])

    def default_broadcaster_config(self) -> BroadcasterConfig:
        return BroadcasterConfig(
            commands=[cmd.strip() for cmd in self.commands if cmd.strip()] or ["!clipit"],
            minimum_votes=self.minimum_votes,
            command_window=self.command_window,
            command_cooldown=self.command_cooldown,
            vote_permissions=self.vote_permissions,
            subscriber_months=self.subscriber_months,
            override_permissions=self.override_permissions,
            discord_webhook_url=self.discord_webhook_url,
            donotallowlist_enabled=self.donotallowlist_enabled,
            donotallowlist_usernames=[
                str(username).strip().lower()
                for username in self.donotallowlist_usernames
                if str(username).strip()
            ],
        )
