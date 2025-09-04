#!/usr/bin/env python3
"""
Discord notifier for blog-centric notifications (M8).
Sends Discord webhook messages for blog status reports and approval workflows.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import httpx
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Add services to path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.blog_status import BlogStatusChecker, format_daily_rollup_message, format_weekly_backlog_message, format_draft_approval_message, format_missing_reminder_message
from services.notify import notify_draft_approval, notify_blog_published

# Load environment variables
load_dotenv()

# Compute base directory relative to script location
base_dir = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


def chunk_message(text: str, limit: int = 2000) -> List[str]:
    """Split a message into chunks that fit within Discord's character limit."""
    if len(text) <= limit:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        # If adding this line would exceed the limit, start a new chunk
        if len(current_chunk) + len(line) + 1 > limit:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
                current_chunk = ""
            
            # If a single line is too long, truncate it
            if len(line) > limit:
                chunks.append(line[:limit-3] + "...")
                continue
        
        current_chunk += line + '\n'
    
    # Add the last chunk if it has content
    if current_chunk.strip():
        chunks.append(current_chunk.rstrip())
    
    return chunks


def notify_discord(webhook_url: str, content: str) -> bool:
    """Send message to Discord webhook."""
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(webhook_url, json={"content": content})
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
            return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Rate limited - extract retry time
            retry_after = e.response.headers.get("Retry-After")
            if not retry_after:
                # Try to get from JSON response
                try:
                    error_data = e.response.json()
                    retry_after = error_data.get("retry_after")
                except:
                    retry_after = "unknown"
            
            logger.warning(f"Discord rate limited. Retry after {retry_after} seconds")
            return False
        else:
            logger.exception(f"Discord webhook failed with status {e.response.status_code}")
            return False
    except httpx.RequestError as e:
        logger.exception(f"Discord webhook request failed")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending Discord notification")
        return False


def format_story_message(packet: Dict[str, Any]) -> str:
    """Format a story packet into a Discord message."""
    title = packet.get("title_human") or packet.get("title_raw", "Untitled")
    pr_url = packet.get("links", {}).get("pr_url", "")
    why = packet.get("why", "")
    highlights = packet.get("highlights", [])
    
    # Get mention target from environment
    mention_target = os.getenv("DISCORD_MENTION_TARGET", "")
    
    lines = [
        f"📹 **Time to record** — {title}",
    ]
    
    # Add mention if configured
    if mention_target:
        # If it's just an ID, wrap it in mention format
        if mention_target.isdigit():
            lines.append(f"<@{mention_target}>")
        else:
            # Assume it's already a full mention string
            lines.append(mention_target)
    
    lines.extend([
        "",
        f"**Why this matters:** {why}" if why else "",
        "",
        "**Key points to cover:**",
        "1) What shipped (the feature/fix)",
        "2) Why it matters (impact/value)", 
        "3) One technical detail (implementation highlight)",
        "",
        f"**PR:** {pr_url}" if pr_url else "",
        "",
        "**Highlights:**" if highlights else "",
    ])
    
    # Add highlights as bullet points
    for highlight in highlights[:3]:  # Max 3 highlights
        lines.append(f"• {highlight}")
    
    # Filter out empty lines
    return "\n".join(line for line in lines if line.strip())


def notify_blog_status(date: str, webhook_url: str = None, dry_run: bool = False) -> None:
    """Send Discord notification for blog status (published/draft/missing)."""
    checker = BlogStatusChecker(base_dir / "blogs")
    
    # Get webhook URL from environment if not provided
    if not webhook_url:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if webhook_url:
        logger.info("Discord webhook configured")
    else:
        logger.warning("No Discord webhook URL found, printing to stdout")
    
    # Get blog status
    rollup = checker.get_daily_rollup(date)
    message = format_daily_rollup_message(rollup)
    
    if dry_run:
        print(message)
        print("---")
        logger.info(f"DRY RUN: Printed blog status for {date}")
    elif webhook_url:
        if notify_discord(webhook_url, message):
            logger.info(f"Sent blog status notification for {date}")
        else:
            logger.error(f"Failed to send blog status notification for {date}")
    else:
        print(message)
        print("---")
        logger.info(f"Printed blog status for {date}")


