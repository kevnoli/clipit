"""
Voting system for !Clipit
Handles vote tracking, cooldowns, and command windows
"""
import time
from logs import get_logger; log = get_logger(__name__)
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from twitchio import User


@dataclass
class Vote:
    """Represents a single vote"""
    user: str
    comment: str
    timestamp: float
    user_obj: User = None


class VotingSystem:
    """Manages voting system with cooldowns and command windows"""

    def __init__(self, config, permission_checker):
        self.config = config
        self.permission_checker = permission_checker
        self.current_votes: List[Vote] = []
        self.last_clip_time: Optional[float] = None
        self.first_vote_time: Optional[float] = None

    def is_on_cooldown(self) -> bool:
        """Check if system is on cooldown"""
        if self.last_clip_time is None:
            return False

        elapsed = time.time() - self.last_clip_time
        return elapsed < self.config.command_cooldown

    def reset_votes(self):
        """Reset vote tracking"""
        self.current_votes = []
        self.first_vote_time = None
        log.debug("Vote tracking reset")

    def check_command_window_expired(self) -> bool:
        """Check if command window has expired"""
        if self.first_vote_time is None:
            return False

        elapsed = time.time() - self.first_vote_time
        if elapsed > self.config.command_window:
            log.debug(f"Command window expired ({elapsed:.1f}s > {self.config.command_window}s)")
            return True
        return False

    def add_vote(self, user: User, comment: str, broadcaster_name: str) -> Dict[str, any]:
        """
        Add a vote and return status information
        Returns dict with: should_trigger, vote_count, votes, is_override
        """
        # Check cooldown
        if self.is_on_cooldown():
            remaining = self.config.command_cooldown - (time.time() - self.last_clip_time)
            log.debug(f"System on cooldown, {remaining:.1f}s remaining")
            return {
                'should_trigger': False,
                'vote_count': len(self.current_votes),
                'votes': self.current_votes,
                'is_override': False,
                'reason': 'cooldown'
            }

        # Check if command window expired
        if self.check_command_window_expired():
            self.reset_votes()

        # Add donotallow check after user validation
        if hasattr(self.config, 'donotallowlist_enabled') and self.config.donotallowlist_enabled:
            for donotallowuser in self.config.donotallowlist_usernames:
                if str(donotallowuser).lower() == str(user.name).lower():
                    log.info(f"User {user.name} is on do not allow list")
                    return {
                        'should_trigger': False,
                        'vote_count': len(self.current_votes),
                        'votes': self.current_votes,
                        'is_override': False,
                        'reason': 'do_not_allow_list'
                    }
                
        # Check override permission
        if self.permission_checker.has_override_permission(user, broadcaster_name):
            log.info(f"Override user {user.name} triggered clip")
            # Include both the override vote AND all previous votes
            override_vote = Vote(user=user.name, comment=comment, timestamp=time.time(), user_obj=user)
            all_votes = self.current_votes + [override_vote]
            return {
                'should_trigger': True,
                'vote_count': len(all_votes),
                'votes': all_votes,
                'is_override': True,
                'reason': 'override'
            }

        # Check if user can vote
        if not self.permission_checker.can_vote(user, broadcaster_name):
            log.debug(f"User {user.name} does not have permission to vote")
            return {
                'should_trigger': False,
                'vote_count': len(self.current_votes),
                'votes': self.current_votes,
                'is_override': False,
                'reason': 'no_permission'
            }

        # Check if user already voted
        existing_vote = next((v for v in self.current_votes if v.user.lower() == user.name.lower()), None)
        if existing_vote:
            log.debug(f"User {user.name} already voted")
            return {
                'should_trigger': False,
                'vote_count': len(self.current_votes),
                'votes': self.current_votes,
                'is_override': False,
                'reason': 'already_voted'
            }

        # Add new vote
        if self.first_vote_time is None:
            self.first_vote_time = time.time()

        vote = Vote(user=user.name, comment=comment, timestamp=time.time(), user_obj=user)
        self.current_votes.append(vote)

        log.info(f"Vote added by {user.name} (total: {len(self.current_votes)}/{self.config.minimum_votes})")

        # Check if minimum votes reached
        should_trigger = len(self.current_votes) >= self.config.minimum_votes

        return {
            'should_trigger': should_trigger,
            'vote_count': len(self.current_votes),
            'votes': self.current_votes.copy(),
            'is_override': False,
            'reason': 'vote_added'
        }

    def mark_clip_generated(self):
        """Mark that a clip was generated (reset votes and set cooldown)"""
        self.last_clip_time = time.time()
        self.reset_votes()
        log.info("Clip generated, cooldown started")

    def get_concatenated_comments(self, votes: List[Vote]) -> str:
        """Concatenate comments from votes with | separator"""
        if not votes:
            return ""
        
        # Extract comments, handling potential None or empty values
        comments = []
        for v in votes:
            # Safely get the comment, defaulting to empty string
            comment_text = getattr(v, 'comment', '') or ''
            if isinstance(comment_text, str) and comment_text.strip():
                comments.append(comment_text.strip())
        
        return " | ".join(comments) if comments else ""

    def get_voter_list(self, votes: List[Vote]) -> List[str]:
        """Get list of voter usernames"""
        return [v.user for v in votes]

