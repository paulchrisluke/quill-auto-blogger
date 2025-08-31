#!/usr/bin/env python3
"""
Discord notifier for story packets (M1.5).
Sends Discord webhook messages for story recording prompts.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List
import httpx
import logging

logger = logging.getLogger(__name__)


def notify_discord(webhook_url: str, content: str) -> bool:
    """Send message to Discord webhook."""
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0)
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


def format_story_message(packet: Dict[str, Any]) -> str:
    """Format a story packet into a Discord message."""
    title = packet.get("title_human") or packet.get("title_raw", "Untitled")
    pr_url = packet.get("links", {}).get("pr_url", "")
    
    lines = [
        f"📹 **Time to record** — {title}",
        f"PR: {pr_url}" if pr_url else "",
        "Suggested flow:",
        "1) What shipped  2) Why it matters  3) One detail"
    ]
    
    # Filter out empty lines
    return "\n".join(line for line in lines if line.strip())


def notify_from_digest(date: str, webhook_url: str = None) -> None:
    """Send Discord notifications for all story packets in a digest."""
    # Load digest
    digest_path = Path(f"blogs/{date}/PRE-CLEANED-{date}_digest.json")
    
    if not digest_path.exists():
        logger.error(f"Digest not found: {digest_path}")
        return
    
    try:
        with open(digest_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Could not load digest {digest_path}: {e}")
        return
    
    story_packets = data.get("story_packets", [])
    if not story_packets:
        logger.info("No story packets found in digest")
        return
    
    # Get webhook URL from environment if not provided
    if not webhook_url:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    success_count = 0
    total_count = len(story_packets)
    
    for packet in story_packets:
        message = format_story_message(packet)
        
        if webhook_url:
            # Send to Discord
            if notify_discord(webhook_url, message):
                success_count += 1
        else:
            # Print to stdout
            print(message)
            print("---")
            success_count += 1
    
    if webhook_url:
        logger.info(f"Sent {success_count}/{total_count} Discord notifications")
    else:
        logger.info(f"Printed {success_count}/{total_count} story prompts to stdout")


def main():
    """Main entry point for command line usage."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python discord_notifier.py YYYY-MM-DD")
        sys.exit(1)
    
    date = sys.argv[1]
    
    # Validate date format
    try:
        from datetime import datetime
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        print("Error: Date must be in YYYY-MM-DD format")
        sys.exit(1)
    
    # Send notifications
    try:
        notify_from_digest(date)
    except Exception as e:
        print(f"Error sending notifications: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
