"""
Voting system for !Clipit
Handles vote tracking, cooldowns, and command windows
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from twitchio import User

from logs import get_logger

log = get_logger(__name__)


@dataclass
class Vote:
    """Represents a single vote."""

    user: str
    comment: str
    timestamp: float
    user_obj: User | None = None


class VotingSystem:
    """Manages voting system with cooldowns and command windows."""

    def __init__(self, config, permission_checker):
        self.config = config
        self.permission_checker = permission_checker
        self.current_votes: List[Vote] = []
        self.last_clip_time: Optional[float] = None
        self.first_vote_time: Optional[float] = None

    def is_on_cooldown(self) -> bool:
        """Check if the system is on cooldown."""
        if self.last_clip_time is None:
            return False

        elapsed = time.time() - self.last_clip_time
        return elapsed < self.config.command_cooldown

    def get_cooldown_remaining(self) -> float:
        if self.last_clip_time is None:
            return 0.0
        return max(0.0, self.config.command_cooldown - (time.time() - self.last_clip_time))

    def reset_votes(self):
        """Reset vote tracking."""
        self.current_votes = []
        self.first_vote_time = None
        log.debug("Vote tracking reset")

    def check_command_window_expired(self) -> bool:
        """Check if the command window has expired."""
        if self.first_vote_time is None:
            return False

        elapsed = time.time() - self.first_vote_time
        if elapsed > self.config.command_window:
            log.debug(
                "Command window expired (%.1fs > %ss)",
                elapsed,
                self.config.command_window,
            )
            return True
        return False

    def add_vote(self, user: User, comment: str, broadcaster_name: str) -> Dict[str, Any]:
        """Add a vote and return status information."""
        if self.is_on_cooldown():
            remaining = self.get_cooldown_remaining()
            log.debug("System on cooldown, %.1fs remaining", remaining)
            return {
                "should_trigger": False,
                "vote_count": len(self.current_votes),
                "votes": self.current_votes,
                "is_override": False,
                "reason": "cooldown",
                "cooldown_remaining": remaining,
            }

        if self.check_command_window_expired():
            self.reset_votes()

        if self.config.donotallowlist_enabled:
            for blocked_user in self.config.donotallowlist_usernames:
                if str(blocked_user).lower() == str(user.name).lower():
                    log.info("User %s is on the do-not-allow list", user.name)
                    return {
                        "should_trigger": False,
                        "vote_count": len(self.current_votes),
                        "votes": self.current_votes,
                        "is_override": False,
                        "reason": "do_not_allow_list",
                    }

        if self.permission_checker.has_override_permission(user, broadcaster_name):
            log.info("Override user %s triggered clip", user.name)
            override_vote = Vote(
                user=user.name,
                comment=comment,
                timestamp=time.time(),
                user_obj=user,
            )
            all_votes = self.current_votes + [override_vote]
            return {
                "should_trigger": True,
                "vote_count": len(all_votes),
                "votes": all_votes,
                "is_override": True,
                "reason": "override",
            }

        if not self.permission_checker.can_vote(user, broadcaster_name):
            log.debug("User %s does not have permission to vote", user.name)
            return {
                "should_trigger": False,
                "vote_count": len(self.current_votes),
                "votes": self.current_votes,
                "is_override": False,
                "reason": "no_permission",
            }

        existing_vote = next(
            (v for v in self.current_votes if v.user.lower() == user.name.lower()), None
        )
        if existing_vote:
            log.debug("User %s already voted", user.name)
            return {
                "should_trigger": False,
                "vote_count": len(self.current_votes),
                "votes": self.current_votes,
                "is_override": False,
                "reason": "already_voted",
            }

        if self.first_vote_time is None:
            self.first_vote_time = time.time()

        vote = Vote(
            user=user.name,
            comment=comment,
            timestamp=time.time(),
            user_obj=user,
        )
        self.current_votes.append(vote)

        log.info(
            "Vote added by %s (total: %s/%s)",
            user.name,
            len(self.current_votes),
            self.config.minimum_votes,
        )

        should_trigger = len(self.current_votes) >= self.config.minimum_votes
        return {
            "should_trigger": should_trigger,
            "vote_count": len(self.current_votes),
            "votes": self.current_votes.copy(),
            "is_override": False,
            "reason": "vote_added",
        }

    def mark_clip_generated(self):
        """Mark that a clip was generated and start the cooldown."""
        self.last_clip_time = time.time()
        self.reset_votes()
        log.info("Clip generated, cooldown started")

    def get_concatenated_comments(self, votes: List[Vote]) -> str:
        """Concatenate comments from votes with | separator."""
        if not votes:
            return ""

        comments = []
        for vote in votes:
            comment_text = getattr(vote, "comment", "") or ""
            if isinstance(comment_text, str) and comment_text.strip():
                comments.append(comment_text.strip())

        return " | ".join(comments) if comments else ""

    def get_voter_list(self, votes: List[Vote]) -> List[str]:
        """Get list of voter usernames."""
        return [vote.user for vote in votes]
