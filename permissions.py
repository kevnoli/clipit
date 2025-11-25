"""
User permission system for !Clipit
Handles role detection and permission checking
"""
from logs import get_logger; log = get_logger(__name__)
from typing import Optional
from twitchio import User


class PermissionChecker:
    """Check user permissions based on role hierarchy"""

    # Permission hierarchy (lower number = higher permission)
    PERMISSION_LEVELS = {
        'Owner': 1,
        'Broadcaster': 1,
        'Moderator': 600,
        'VIP': 700,
        'Subscriber': 800,
        'Everyone': 1000
    }

    def __init__(self, config):
        self.config = config
        self.vote_permission_level = self._parse_permission(config.vote_permissions)
        self.override_permission_level = self._parse_permission(config.override_permissions)
        self.subscriber_months = self._parse_subscriber_months(config.subscriber_months)

    def _parse_permission(self, permission_str: str) -> int:
        """Parse permission string to level"""
        if permission_str.startswith('SUB:'):
            return self.PERMISSION_LEVELS['Subscriber']
        return self.PERMISSION_LEVELS.get(permission_str, self.PERMISSION_LEVELS['Everyone'])

    def _parse_subscriber_months(self, sub_str: str) -> Optional[int]:
        """Parse subscriber months requirement (e.g., SUB:3 -> 3)"""
        if sub_str and sub_str.startswith('SUB:'):
            try:
                return int(sub_str.split(':')[1])
            except (ValueError, IndexError):
                return None
        return None

    def get_user_permission_level(self, user: User, broadcaster_name: str) -> int:
        """Get permission level for a user"""
        username_lower = user.name.lower()
        broadcaster_lower = broadcaster_name.lower()

        # Check if user is broadcaster/owner
        if username_lower == broadcaster_lower:
            return self.PERMISSION_LEVELS['Owner']

        # Check if user is moderator
        if user.is_mod:
            return self.PERMISSION_LEVELS['Moderator']

        # Check if user is VIP
        if hasattr(user, 'is_vip') and user.is_vip:
            return self.PERMISSION_LEVELS['VIP']

        # Check if user is subscriber
        if user.is_subscriber:
            # Check subscriber months if required
            if self.subscriber_months and hasattr(user, 'subscriber_months'):
                if user.subscriber_months >= self.subscriber_months:
                    return self.PERMISSION_LEVELS['Subscriber']
                else:
                    return self.PERMISSION_LEVELS['Everyone']
            return self.PERMISSION_LEVELS['Subscriber']

        return self.PERMISSION_LEVELS['Everyone']

    def can_vote(self, user: User, broadcaster_name: str) -> bool:
        """Check if user can vote based on vote_permissions setting"""
        user_level = self.get_user_permission_level(user, broadcaster_name)
        required_level = self.vote_permission_level

        # If vote_permissions is Subscribers with month requirement
        if self.config.vote_permissions.startswith('SUB:'):
            if user_level == self.PERMISSION_LEVELS['Subscriber']:
                if self.subscriber_months and hasattr(user, 'subscriber_months'):
                    return user.subscriber_months >= self.subscriber_months
                return True
            return False

        # General permission check (user level must be <= required level)
        return user_level <= required_level

    def has_override_permission(self, user: User, broadcaster_name: str) -> bool:
        """Check if user has override permission (can instantly trigger clip)"""
        user_level = self.get_user_permission_level(user, broadcaster_name)
        override_level = self.override_permission_level

        # If override_permissions is Subscribers with month requirement
        if self.config.override_permissions.startswith('SUB:'):
            if user_level == self.PERMISSION_LEVELS['Subscriber']:
                if self.subscriber_months and hasattr(user, 'subscriber_months'):
                    return user.subscriber_months >= self.subscriber_months
                return True
            return False

        # General permission check
        return user_level <= override_level

