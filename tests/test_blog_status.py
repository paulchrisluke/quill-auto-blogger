"""
Tests for blog status functionality (M8).
"""

import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from services.blog_status import BlogStatusChecker, format_daily_rollup_message, format_weekly_backlog_message


class TestBlogStatusChecker(unittest.TestCase):
    """Test BlogStatusChecker functionality."""
    
    def setUp(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.blogs_dir = Path(self.temp_dir) / "blogs"
        self.blogs_dir.mkdir(parents=True, exist_ok=True)
        self.checker = BlogStatusChecker(self.blogs_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_is_missing(self):
        """Test is_missing function."""
        # Test with non-existent date
        self.assertTrue(self.checker.is_missing("2025-01-01"))
        
        # Test with existing directory but no digest files
        date_dir = self.blogs_dir / "2025-01-01"
        date_dir.mkdir()
        self.assertTrue(self.checker.is_missing("2025-01-01"))
    
    def test_is_draft_only(self):
        """Test is_draft_only function."""
        date = "2025-01-01"
        date_dir = self.blogs_dir / date
        date_dir.mkdir()
        
        # Test with no files
        self.assertFalse(self.checker.is_draft_only(date))
        
        # Test with PRE-CLEANED only
        pre_cleaned_path = date_dir / f"PRE-CLEANED-{date}_digest.json"
        with open(pre_cleaned_path, 'w') as f:
            json.dump({"version": "2", "date": date, "frontmatter": {"title": "Test"}}, f)
        
        self.assertTrue(self.checker.is_draft_only(date))
        
        # Test with both PRE-CLEANED and FINAL
        final_path = date_dir / f"FINAL-{date}_digest.json"
        with open(final_path, 'w') as f:
            json.dump({"version": "2", "date": date, "frontmatter": {"title": "Test"}}, f)
        
        self.assertFalse(self.checker.is_draft_only(date))
    
    def test_is_published(self):
        """Test is_published function."""
        date = "2025-01-01"
        date_dir = self.blogs_dir / date
        date_dir.mkdir()
        
        # Test with no files
        self.assertFalse(self.checker.is_published(date))
        
        # Test with PRE-CLEANED only
        pre_cleaned_path = date_dir / f"PRE-CLEANED-{date}_digest.json"
        with open(pre_cleaned_path, 'w') as f:
            json.dump({"version": "2", "date": date, "frontmatter": {"title": "Test"}}, f)
        
        self.assertFalse(self.checker.is_published(date))
        
        # Test with FINAL
        final_path = date_dir / f"FINAL-{date}_digest.json"
        with open(final_path, 'w') as f:
            json.dump({"version": "2", "date": date, "frontmatter": {"title": "Test"}}, f)
        
        self.assertTrue(self.checker.is_published(date))
    
    def test_get_blog_status(self):
        """Test get_blog_status function."""
        date = "2025-01-01"
        
        # Test missing
        self.assertEqual(self.checker.get_blog_status(date), "missing")
        
        # Test draft
        date_dir = self.blogs_dir / date
        date_dir.mkdir()
        pre_cleaned_path = date_dir / f"PRE-CLEANED-{date}_digest.json"
        with open(pre_cleaned_path, 'w') as f:
            json.dump({"version": "2", "date": date, "frontmatter": {"title": "Test"}}, f)
        
        self.assertEqual(self.checker.get_blog_status(date), "draft")
        
        # Test published
        final_path = date_dir / f"FINAL-{date}_digest.json"
        with open(final_path, 'w') as f:
            json.dump({"version": "2", "date": date, "frontmatter": {"title": "Test"}}, f)
        
        self.assertEqual(self.checker.get_blog_status(date), "published")
    
    def test_get_draft_info(self):
        """Test get_draft_info function."""
        date = "2025-01-01"
        
        # Test with no draft
        self.assertIsNone(self.checker.get_draft_info(date))
        
        # Test with draft
        date_dir = self.blogs_dir / date
        date_dir.mkdir()
        pre_cleaned_path = date_dir / f"PRE-CLEANED-{date}_digest.json"
        
        draft_data = {
            "version": "2",
            "date": date,
            "frontmatter": {
                "title": "Test Blog Post",
                "lead": "This is a test excerpt",
                "description": "SEO description for the blog"
            },
            "story_packets": [
                {"id": "story1", "title_human": "Story 1"},
                {"id": "story2", "title_human": "Story 2"}
            ]
        }
        
        with open(pre_cleaned_path, 'w') as f:
            json.dump(draft_data, f)
        
        draft_info = self.checker.get_draft_info(date)
        self.assertIsNotNone(draft_info)
        self.assertEqual(draft_info["date"], date)
        self.assertEqual(draft_info["title"], "Test Blog Post")
        self.assertEqual(draft_info["excerpt"], "This is a test excerpt")
        self.assertEqual(draft_info["seo_description"], "SEO description for the blog")
        self.assertEqual(draft_info["story_count"], 2)
    
    def test_scan_date_range(self):
        """Test scan_date_range function."""
        # Create test data for multiple dates
        dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
        
        for i, date in enumerate(dates):
            date_dir = self.blogs_dir / date
            date_dir.mkdir()
            
            if i == 0:  # Missing
                pass
            elif i == 1:  # Draft
                pre_cleaned_path = date_dir / f"PRE-CLEANED-{date}_digest.json"
                with open(pre_cleaned_path, 'w') as f:
                    json.dump({"version": "2", "date": date}, f)
            else:  # Published
                pre_cleaned_path = date_dir / f"PRE-CLEANED-{date}_digest.json"
                final_path = date_dir / f"FINAL-{date}_digest.json"
                with open(pre_cleaned_path, 'w') as f:
                    json.dump({"version": "2", "date": date}, f)
                with open(final_path, 'w') as f:
                    json.dump({"version": "2", "date": date}, f)
        
        result = self.checker.scan_date_range("2025-01-01", "2025-01-03")
        
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(len(result["draft"]), 1)
        self.assertEqual(len(result["published"]), 1)
        self.assertIn("2025-01-01", result["missing"])
        self.assertIn("2025-01-02", result["draft"])
        self.assertIn("2025-01-03", result["published"])


class TestMessageFormatting(unittest.TestCase):
    """Test message formatting functions."""
    
    def test_format_daily_rollup_message_published(self):
        """Test daily rollup message for published blog."""
        rollup = {
            "date": "2025-01-01",
            "status": "published",
            "is_published": True,
            "is_draft": False,
            "is_missing": False
        }
        
        message = format_daily_rollup_message(rollup)
        self.assertIn("✅ **Blog Published**", message)
        self.assertIn("2025-01-01", message)
        self.assertIn("All good!", message)
    
    def test_format_daily_rollup_message_draft(self):
        """Test daily rollup message for draft blog."""
        rollup = {
            "date": "2025-01-01",
            "status": "draft",
            "is_published": False,
            "is_draft": True,
            "is_missing": False,
            "title": "Test Blog",
            "story_count": 3
        }
        
        message = format_daily_rollup_message(rollup)
        self.assertIn("⚠️ **Draft Awaiting Approval**", message)
        self.assertIn("2025-01-01", message)
        self.assertIn("Test Blog", message)
        self.assertIn("3 story packets", message)
    
    def test_format_daily_rollup_message_missing(self):
        """Test daily rollup message for missing blog."""
        rollup = {
            "date": "2025-01-01",
            "status": "missing",
            "is_published": False,
            "is_draft": False,
            "is_missing": True
        }
        
        message = format_daily_rollup_message(rollup)
        self.assertIn("🚫 **Missing Blog**", message)
        self.assertIn("2025-01-01", message)
        self.assertIn("No blog activity detected", message)
    
    def test_format_weekly_backlog_message(self):
        """Test weekly backlog message formatting."""
        backlog = {
            "period": "2025-01-01 to 2025-01-07",
            "summary": {
                "published": 3,
                "draft": 2,
                "missing": 2
            },
            "published_dates": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "draft_details": [
                {
                    "date": "2025-01-04",
                    "title": "Draft Blog 1",
                    "story_count": 2
                },
                {
                    "date": "2025-01-05",
                    "title": "Draft Blog 2",
                    "story_count": 1
                }
            ],
            "missing_dates": ["2025-01-06", "2025-01-07"]
        }
        
        message = format_weekly_backlog_message(backlog)
        self.assertIn("📊 **Weekly Blog Report**", message)
        self.assertIn("2025-01-01 to 2025-01-07", message)
        self.assertIn("✅ **Published:** 3 blogs", message)
        self.assertIn("⚠️ **Drafts:** 2 awaiting approval", message)
        self.assertIn("🚫 **Missing:** 2 no activity", message)
        self.assertIn("Draft Blog 1", message)
        self.assertIn("Draft Blog 2", message)
        self.assertIn("2025-01-06", message)
        self.assertIn("2025-01-07", message)


if __name__ == "__main__":
    unittest.main()
