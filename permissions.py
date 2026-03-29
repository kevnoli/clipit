"""
User permission system for !Clipit
Handles role detection and permission checking
"""

from typing import Optional

from twitchio import User

from logs import get_logger

log = get_logger(__name__)


class PermissionChecker:
    """Check user permissions based on role hierarchy."""

    # Lower number = higher permission.
    PERMISSION_LEVELS = {
        "Owner": 1,
        "Broadcaster": 1,
        "Moderator": 600,
        "VIP": 700,
        "Subscriber": 800,
        "Everyone": 1000,
    }

    PERMISSION_ALIASES = {
        "owner": "Owner",
        "broadcaster": "Broadcaster",
        "moderator": "Moderator",
        "moderators": "Moderator",
        "vip": "VIP",
        "vips": "VIP",
        "subscriber": "Subscriber",
        "subscribers": "Subscriber",
        "everyone": "Everyone",
    }

    def __init__(self, config):
        self.config = config
        self.vote_permission_level = self._parse_permission(config.vote_permissions)
        self.override_permission_level = self._parse_permission(
            config.override_permissions
        )
        self.subscriber_months = self._parse_subscriber_months(config.subscriber_months)

    def _normalize_permission(self, permission_str: str) -> str:
        normalized = (permission_str or "Everyone").strip().lower()
        return self.PERMISSION_ALIASES.get(normalized, "Everyone")

    def _parse_permission(self, permission_str: str) -> int:
        """Parse permission string to level."""
        if permission_str.startswith("SUB:"):
            return self.PERMISSION_LEVELS["Subscriber"]
        return self.PERMISSION_LEVELS[self._normalize_permission(permission_str)]

    def _parse_subscriber_months(self, sub_str: str) -> Optional[int]:
        """Parse subscriber months requirement (e.g. SUB:3 -> 3)."""
        if sub_str and sub_str.startswith("SUB:"):
            try:
                return int(sub_str.split(":", 1)[1])
            except (ValueError, IndexError):
                return None
        return None

    def get_user_permission_level(self, user: User, broadcaster_name: str) -> int:
        """Get permission level for a user."""
        username_lower = user.name.lower()
        broadcaster_lower = broadcaster_name.lower()

        if username_lower == broadcaster_lower:
            return self.PERMISSION_LEVELS["Owner"]
        if getattr(user, "is_mod", False):
            return self.PERMISSION_LEVELS["Moderator"]
        if getattr(user, "is_vip", False):
            return self.PERMISSION_LEVELS["VIP"]
        if getattr(user, "is_subscriber", False):
            return self.PERMISSION_LEVELS["Subscriber"]
        return self.PERMISSION_LEVELS["Everyone"]

    def _subscriber_requirement_met(self, user: User) -> bool:
        if not getattr(user, "is_subscriber", False):
            return False
        if self.subscriber_months is None:
            return True

        months = getattr(user, "subscriber_months", None)
        return isinstance(months, int) and months >= self.subscriber_months

    def can_vote(self, user: User, broadcaster_name: str) -> bool:
        """Check if user can vote based on the configured permission level."""
        if self.vote_permission_level == self.PERMISSION_LEVELS["Subscriber"]:
            return self._subscriber_requirement_met(user)

        user_level = self.get_user_permission_level(user, broadcaster_name)
        return user_level <= self.vote_permission_level

    def has_override_permission(self, user: User, broadcaster_name: str) -> bool:
        """Check if user can instantly trigger a clip."""
        if self.override_permission_level == self.PERMISSION_LEVELS["Subscriber"]:
            return self._subscriber_requirement_met(user)

        user_level = self.get_user_permission_level(user, broadcaster_name)
        return user_level <= self.override_permission_level
