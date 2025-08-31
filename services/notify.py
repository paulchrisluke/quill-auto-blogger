"""
Discord notification service for story packets and digest summaries.
"""

import os
import logging
from typing import Dict, Any, List, Optional
import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def notify_story_discord(packet: Dict[str, Any], date: str, webhook_url: str) -> bool:
    """
    Send Discord notification for a single story packet.
    
    Args:
        packet: Story packet dictionary
        date: Date string
        webhook_url: Discord webhook URL
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        # Extract packet data
        title = packet.get("title_human") or packet.get("title_raw", "Untitled")
        pr_url = packet.get("links", {}).get("pr_url", "")
        video_path = packet.get("video", {}).get("path", "")
        highlights = packet.get("highlights", [])
        video_status = packet.get("video", {}).get("status", "pending")
        
        # Status emoji
        status_emoji = {
            "rendered": "✅",
            "failed": "⚠️",
            "pending": "⏳",
            "rendering": "⏳"
        }.get(video_status, "⏳")
        
        # Build message
        lines = [
            f"{status_emoji} **{title}**",
            "",
        ]
        
        # Add highlights
        if highlights:
            lines.append("**Highlights:**")
            for highlight in highlights[:3]:  # Max 3 highlights
                lines.append(f"• {highlight}")
            lines.append("")
        
        # Add links
        if pr_url:
            lines.append(f"**PR:** {pr_url}")
        if video_path:
            lines.append(f"**Video:** {video_path}")
        
        message = "\n".join(lines)
        
        # Send to Discord
        return _send_discord_webhook(webhook_url, message)
        
    except Exception as e:
        logger.error(f"Failed to send story notification: {e}")
        return False


def notify_digest_summary(date: str, count: int, url: str, webhook_url: str) -> bool:
    """
    Send Discord notification for digest summary.
    
    Args:
        date: Date string
        count: Number of stories
        url: Blog URL
        webhook_url: Discord webhook URL
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        message = (
            f"📊 **Daily Devlog Summary — {date}**\n\n"
            f"Shipped {count} {'story' if count == 1 else 'stories'} today!\n\n"
            f"📖 **Read the full devlog:** {url}"
        )
        
        return _send_discord_webhook(webhook_url, message)
        
    except Exception as e:
        logger.error(f"Failed to send digest summary: {e}")
        return False


def _send_discord_webhook(webhook_url: str, content: str) -> bool:
    """Send message to Discord webhook."""
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(webhook_url, json={"content": content})
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Discord webhook failed: {e.response.text}")
        return False
    except httpx.RequestError as e:
        logger.error(f"Discord webhook request failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Discord notification: {e}")
        return False


def get_webhook_url() -> Optional[str]:
    """Get Discord webhook URL from environment."""
    return os.getenv("DISCORD_WEBHOOK_URL")
