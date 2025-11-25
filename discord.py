"""
Discord webhook integration for !Clipit
"""
import aiohttp
from typing import Optional, List
from datetime import datetime
from logs import get_logger; log = get_logger(__name__)


class DiscordWebhook:
    """Handle Discord webhook messages"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url and webhook_url.strip())

    async def send_clip_notification(self, clip_url: str, comments: str = "", 
                                   broadcaster_name: str = "", clip_title: str = "",
                                   directory: str = "", voters: List[str] = None,
                                   time_to_generate: float = 0, 
                                   time_into_broadcast: str = "", 
                                   thumbnail_url: str = "", 
                                   clip_id: str = ""):
        """Send clip notification to Discord webhook"""
        if not self.enabled:
            log.debug("Discord webhook not configured, skipping")
            return

        # Format timestamps
        now = datetime.now()
        generated_time = now.strftime("%m/%d/%Y %H:%M:%S")
        
        # Create embed fields
        fields = [
            {
                "name": "Broadcaster",
                "value": f"`{broadcaster_name}`",
                "inline": False
            },
            {
                "name": "Clip Title",
                "value": f"`{clip_title}`",
                "inline": False
            },
            {
                "name": "Directory",
                "value": f"`{directory}`",
                "inline": False
            },
            {
                "name": "Voted By",
                "value": f"`{", ".join(voters) if voters else "None"}`",
                "inline": False
            }
        ]

        # Add comments if they exist
        if comments:
            fields.append({
                "name": "Comments",
                "value": comments,
                "inline": False
            })

        # Add URL and Direct Download
        fields.extend([
            {
                "name": "URL",
                "value": clip_url,
                "inline": False
            }
        ])

        # Add statistics
        fields.extend([
            {
                "name": "Statistics",
                "value": f"Time to generate: {time_to_generate:.2f}s \nGenerated on: {generated_time}",
                "inline": False
            }
        ])

        # Create embed
        embed = {
            "title": f"🎬  New Clip Generated on {generated_time}",
            "description": f"[Watch Clip]({clip_url})",
            "color": 0xFFFF00,  
            "fields": fields,
            "timestamp": now.isoformat()  # This is a string now
        }

        # Add thumbnail image if available
        if thumbnail_url:
            embed["thumbnail"] = {
                "url": thumbnail_url
            }

        payload = {
            "embeds": [embed]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 204:
                        log.info("Discord webhook notification sent successfully")
                    else:
                        error_text = await response.text()
                        log.error(f"Failed to send Discord webhook: {response.status} - {error_text}")
        except Exception as e:
            log.error(f"Error sending Discord webhook: {e}")