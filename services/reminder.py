from __future__ import annotations
import os, json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import schedule, time
from typing import Dict, List

from .blog_status import BlogStatusChecker, format_daily_rollup_message, format_weekly_backlog_message, format_missing_reminder_message

DATA_DIR = Path("blogs")

def _post_discord(msg: str) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        import httpx
        with httpx.Client(timeout=5) as client:
            client.post(
                webhook_url, 
                json={
                    "content": msg,
                    "allowed_mentions": {"parse": []}  # Block @everyone/@here
                }
            )
    except (httpx.RequestError, httpx.TimeoutException) as e:
        # Log the error but don't crash the reminder service
        print(f"Discord webhook error: {e}")

def daily_rollup_report() -> None:
    """Send daily rollup report at 9am UTC."""
    checker = BlogStatusChecker(DATA_DIR)
    
    # Check yesterday's blog status
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    rollup = checker.get_daily_rollup(yesterday)
    
    message = format_daily_rollup_message(rollup)
    _post_discord(message)

def weekly_backlog_report() -> None:
    """Send weekly backlog report on Mondays."""
    checker = BlogStatusChecker(DATA_DIR)
    
    # Get backlog for past 7 days
    end_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    backlog = checker.get_weekly_backlog(end_date)
    
    message = format_weekly_backlog_message(backlog)
    _post_discord(message)

def missing_blog_reminder() -> None:
    """Check for missing blogs and send reminders."""
    checker = BlogStatusChecker(DATA_DIR)
    
    # Check yesterday for missing blog
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if checker.is_missing(yesterday):
        message = format_missing_reminder_message(yesterday)
        _post_discord(message)

def scan_and_notify() -> None:
    """Legacy story-level scanning - kept for backward compatibility."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Guard against missing data directory
    if not DATA_DIR.exists():
        return
    
    for day_dir in DATA_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        # Look for PRE-CLEANED digests in the YYYY-MM-DD subdirectories
        for digest_path in sorted(day_dir.glob("PRE-CLEANED-*digest.json")):
            try:
                obj = json.loads(digest_path.read_text())
            except Exception:
                continue
            for p in obj.get("story_packets", []):
                exp = p.get("explainer", {})
                req = exp.get("required", False)
                status = exp.get("status", "missing")
                merged_at = p.get("merged_at")
                if not (req and status == "missing" and merged_at):
                    continue
                try:
                    merged_dt = datetime.fromisoformat(merged_at.replace("Z","+00:00"))
                    # Ensure merged_dt is timezone-aware and in UTC
                    if merged_dt.tzinfo is None:
                        merged_dt = merged_dt.replace(tzinfo=timezone.utc)
                    else:
                        merged_dt = merged_dt.astimezone(timezone.utc)
                except Exception:
                    continue
                if merged_dt < cutoff:
                    _post_discord(f"⏰ Reminder: `{p.get('id')}` **{p.get('title_human','Story')}** still needs an explainer. Try `/record_start {p.get('id')}`.")
                    
def run_forever():
    # Blog-centric scheduling
    schedule.every().day.at("09:00").do(daily_rollup_report)  # 9am UTC daily
    schedule.every().monday.at("09:00").do(weekly_backlog_report)  # Monday 9am UTC
    schedule.every().day.at("10:00").do(missing_blog_reminder)  # 10am UTC daily
    
    # Legacy story-level scanning (can be removed later)
    schedule.every(30).minutes.do(scan_and_notify)
    
    while True:
        schedule.run_pending()
        time.sleep(10)

if __name__ == "__main__":
    run_forever()
