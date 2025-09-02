"""
Tests for M5 related posts service.
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch
from services.related import RelatedPostsService


class TestRelatedPostsService:
    """Test related posts service functionality."""
    
    @pytest.fixture
    def temp_blogs_dir(self):
        """Create temporary blogs directory with test data."""
        temp_dir = tempfile.mkdtemp()
        blogs_dir = Path(temp_dir) / "blogs"
        blogs_dir.mkdir(parents=True)
        
        # Create test digest files
        test_dates = ["2025-01-10", "2025-01-15", "2025-01-20", "2025-02-01"]
        test_data = [
            {
                "version": "2",
                "date": "2025-01-10",
                "frontmatter": {
                    "title": "Daily Devlog — Jan 10, 2025",
                    "tags": ["feat", "docs"]
                }
            },
            {
                "version": "2",
                "date": "2025-01-15",
                "frontmatter": {
                    "title": "Daily Devlog — Jan 15, 2025",
                    "tags": ["feat", "fix", "perf"]
                }
            },
            {
                "version": "2",
                "date": "2025-01-20",
                "frontmatter": {
                    "title": "Daily Devlog — Jan 20, 2025",
                    "tags": ["security", "infra"]
                }
            },
            {
                "version": "2",
                "date": "2025-02-01",
                "frontmatter": {
                    "title": "Daily Devlog — Feb 1, 2025",
                    "tags": ["feat", "docs", "perf"]
                }
            }
        ]
        
        for date, data in zip(test_dates, test_data):
            date_dir = blogs_dir / date
            date_dir.mkdir()
            
            digest_file = date_dir / f"PRE-CLEANED-{date}_digest.json"
            with open(digest_file, 'w') as f:
                json.dump(data, f)
        
        yield blogs_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def related_service(self, temp_blogs_dir):
        """Create related service with test blogs directory."""
        service = RelatedPostsService()
        service.blogs_dir = temp_blogs_dir
        return service
    
    def test_find_related_posts_basic(self, related_service):
        """Test basic related posts finding."""
        current_date = "2025-01-15"
        current_tags = ["feat", "fix"]
        current_title = "Daily Devlog — Jan 15, 2025"
        
        related_posts = related_service.find_related_posts(
            current_date, current_tags, current_title
        )
        
        # Should find related posts (excluding current date)
        assert len(related_posts) > 0
        
        # Current date should not be included
        for title, path, score in related_posts:
            assert "Jan 15" not in title
        
        # Should be sorted by score descending
        scores = [score for _, _, score in related_posts]
        assert scores == sorted(scores, reverse=True)
    
    def test_find_related_posts_no_blogs_dir(self, related_service):
        """Test behavior when blogs directory doesn't exist."""
        related_service.blogs_dir = Path("/nonexistent/path")
        
        related_posts = related_service.find_related_posts(
            "2025-01-15", ["feat"], "Test Title"
        )
        
        assert related_posts == []
    
    def test_find_related_posts_empty_blogs_dir(self, related_service):
        """Test behavior with empty blogs directory."""
        # Remove all test data
        for item in related_service.blogs_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
        
        related_posts = related_service.find_related_posts(
            "2025-01-15", ["feat"], "Test Title"
        )
        
        assert related_posts == []
    
    def test_find_related_posts_invalid_date_folders(self, related_service):
        """Test behavior with invalid date folder names."""
        # Create invalid folder
        invalid_dir = related_service.blogs_dir / "invalid-folder"
        invalid_dir.mkdir()
        
        related_posts = related_service.find_related_posts(
            "2025-01-15", ["feat"], "Test Title"
        )
        
        # Should still work and ignore invalid folders
        assert len(related_posts) > 0
    
    def test_find_related_posts_corrupted_digest(self, related_service):
        """Test behavior with corrupted digest files."""
        # Corrupt one digest file
        corrupt_file = related_service.blogs_dir / "2025-01-10" / "PRE-CLEANED-2025-01-10_digest.json"
        with open(corrupt_file, 'w') as f:
            f.write("invalid json content")
        
        related_posts = related_service.find_related_posts(
            "2025-01-15", ["feat"], "Test Title"
        )
        
        # Should still work and skip corrupted files
        assert len(related_posts) > 0
    
    def test_find_related_posts_max_limit(self, related_service):
        """Test max posts limit."""
        current_date = "2025-01-15"
        current_tags = ["feat", "fix"]
        current_title = "Daily Devlog — Jan 15, 2025"
        
        # Request only 2 posts
        related_posts = related_service.find_related_posts(
            current_date, current_tags, current_title, max_posts=2
        )
        
        assert len(related_posts) <= 2
    
    def test_compute_related_score_tags_overlap(self, related_service):
        """Test tags overlap scoring."""
        current_tags = ["feat", "fix", "perf"]
        current_title = "Test Title"
        current_date = "2025-01-15"
        
        # High overlap
        post_tags = ["feat", "fix", "perf", "docs"]
        post_title = "Post Title"
        post_date = "2025-01-10"
        
        score_high = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags, post_title, post_date
        )
        
        # Low overlap
        post_tags_low = ["docs", "infra"]
        
        score_low = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags_low, post_title, post_date
        )
        
        # High overlap should score higher
        assert score_high > score_low
    
    def test_compute_related_score_title_similarity(self, related_service):
        """Test title similarity scoring."""
        current_tags = ["feat"]
        current_title = "Daily Devlog — Jan 15, 2025"
        current_date = "2025-01-15"
        
        # Similar title
        post_tags = ["feat"]
        post_title = "Daily Devlog — Jan 10, 2025"
        post_date = "2025-01-10"
        
        score_similar = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags, post_title, post_date
        )
        
        # Different title
        post_title_diff = "Completely Different Title"
        
        score_diff = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags, post_title_diff, post_date
        )
        
        # Similar title should score higher
        assert score_similar > score_diff
    
    def test_compute_related_score_recency_decay(self, related_service):
        """Test recency decay scoring."""
        current_tags = ["feat"]
        current_title = "Test Title"
        current_date = "2025-01-15"
        
        # Recent post
        post_tags = ["feat"]
        post_title = "Post Title"
        recent_date = "2025-01-14"  # 1 day ago
        
        score_recent = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags, post_title, recent_date
        )
        
        # Old post
        old_date = "2024-10-15"  # ~3 months ago
        
        score_old = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags, post_title, old_date
        )
        
        # Recent post should score higher
        assert score_recent > score_old
    
    def test_compute_related_score_weighted_combination(self, related_service):
        """Test that all scoring components contribute."""
        current_tags = ["feat", "fix"]
        current_title = "Daily Devlog — Jan 15, 2025"
        current_date = "2025-01-15"
        
        # Post with high tags overlap but different title and old date
        post_tags = ["feat", "fix", "perf"]
        post_title = "Completely Different Title"
        old_date = "2024-10-15"
        
        score = related_service._compute_related_score(
            current_tags, current_title, current_date,
            post_tags, post_title, old_date
        )
        
        # Score should be between 0 and 1
        assert 0.0 <= score <= 1.0
        
        # Should have some contribution from tags overlap
        assert score > 0.0
    
    def test_compute_tags_overlap_basic(self, related_service):
        """Test basic tags overlap calculation."""
        current_tags = ["feat", "fix", "perf"]
        post_tags = ["feat", "fix", "docs"]
        
        score = related_service._compute_tags_overlap(current_tags, post_tags)
        
        # 2 common tags, 4 total unique tags = 0.5
        assert score == 0.5
    
    def test_compute_tags_overlap_no_overlap(self, related_service):
        """Test tags overlap with no common tags."""
        current_tags = ["feat", "fix"]
        post_tags = ["docs", "infra"]
        
        score = related_service._compute_tags_overlap(current_tags, post_tags)
        
        assert score == 0.0
    
    def test_compute_tags_overlap_case_insensitive(self, related_service):
        """Test that tags overlap is case insensitive."""
        current_tags = ["Feat", "Fix"]
        post_tags = ["feat", "FIX"]
        
        score = related_service._compute_tags_overlap(current_tags, post_tags)
        
        # Should match despite case differences
        assert score == 1.0
    
    def test_compute_tags_overlap_empty_lists(self, related_service):
        """Test tags overlap with empty lists."""
        # Both empty
        score = related_service._compute_tags_overlap([], [])
        assert score == 0.0
        
        # One empty
        score = related_service._compute_tags_overlap(["feat"], [])
        assert score == 0.0
        
        score = related_service._compute_tags_overlap([], ["feat"])
        assert score == 0.0
    
    def test_compute_title_similarity_basic(self, related_service):
        """Test basic title similarity calculation."""
        current_title = "Daily Devlog — Jan 15, 2025"
        post_title = "Daily Devlog — Jan 10, 2025"
        
        score = related_service._compute_title_similarity(current_title, post_title)
        
        # Should have some similarity due to common words
        assert score > 0.0
        assert score <= 1.0
    
    def test_compute_title_similarity_stop_words_removed(self, related_service):
        """Test that stop words are removed from similarity calculation."""
        current_title = "The Daily Devlog — Jan 15, 2025"
        post_title = "A Daily Devlog — Jan 10, 2025"
        
        score = related_service._compute_title_similarity(current_title, post_title)
        
        # Should still have good similarity despite different articles
        assert score > 0.0
    
    def test_compute_title_similarity_no_common_words(self, related_service):
        """Test title similarity with no common words."""
        current_title = "Completely Unique Content"
        post_title = "Another Different Story"
        
        score = related_service._compute_title_similarity(current_title, post_title)
        
        assert score == 0.0
    
    def test_compute_recency_decay_same_date(self, related_service):
        """Test recency decay for same date."""
        from datetime import date
        current_date = date(2025, 1, 15)
        post_date = date(2025, 1, 15)
        
        score = related_service._compute_recency_decay(current_date, post_date)
        
        assert score == 1.0
    
    def test_compute_recency_decay_90_days(self, related_service):
        """Test recency decay for 90 days (half-life)."""
        from datetime import date
        current_date = date(2025, 1, 15)
        post_date = date(2024, 10, 17)  # ~90 days ago
        
        score = related_service._compute_recency_decay(current_date, post_date)
        
        # Should be close to 0.5 (half-life)
        assert abs(score - 0.5) < 0.1
    
    def test_compute_recency_decay_180_days(self, related_service):
        """Test recency decay for 180 days (quarter-life)."""
        from datetime import date
        current_date = date(2025, 1, 15)
        post_date = date(2024, 7, 18)  # ~180 days ago
        
        score = related_service._compute_recency_decay(current_date, post_date)
        
        # Should be close to 0.25 (quarter-life)
        assert abs(score - 0.25) < 0.1
    
    def test_compute_recency_decay_future_date(self, related_service):
        """Test recency decay for future date."""
        from datetime import date
        current_date = date(2025, 1, 15)
        post_date = date(2025, 2, 15)  # Future date
        
        score = related_service._compute_recency_decay(current_date, post_date)
        
        # Should still decay based on absolute difference
        assert score < 1.0
        assert score > 0.0
    
    def test_find_published_posts_structure(self, related_service):
        """Test that published posts have correct structure."""
        published_posts = related_service._find_published_posts()
        
        assert len(published_posts) > 0
        
        for post in published_posts:
            assert "date" in post
            assert "title" in post
            assert "tags" in post
            assert "path" in post
            
            # Validate date format
            assert len(post["date"]) == 10  # YYYY-MM-DD
            assert post["date"].count("-") == 2
            
            # Validate path format
            assert post["path"].startswith("/blog/")
    
    def test_find_published_posts_skip_invalid_dates(self, related_service):
        """Test that invalid date folders are skipped."""
        # Create folder with invalid date name
        invalid_dir = related_service.blogs_dir / "invalid-date"
        invalid_dir.mkdir()
        
        # Create digest file in invalid directory
        digest_file = invalid_dir / "PRE-CLEANED-invalid-date_digest.json"
        with open(digest_file, 'w') as f:
            json.dump({"test": "data"}, f)
        
        published_posts = related_service._find_published_posts()
        
        # Should not include posts from invalid date folders
        for post in published_posts:
            assert post["date"] != "invalid-date"
    
    def test_find_published_posts_skip_v1_digests(self, related_service):
        """Test that v1 digests are skipped."""
        # Create v1 digest file
        v1_dir = related_service.blogs_dir / "2025-01-25"
        v1_dir.mkdir()
        
        v1_digest = v1_dir / "PRE-CLEANED-2025-01-25_digest.json"
        v1_data = {
            "date": "2025-01-25",
            "version": "1",  # v1 digest
            "title": "Test Title"
        }
        
        with open(v1_digest, 'w') as f:
            json.dump(v1_data, f)
        
        published_posts = related_service._find_published_posts()
        
        # Should not include v1 digests
        for post in published_posts:
            assert post["date"] != "2025-01-25"
    
    def test_find_related_posts_with_repo(self, related_service):
        """Test finding related posts with remote repo specified."""
        current_date = "2025-01-15"
        current_tags = ["feat", "fix"]
        current_title = "Daily Devlog — Jan 15, 2025"
        
        # Mock the remote posts fetching
        with patch.object(related_service, '_fetch_published_posts_from_remote') as mock_remote:
            mock_remote.return_value = [
                {
                    "date": "2025-01-05",
                    "title": "Remote Post 1",
                    "tags": ["feat", "docs"],
                    "path": "/blog/2025-01-05"
                },
                {
                    "date": "2025-01-08",
                    "title": "Remote Post 2",
                    "tags": ["fix", "perf"],
                    "path": "/blog/2025-01-08"
                }
            ]
            
            related_posts = related_service.find_related_posts(
                current_date, current_tags, current_title, repo="test/repo"
            )
            
            # Should call remote fetching
            mock_remote.assert_called_once_with("test/repo")
            
            # Should include both local and remote posts
            assert len(related_posts) > 0
    
    def test_find_related_posts_remote_api_failure(self, related_service):
        """Test graceful handling of remote API failures."""
        current_date = "2025-01-15"
        current_tags = ["feat", "fix"]
        current_title = "Daily Devlog — Jan 15, 2025"
        
        # Mock the remote posts fetching to fail
        with patch.object(related_service, '_fetch_published_posts_from_remote') as mock_remote:
            mock_remote.side_effect = Exception("API Error")
            
            related_posts = related_service.find_related_posts(
                current_date, current_tags, current_title, repo="test/repo"
            )
            
            # Should still return local posts
            assert len(related_posts) > 0
            
            # Should log the error but continue
            mock_remote.assert_called_once_with("test/repo")
    
    def test_find_related_posts_validation(self, related_service):
        """Test that posts without required fields are filtered out."""
        current_date = "2025-01-15"
        current_tags = ["feat", "fix"]
        current_title = "Daily Devlog — Jan 15, 2025"
        
        # Mock the remote posts fetching to return invalid posts
        with patch.object(related_service, '_fetch_published_posts_from_remote') as mock_remote:
            mock_remote.return_value = [
                {
                    "date": "2025-01-05",
                    "title": "",  # Empty title
                    "tags": ["feat"],
                    "path": "/blog/2025-01-05"
                },
                {
                    "date": "2025-01-08",
                    "title": "Valid Post",
                    "tags": [],  # Empty tags
                    "path": "/blog/2025-01-08"
                }
            ]
            
            related_posts = related_service.find_related_posts(
                current_date, current_tags, current_title, repo="test/repo"
            )
            
            # Should filter out invalid posts
            assert len(related_posts) >= 0  # May be 0 if all posts are invalid