def notify_draft_for_approval(date: str, webhook_url: str = None, dry_run: bool = False) -> None:
    """Send Discord notification for draft approval workflow."""
    # Get webhook URL from environment if not provided
    if not webhook_url:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if webhook_url:
        logger.info("Discord webhook configured")
    else:
        logger.warning("No Discord webhook URL found, printing to stdout")
    
    if dry_run:
        checker = BlogStatusChecker(base_dir / "blogs")
        draft_info = checker.get_draft_info(date)
        if draft_info:
            message = format_draft_approval_message(draft_info)
            print(message)
            print("---")
            logger.info(f"DRY RUN: Printed draft approval message for {date}")
        else:
            logger.warning(f"No draft found for {date}")
    elif webhook_url:
        if notify_draft_approval(date, webhook_url):
            logger.info(f"Sent draft approval notification for {date}")
        else:
            logger.error(f"Failed to send draft approval notification for {date}")
    else:
        checker = BlogStatusChecker(base_dir / "blogs")
        draft_info = checker.get_draft_info(date)
        if draft_info:
            message = format_draft_approval_message(draft_info)
            print(message)
            print("---")
            logger.info(f"Printed draft approval message for {date}")
        else:
            logger.warning(f"No draft found for {date}")


def notify_weekly_backlog(end_date: str = None, webhook_url: str = None, dry_run: bool = False) -> None:
    """Send Discord notification for weekly backlog report."""
    if not end_date:
        end_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    checker = BlogStatusChecker(base_dir / "blogs")
    
    # Get webhook URL from environment if not provided
    if not webhook_url:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if webhook_url:
        logger.info("Discord webhook configured")
    else:
        logger.warning("No Discord webhook URL found, printing to stdout")
    
    # Get backlog report
    backlog = checker.get_weekly_backlog(end_date)
    message = format_weekly_backlog_message(backlog)
    
    if dry_run:
        print(message)
        print("---")
        logger.info(f"DRY RUN: Printed weekly backlog report ending {end_date}")
    elif webhook_url:
        if notify_discord(webhook_url, message):
            logger.info(f"Sent weekly backlog report ending {end_date}")
        else:
            logger.error(f"Failed to send weekly backlog report ending {end_date}")
    else:
        print(message)
        print("---")
        logger.info(f"Printed weekly backlog report ending {end_date}")


def notify_missing_blog(date: str, webhook_url: str = None, dry_run: bool = False) -> None:
    """Send Discord notification for missing blog reminder."""
    # Get webhook URL from environment if not provided
    if not webhook_url:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if webhook_url:
        logger.info("Discord webhook configured")
    else:
        logger.warning("No Discord webhook URL found, printing to stdout")
    
    message = format_missing_reminder_message(date)
    
    if dry_run:
        print(message)
        print("---")
        logger.info(f"DRY RUN: Printed missing blog reminder for {date}")
    elif webhook_url:
        if notify_discord(webhook_url, message):
            logger.info(f"Sent missing blog reminder for {date}")
        else:
            logger.error(f"Failed to send missing blog reminder for {date}")
    else:
        print(message)
        print("---")
        logger.info(f"Printed missing blog reminder for {date}")


def main():
    """Main entry point for command line usage."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python discord_notifier.py status YYYY-MM-DD [--dry-run]")
        print("  python discord_notifier.py draft YYYY-MM-DD [--dry-run]")
        print("  python discord_notifier.py backlog [YYYY-MM-DD] [--dry-run]")
        print("  python discord_notifier.py missing YYYY-MM-DD [--dry-run]")
        sys.exit(1)
    
    command = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    
    try:
        if command == "status":
            if len(sys.argv) < 3:
                print("Error: status command requires a date")
                sys.exit(1)
            date = sys.argv[2]
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
            notify_blog_status(date, dry_run=dry_run)
            
        elif command == "draft":
            if len(sys.argv) < 3:
                print("Error: draft command requires a date")
                sys.exit(1)
            date = sys.argv[2]
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
            notify_draft_for_approval(date, dry_run=dry_run)
            
        elif command == "backlog":
            end_date = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
            if end_date:
                # Validate date format
                datetime.strptime(end_date, "%Y-%m-%d")
            notify_weekly_backlog(end_date, dry_run=dry_run)
            
        elif command == "missing":
            if len(sys.argv) < 3:
                print("Error: missing command requires a date")
                sys.exit(1)
            date = sys.argv[2]
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
            notify_missing_blog(date, dry_run=dry_run)
            
        else:
            print(f"Error: Unknown command '{command}'")
            print("Available commands: status, draft, backlog, missing")
            sys.exit(1)
            
    except ValueError as e:
        if "time data" in str(e):
            print("Error: Date must be in YYYY-MM-DD format")
        else:
            print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
