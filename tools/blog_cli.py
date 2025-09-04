#!/usr/bin/env python3
"""
Blog-centric CLI tool for M8.
Provides commands for blog status checking and approval workflows.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add services to path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.blog_status import BlogStatusChecker
from services.notify import notify_draft_approval, notify_blog_published
from services.blog import BlogDigestBuilder


def check_status(date: str):
    """Check blog status for a given date."""
    checker = BlogStatusChecker()
    
    print(f"Blog Status for {date}:")
    print(f"  Published: {checker.is_published(date)}")
    print(f"  Draft Only: {checker.is_draft_only(date)}")
    print(f"  Missing: {checker.is_missing(date)}")
    print(f"  Status: {checker.get_blog_status(date)}")
    
    if checker.is_draft_only(date):
        draft_info = checker.get_draft_info(date)
        if draft_info:
            print(f"  Draft Title: {draft_info['title']}")
            print(f"  Story Count: {draft_info['story_count']}")


def approve_draft(date: str):
    """Approve a draft and create FINAL digest."""
    checker = BlogStatusChecker()
    
    if not checker.is_draft_only(date):
        print(f"Error: No draft found for {date}")
        return False
    
    try:
        # Create FINAL digest using BlogDigestBuilder
        builder = BlogDigestBuilder()
        final_digest = builder.create_final_digest(date)
        
        if final_digest:
            print(f"✅ Created FINAL digest for {date}")
            
            # Send published notification
            if notify_blog_published(date):
                print(f"✅ Sent published notification for {date}")
            else:
                print(f"⚠️ Failed to send published notification for {date}")
            
            return True
        else:
            print(f"❌ Failed to create FINAL digest for {date}")
            return False
            
    except Exception as e:
        print(f"❌ Error approving draft for {date}: {e}")
        return False


def request_approval(date: str):
    """Send draft approval request to Discord."""
    checker = BlogStatusChecker()
    
    if not checker.is_draft_only(date):
        print(f"Error: No draft found for {date}")
        return False
    
    try:
        if notify_draft_approval(date):
            print(f"✅ Sent approval request for {date}")
            return True
        else:
            print(f"❌ Failed to send approval request for {date}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending approval request for {date}: {e}")
        return False


def weekly_report(end_date: str = None):
    """Generate weekly backlog report."""
    if not end_date:
        end_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    checker = BlogStatusChecker()
    backlog = checker.get_weekly_backlog(end_date)
    
    print(f"Weekly Blog Report ({backlog['period']}):")
    print(f"  Published: {backlog['summary']['published']}")
    print(f"  Drafts: {backlog['summary']['draft']}")
    print(f"  Missing: {backlog['summary']['missing']}")
    
    if backlog['draft_details']:
        print("\nDrafts awaiting approval:")
        for draft in backlog['draft_details']:
            print(f"  • {draft['date']}: {draft['title']} ({draft['story_count']} stories)")
    
    if backlog['missing_dates']:
        print("\nMissing blogs:")
        for date in backlog['missing_dates']:
            print(f"  • {date}")


def main():
    """Main entry point for command line usage."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python blog_cli.py status YYYY-MM-DD")
        print("  python blog_cli.py approve YYYY-MM-DD")
        print("  python blog_cli.py request-approval YYYY-MM-DD")
        print("  python blog_cli.py weekly-report [YYYY-MM-DD]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        if command == "status":
            if len(sys.argv) < 3:
                print("Error: status command requires a date")
                sys.exit(1)
            date = sys.argv[2]
            datetime.strptime(date, "%Y-%m-%d")
            check_status(date)
            
        elif command == "approve":
            if len(sys.argv) < 3:
                print("Error: approve command requires a date")
                sys.exit(1)
            date = sys.argv[2]
            datetime.strptime(date, "%Y-%m-%d")
            approve_draft(date)
            
        elif command == "request-approval":
            if len(sys.argv) < 3:
                print("Error: request-approval command requires a date")
                sys.exit(1)
            date = sys.argv[2]
            datetime.strptime(date, "%Y-%m-%d")
            request_approval(date)
            
        elif command == "weekly-report":
            end_date = sys.argv[2] if len(sys.argv) > 2 else None
            if end_date:
                datetime.strptime(end_date, "%Y-%m-%d")
            weekly_report(end_date)
            
        else:
            print(f"Error: Unknown command '{command}'")
            print("Available commands: status, approve, request-approval, weekly-report")
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
