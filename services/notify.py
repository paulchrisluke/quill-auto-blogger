"""
Discord notification service for story packets, digest summaries, and blog-centric notifications.
"""

import os
import logging
from typing import Dict, Any, List, Optional
import httpx
from dotenv import load_dotenv
from pathlib import Path

from .blog_status import BlogStatusChecker, format_draft_approval_message

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
    """
    Send message to Discord webhook with input validation, character limit handling,
    and mass ping prevention.
    
    Args:
        webhook_url: Discord webhook URL
        content: Message content to send
        
    Returns:
        True if all chunks sent successfully, False otherwise
    """
    # Input validation
    if not webhook_url or not webhook_url.strip():
        logger.error("Discord webhook URL is empty or invalid")
        return False
    
    if not content or not content.strip():
        logger.error("Discord message content is empty or invalid")
        return False
    
    # Split content into chunks if it exceeds Discord's 2000 character limit
    # Leave some buffer for safety (1900 chars)
    max_chunk_size = 1900
    chunks = []
    
    if len(content) <= max_chunk_size:
        chunks = [content]
    else:
        # Split by lines to avoid breaking in the middle of a line
        lines = content.split('\n')
        current_chunk = ""
        
        for line in lines:
            # If adding this line would exceed the limit, start a new chunk
            if len(current_chunk) + len(line) + 1 > max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    # Single line is too long, split it
                    while len(line) > max_chunk_size:
                        chunks.append(line[:max_chunk_size])
                        line = line[max_chunk_size:]
                    current_chunk = line
            else:
                current_chunk += ('\n' + line) if current_chunk else line
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
    
    # Send each chunk sequentially
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            for i, chunk in enumerate(chunks):
                payload = {
                    "content": chunk,
                    "allowed_mentions": {"parse": []}  # Prevent mass pings
                }
                
                response = client.post(webhook_url, json=payload)
                
                # Check for non-2xx responses
                if response.status_code < 200 or response.status_code >= 300:
                    logger.error(f"Discord webhook failed with status {response.status_code}: {response.text}")
                    return False
                
                logger.info(f"Discord notification chunk {i+1}/{len(chunks)} sent successfully")
            
            logger.info(f"All {len(chunks)} Discord notification chunks sent successfully")
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


def notify_draft_approval(date: str, webhook_url: str = None) -> bool:
    """
    Send Discord notification for draft approval workflow.
    
    Args:
        date: Date in YYYY-MM-DD format
        webhook_url: Discord webhook URL (optional, uses env var if not provided)
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        if not webhook_url:
            webhook_url = get_webhook_url()
        
        if not webhook_url:
            logger.error("No Discord webhook URL available")
            return False
        
        checker = BlogStatusChecker()
        draft_info = checker.get_draft_info(date)
        
        if not draft_info:
            logger.warning(f"No draft found for {date}")
            return False
        
        message = format_draft_approval_message(draft_info)
        
        # Send with interaction buttons (Discord components)
        payload = {
            "content": message,
            "components": [
                {
                    "type": 1,  # Action row
                    "components": [
                        {
                            "type": 2,  # Button
                            "style": 3,  # Success (green)
                            "label": "✅ Approve & Publish",
                            "custom_id": f"approve_blog_{date}"
                        },
                        {
                            "type": 2,  # Button
                            "style": 2,  # Secondary (gray)
                            "label": "📝 Needs Edits",
                            "custom_id": f"edit_blog_{date}"
                        }
                    ]
                }
            ],
            "allowed_mentions": {"parse": []}
        }
        
        return _send_discord_webhook_with_payload(webhook_url, payload)
        
    except Exception as e:
        logger.error(f"Failed to send draft approval notification: {e}")
        return False


def notify_blog_published(date: str, webhook_url: str = None) -> bool:
    """
    Send Discord notification when a blog is published.
    
    Args:
        date: Date in YYYY-MM-DD format
        webhook_url: Discord webhook URL (optional, uses env var if not provided)
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        if not webhook_url:
            webhook_url = get_webhook_url()
        
        if not webhook_url:
            logger.error("No Discord webhook URL available")
            return False
        
        checker = BlogStatusChecker()
        
        # Get blog info from FINAL digest
        final_path = Path("blogs") / date / f"FINAL-{date}_digest.json"
        if not final_path.exists():
            logger.warning(f"FINAL digest not found for {date}")
            return False
        
        import json
        with open(final_path, 'r', encoding='utf-8') as f:
            digest = json.load(f)
        
        frontmatter = digest.get("frontmatter", {})
        title = frontmatter.get("title", "Untitled")
        story_count = len(digest.get("story_packets", []))
        
        # Get blog URL from environment
        blog_base_url = os.getenv("BLOG_BASE_URL", "https://example.com").rstrip("/")
        blog_url = f"{blog_base_url}/blog/{date}"
        
        message = (
            f"✅ **Blog Published** — {date}\n\n"
            f"**Title:** {title}\n"
            f"**Stories:** {story_count} story packets\n\n"
            f"📖 **Read the blog:** {blog_url}"
        )
        
        return _send_discord_webhook(webhook_url, message)
        
    except Exception as e:
        logger.error(f"Failed to send blog published notification: {e}")
        return False


def _send_discord_webhook_with_payload(webhook_url: str, payload: Dict) -> bool:
    """
    Send Discord webhook with custom payload (for components/interactions).
    
    Args:
        webhook_url: Discord webhook URL
        payload: Custom payload dictionary
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(webhook_url, json=payload)
            
            if response.status_code < 200 or response.status_code >= 300:
                logger.error(f"Discord webhook failed with status {response.status_code}: {response.text}")
                return False
            
            logger.info("Discord notification with payload sent successfully")
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
