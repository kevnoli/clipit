"""
Configuration management for !Clipit
"""
import yaml
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from logs import get_logger; log = get_logger(__name__)

# Load .env variables if present
load_dotenv()

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self):
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please copy config.yaml.example to {self.config_path} and fill in your values."
            )

        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Validate required fields
        self._validate_config()

    def _validate_config(self):
        """Validate that required configuration fields are present."""
        required_fields = [
            'twitch.client_id',
            'twitch.client_secret',
            'twitch.broadcaster_channel',
            'commands',
            'donotallowlist.enabled',
            'donotallowlist.usernames',
            'voting.minimum_votes',
            'voting.command_window',
            'voting.command_cooldown',
            'permissions.vote_permissions',
            'permissions.override_permissions'
        ]

        for field in required_fields:
            # Skip validation for client_id / client_secret if env var is set
            if field in ('twitch.client_id', 'twitch.client_secret'):
                env_key = field.split('.')[1].upper()  # client_id -> CLIENT_ID
                if os.getenv(f"TWITCH_{env_key}"):
                    continue
            keys = field.split('.')
            value = self.config
            for key in keys:
                if key not in value:
                    raise ValueError(f"Missing required configuration: {field}")
                value = value[key]

    def get(self, path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    @property
    def twitch_client_id(self) -> str:
        """Return the Twitch client ID – env var overrides YAML."""
        return os.getenv('TWITCH_CLIENT_ID', self.get('twitch.client_id'))

    @property
    def twitch_client_secret(self) -> str:
        """Return the Twitch client secret – env var overrides YAML."""
        return os.getenv('TWITCH_CLIENT_SECRET', self.get('twitch.client_secret'))

    @property
    def broadcaster_channel(self) -> str:
        return self.get('twitch.broadcaster_channel').lower()

    @property
    def commands(self) -> List[str]:
        return self.get('commands', ['!clipit'])

    @property
    def minimum_votes(self) -> int:
        return self.get('voting.minimum_votes', 2)

    @property
    def command_window(self) -> int:
        return self.get('voting.command_window', 15)

    @property
    def command_cooldown(self) -> int:
        return self.get('voting.command_cooldown', 30)

    @property
    def vote_permissions(self) -> str:
        return self.get('permissions.vote_permissions', 'Everyone')

    @property
    def subscriber_months(self) -> str:
        return self.get('permissions.subscriber_months', 'SUB:3')

    @property
    def override_permissions(self) -> str:
        return self.get('permissions.override_permissions', 'Owner')

    @property
    def discord_webhook_url(self) -> str:
        return self.get('discord.webhook_url', '')
    
    @property
    def donotallowlist_enabled(self) -> bool:
        return self.get('donotallowlist.enabled', 'False')

    @property
    def donotallowlist_usernames(self) -> List[str]:
        return self.get('donotallowlist.usernames', [])

