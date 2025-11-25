"""
Twitch Clip data model for !Clipit
Represents all data associated with a Twitch clip as defined in the Twitch API documentation
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from logs import get_logger; log = get_logger(__name__)


@dataclass
class TwitchClip:
    """Represents a Twitch clip with all data fields from the Twitch API"""
    
    # Required fields
    id: str
    url: str
    embed_url: str
    broadcaster_id: str
    broadcaster_name: str
    creator_id: str
    creator_name: str
    video_id: str
    game_id: str
    language: str
    title: str
    view_count: int
    created_at: str
    thumbnail_url: str
    duration: float
    vod_offset: int
    
    # Optional fields (may be None)
    is_featured: Optional[bool] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    is_mature: Optional[bool] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'TwitchClip':
        """Create a TwitchClip instance from API response data"""
        # Convert created_at string to datetime
        created_at = datetime.strptime(data['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        
        return cls(
            id=data['id'],
            url=data['url'],
            embed_url=data['embed_url'],
            broadcaster_id=data['broadcaster_id'],
            broadcaster_name=data['broadcaster_name'],
            creator_id=data['creator_id'],
            creator_name=data['creator_name'],
            video_id=data['video_id'],
            game_id=data['game_id'],
            language=data['language'],
            title=data['title'],
            view_count=data['view_count'],
            created_at=created_at,
            thumbnail_url=data['thumbnail_url'],
            duration=data['duration'],
            vod_offset=data['vod_offset'],
            is_featured=data.get('is_featured'),
            category_id=data.get('category_id'),
            category_name=data.get('category_name'),
            is_mature=data.get('is_mature')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the TwitchClip instance to a dictionary"""
        return {
            'id': self.id,
            'url': self.url,
            'embed_url': self.embed_url,
            'broadcaster_id': self.broadcaster_id,
            'broadcaster_name': self.broadcaster_name,
            'creator_id': self.creator_id,
            'creator_name': self.creator_name,
            'video_id': self.video_id,
            'game_id': self.game_id,
            'language': self.language,
            'title': self.title,
            'view_count': self.view_count,
            'created_at': self.created_at,
            'thumbnail_url': self.thumbnail_url,
            'duration': self.duration,
            'vod_offset': self.vod_offset,
            'is_featured': self.is_featured,
            'category_id': self.category_id,
            'category_name': self.category_name,
            'is_mature': self.is_mature
        }