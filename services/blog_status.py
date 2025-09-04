"""
Blog status helper functions for M8 blog-centric refactor.
Provides utilities to check blog publication states and generate status reports.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BlogStatusChecker:
    """Helper class for checking blog publication status."""
    
    def __init__(self, blogs_dir: Optional[Path] = None):
        self.blogs_dir = blogs_dir or Path("blogs")
    
    def is_published(self, date: str) -> bool:
        """
        Check if a blog is published (FINAL digest exists).
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            True if FINAL digest exists, False otherwise
        """
        final_path = self.blogs_dir / date / f"FINAL-{date}_digest.json"
        return final_path.exists()
    
    def is_draft_only(self, date: str) -> bool:
        """
        Check if a blog is in draft state (PRE-CLEANED exists, no FINAL).
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            True if PRE-CLEANED exists but no FINAL, False otherwise
        """
        pre_cleaned_path = self.blogs_dir / date / f"PRE-CLEANED-{date}_digest.json"
        final_path = self.blogs_dir / date / f"FINAL-{date}_digest.json"
        
        return pre_cleaned_path.exists() and not final_path.exists()
    
    def is_missing(self, date: str) -> bool:
        """
        Check if no digest exists for a date.
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            True if no digest files exist, False otherwise
        """
        date_dir = self.blogs_dir / date
        if not date_dir.exists():
            return True
        
        # Check for any digest files
        digest_files = list(date_dir.glob("*_digest.json"))
        return len(digest_files) == 0
    
    def get_blog_status(self, date: str) -> str:
        """
        Get the current status of a blog for a given date.
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            Status string: 'published', 'draft', or 'missing'
        """
        if self.is_published(date):
            return 'published'
        elif self.is_draft_only(date):
            return 'draft'
        else:
            return 'missing'
    
    def get_draft_info(self, date: str) -> Optional[Dict]:
        """
        Get information about a draft blog.
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary with draft info or None if not a draft
        """
        if not self.is_draft_only(date):
            return None
        
        pre_cleaned_path = self.blogs_dir / date / f"PRE-CLEANED-{date}_digest.json"
        
        try:
            with open(pre_cleaned_path, 'r', encoding='utf-8') as f:
                digest = json.load(f)
            
            frontmatter = digest.get("frontmatter", {})
            story_packets = digest.get("story_packets", [])
            
            return {
                "date": date,
                "title": frontmatter.get("title", "Untitled"),
                "excerpt": frontmatter.get("lead", ""),
                "seo_description": frontmatter.get("description", ""),
                "story_count": len(story_packets),
                "created_at": pre_cleaned_path.stat().st_mtime
            }
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read draft info for {date}: {e}")
            return None
    
    def scan_date_range(self, start_date: str, end_date: str) -> Dict[str, List[str]]:
        """
        Scan a date range and categorize blogs by status.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary with 'published', 'draft', 'missing' lists of dates
        """
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        result = {
            "published": [],
            "draft": [],
            "missing": []
        }
        
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            status = self.get_blog_status(date_str)
            result[status].append(date_str)
            current += timedelta(days=1)
        
        return result
    
    def get_daily_rollup(self, target_date: str) -> Dict:
        """
        Generate daily rollup report for a specific date.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary with rollup information
        """
        status = self.get_blog_status(target_date)
        
        result = {
            "date": target_date,
            "status": status,
            "is_published": status == "published",
            "is_draft": status == "draft",
            "is_missing": status == "missing"
        }
        
        if status == "draft":
            draft_info = self.get_draft_info(target_date)
            if draft_info:
                result.update(draft_info)
        
        return result
    
    def get_weekly_backlog(self, end_date: str) -> Dict:
        """
        Generate weekly backlog report for the past 7 days.
        
        Args:
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary with backlog information
        """
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        start = end - timedelta(days=6)  # 7 days total
        
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        
        scan_result = self.scan_date_range(start_str, end_str)
        
        # Get detailed info for drafts
        draft_details = []
        for date in scan_result["draft"]:
            draft_info = self.get_draft_info(date)
            if draft_info:
                draft_details.append(draft_info)
        
        return {
            "period": f"{start_str} to {end_str}",
            "summary": {
                "published": len(scan_result["published"]),
                "draft": len(scan_result["draft"]),
                "missing": len(scan_result["missing"])
            },
            "published_dates": scan_result["published"],
            "draft_details": draft_details,
            "missing_dates": scan_result["missing"]
        }


def format_daily_rollup_message(rollup: Dict) -> str:
    """
    Format daily rollup information into a Discord message.
    
    Args:
        rollup: Daily rollup dictionary from get_daily_rollup()
        
    Returns:
        Formatted Discord message string
    """
    date = rollup["date"]
    status = rollup["status"]
    
    if status == "published":
        return f"✅ **Blog Published** — {date}\nAll good! Blog is live and published."
    
    elif status == "draft":
        title = rollup.get("title", "Untitled")
        story_count = rollup.get("story_count", 0)
        return (
            f"⚠️ **Draft Awaiting Approval** — {date}\n"
            f"**Title:** {title}\n"
            f"**Stories:** {story_count} story packets\n"
            f"Ready for review and approval."
        )
    
    else:  # missing
        return (
            f"🚫 **Missing Blog** — {date}\n"
            f"No blog activity detected. Consider recording some content!"
        )


def format_weekly_backlog_message(backlog: Dict) -> str:
    """
    Format weekly backlog information into a Discord message.
    
    Args:
        backlog: Weekly backlog dictionary from get_weekly_backlog()
        
    Returns:
        Formatted Discord message string
    """
    period = backlog["period"]
    summary = backlog["summary"]
    
    lines = [
        f"📊 **Weekly Blog Report** — {period}",
        "",
        f"✅ **Published:** {summary['published']} blogs",
        f"⚠️ **Drafts:** {summary['draft']} awaiting approval", 
        f"🚫 **Missing:** {summary['missing']} no activity",
        ""
    ]
    
    # Add draft details
    if backlog["draft_details"]:
        lines.append("**Drafts awaiting approval:**")
        for draft in backlog["draft_details"]:
            lines.append(f"• {draft['date']}: {draft['title']} ({draft['story_count']} stories)")
        lines.append("")
    
    # Add missing dates
    if backlog["missing_dates"]:
        lines.append("**Missing blogs:**")
        for date in backlog["missing_dates"]:
            lines.append(f"• {date}")
    
    return "\n".join(lines)


def format_draft_approval_message(draft_info: Dict) -> str:
    """
    Format draft information for approval workflow.
    
    Args:
        draft_info: Draft info dictionary from get_draft_info()
        
    Returns:
        Formatted Discord message for approval
    """
    date = draft_info["date"]
    title = draft_info["title"]
    excerpt = draft_info["excerpt"]
    seo_description = draft_info["seo_description"]
    story_count = draft_info["story_count"]
    
    lines = [
        f"📝 **Blog Draft Ready for Review** — {date}",
        "",
        f"**Title:** {title}",
        "",
        f"**Excerpt:** {excerpt}" if excerpt else "",
        "",
        f"**SEO Description:** {seo_description}" if seo_description else "",
        "",
        f"**Content:** {story_count} story packets included",
        "",
        "**Actions:**",
        "✅ Approve & Publish",
        "📝 Needs Edits"
    ]
    
    return "\n".join(line for line in lines if line.strip())


def format_missing_reminder_message(date: str) -> str:
    """
    Format missing blog reminder message.
    
    Args:
        date: Date in YYYY-MM-DD format
        
    Returns:
        Formatted Discord reminder message
    """
    return (
        f"⏰ **Missing Blog Reminder** — {date}\n"
        f"No blog activity detected for {date}. Want to jot a quick note?\n"
        f"→ `/record_blog {date}`"
    )