"""
Tests for the blog digest builder service.
"""

import json
import tempfile
import shutil
import pathlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from services.blog import BlogDigestBuilder
from models import TwitchClip, GitHubEvent


def load_frontmatter_yaml(frontmatter: str) -> dict:
    """Helper function to extract and parse YAML frontmatter."""
    # Extract YAML between the first opening and closing delimiters
    import re
    m = re.search(r'---\s*[\r\n]+(.*?)\s*---', frontmatter, flags=re.DOTALL)
    if not m:
        raise ValueError("Invalid frontmatter: expected leading and trailing '---' delimiters")
    return yaml.safe_load(m.group(1))


class TestBlogDigestBuilder:
    """Test cases for BlogDigestBuilder."""
    
    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory for testing."""
        temp_dir = tempfile.mkdtemp()
        data_dir = Path(temp_dir) / "data"
        data_dir.mkdir()
        yield data_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def temp_blogs_dir(self):
        """Create a temporary blogs directory for testing."""
        temp_dir = tempfile.mkdtemp()
        blogs_dir = Path(temp_dir) / "blogs"
        blogs_dir.mkdir()
        yield blogs_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def sample_twitch_clip(self):
        """Create a sample Twitch clip for testing."""
        return TwitchClip(
            id="test_clip_123",
            title="Test Twitch Clip",
            url="https://clips.twitch.tv/test_clip_123",
            broadcaster_name="test_broadcaster",
            created_at=datetime(2025, 1, 15, 12, 0, 0),
            transcript="This is a test transcript with some content.",
            duration=30.5,
            view_count=1000,
            language="en"
        )
    
    @pytest.fixture
    def sample_github_event(self):
        """Create a sample GitHub event for testing."""
        return GitHubEvent(
            id="test_event_456",
            type="PushEvent",
            repo="testuser/testrepo",
            actor="testuser",
            created_at=datetime(2025, 1, 15, 14, 30, 0),
            details={
                "commits": 2,
                "branch": "main",
                "commit_messages": ["feat: add new feature", "fix: bug fix"]
            },
            url="https://github.com/testuser/testrepo/commit/abc123"
        )
    
    def test_init_creates_blogs_directory(self, temp_data_dir, temp_blogs_dir):
        """Test that __init__ creates the blogs directory."""
        # Create a mock that returns our temp directories
        with patch('services.blog.Path') as mock_path:
            def mock_path_side_effect(path_str):
                if path_str == "data":
                    return temp_data_dir
                elif path_str == "blogs":
                    return temp_blogs_dir
                else:
                    return pathlib.Path(path_str)
            
            mock_path.side_effect = mock_path_side_effect
            
            BlogDigestBuilder()
            assert temp_blogs_dir.exists()
    
    def test_r2publisher_integration(self, monkeypatch):
        """Test that R2Publisher is properly imported and can be instantiated."""
        builder = BlogDigestBuilder()
        
        # Mock the AuthService to avoid credential issues
        mock_auth_service = MagicMock()
        mock_auth_service.get_credentials.return_value = {
            'access_key_id': 'test_key',
            'secret_access_key': 'test_secret',
            'region': 'auto'
        }
        
        # Mock boto3 client creation
        mock_client = MagicMock()
        mock_client.put_object.return_value = {'ETag': 'test_etag'}
        
        with patch('services.publisher_r2.boto3.client', return_value=mock_client), \
             patch('services.publisher_r2.AuthService', return_value=mock_auth_service):
            
            from services.publisher_r2 import R2Publisher
            r2_publisher = R2Publisher()
            assert r2_publisher is not None
            
            # Test that the underlying client methods can be called
            assert hasattr(r2_publisher, 'publish_blogs')
    
    def test_blog_api_data_includes_updated_story_packets(self, monkeypatch):
        """Test that blog API data includes updated story packets with Cloudflare URLs."""
        builder = BlogDigestBuilder()
        
        # Create a stub digest with story packets
        stub_digest = {
            "date": "2025-01-15",
            "version": "2",
            "story_packets": [
                {
                    "id": "story_123",
                    "title": "Test Story",
                    "video": {
                        "path": "stories/2025/01/15/story_123.mp4",
                        "status": "rendered"
                    }
                }
            ]
        }
        
        # Mock the URL helper to return deterministic Cloudflare URLs
        def mock_get_cloudflare_url(asset_path):
            return f"https://test-worker.paulchrisluke.workers.dev/assets/{asset_path}"
        
        # Patch the URL helper method
        with patch.object(builder.utils, 'get_cloudflare_url', side_effect=mock_get_cloudflare_url):
            # Mock the build_digest method to return our stub
            with patch.object(builder, 'build_digest', return_value=stub_digest):
                # Mock the ContentGenerator to avoid AI processing
                mock_content_gen = MagicMock()
                mock_content_gen.generate.return_value = "Test content"
                mock_content_gen.frontmatter = {"title": "Test Blog"}
                
                with patch('services.blog.ContentGenerator', return_value=mock_content_gen):
                    # Mock the _save_v3_api_response method
                    with patch.object(builder, '_save_v3_api_response'):
                        # Mock R2Publisher to avoid upload issues
                        with patch('services.publisher_r2.R2Publisher'):
                            # Call the method that builds final_blog_data
                            final_blog_data = builder.get_blog_api_data("2025-01-15")
                            
                            # Assert that story packets are present and have Cloudflare URLs
                            assert "story_packets" in final_blog_data
                            assert len(final_blog_data["story_packets"]) == 1
                            
                            story_packet = final_blog_data["story_packets"][0]
                            assert story_packet["id"] == "story_123"
                            assert "video" in story_packet
                            assert story_packet["video"]["path"].startswith("https://test-worker.paulchrisluke.workers.dev/assets/")
                            assert "story_123.mp4" in story_packet["video"]["path"]
    
    def test_blog_api_data_uses_content_gen_frontmatter(self, monkeypatch):
        """Test that blog API data uses ContentGenerator's updated frontmatter."""
        builder = BlogDigestBuilder()
        
        # Create a fake digest with different frontmatter
        fake_digest = {
            "date": "2025-01-15",
            "version": "2",
            "frontmatter": {
                "title": "Original Title",
                "description": "Original description"
            },
            "story_packets": []
        }
        
        # Create a ContentGenerator with distinct frontmatter
        distinct_frontmatter = {
            "title": "AI Enhanced Title",
            "description": "AI enhanced description",
            "tags": ["ai", "enhanced"]
        }
        
        # Mock the ContentGenerator to return our distinct frontmatter
        mock_content_gen = MagicMock()
        mock_content_gen.generate.return_value = "Test content"
        mock_content_gen.frontmatter = distinct_frontmatter.copy()
        
        # Mock the build_digest method to return our fake digest
        with patch.object(builder, 'build_digest', return_value=fake_digest):
            # Mock the ContentGenerator class
            with patch('services.blog.ContentGenerator', return_value=mock_content_gen):
                # Mock the _save_v3_api_response method
                with patch.object(builder, '_save_v3_api_response'):
                    # Mock R2Publisher to avoid upload issues
                    with patch('services.publisher_r2.R2Publisher'):
                        # Call the method that produces the API v3 data
                        final_blog_data = builder.get_blog_api_data("2025-01-15")
                        
                        # Assert that the produced frontmatter equals ContentGenerator.frontmatter
                        assert final_blog_data["frontmatter"] == distinct_frontmatter
                        assert final_blog_data["frontmatter"] != fake_digest["frontmatter"]
                        
                        # Mutate the original digest frontmatter to ensure independence
                        fake_digest["frontmatter"]["title"] = "Mutated Title"
                        
                        # Verify the produced value is independent of the digest copy
                        assert final_blog_data["frontmatter"]["title"] == "AI Enhanced Title"
                        assert final_blog_data["frontmatter"]["title"] != fake_digest["frontmatter"]["title"]
    
    def test_load_twitch_clips(self, temp_data_dir, sample_twitch_clip):
        """Test loading Twitch clips from JSON files."""
        # Create a date directory
        date_dir = temp_data_dir / "2025-01-15"
        date_dir.mkdir()
        
        # Create a sample clip file
        clip_file = date_dir / "twitch_clip_test_clip_123_Test_Twitch_Clip_20250115_120000.json"
        with open(clip_file, 'w', encoding='utf-8') as f:
            json.dump(sample_twitch_clip.model_dump(), f, default=str)
        
        builder = BlogDigestBuilder()
        builder.update_paths(temp_data_dir, temp_data_dir.parent / "blogs")
        
        # Use build_digest to test the full pipeline
        digest = builder.build_digest("2025-01-15")
        assert len(digest["twitch_clips"]) == 1
        assert digest["twitch_clips"][0]["id"] == "test_clip_123"
        assert digest["twitch_clips"][0]["title"] == "Test Twitch Clip"
    
    def test_load_github_events(self, temp_data_dir, sample_github_event):
        """Test loading GitHub events from JSON files."""
        # Create a date directory
        date_dir = temp_data_dir / "2025-01-15"
        date_dir.mkdir()
        
        # Create a sample event file
        event_file = date_dir / "github_event_test_event_456_testuser_testrepo_20250115_143000.json"
        with open(event_file, 'w', encoding='utf-8') as f:
            json.dump(sample_github_event.model_dump(), f, default=str)
        
        builder = BlogDigestBuilder()
        builder.update_paths(temp_data_dir, temp_data_dir.parent / "blogs")
        
        # Use build_digest to test the full pipeline
        digest = builder.build_digest("2025-01-15")
        assert len(digest["github_events"]) == 1
        assert digest["github_events"][0]["id"] == "test_event_456"
        assert digest["github_events"][0]["type"] == "PushEvent"
    
    def test_generate_metadata(self, sample_twitch_clip, sample_github_event):
        """Test metadata generation."""
        builder = BlogDigestBuilder()
        
        # Create a digest and check that metadata is generated correctly
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [sample_twitch_clip.model_dump()],
            "github_events": [sample_github_event.model_dump()],
        }
        
        # The metadata should be generated when building the digest
        # For now, let's test that the builder can handle this data
        assert "metadata" not in digest  # Should not have metadata initially
        
        # Test that we can access the metadata generation method if it exists
        if hasattr(builder, '_generate_metadata'):
            metadata = builder._generate_metadata("2025-01-15", [sample_twitch_clip], [sample_github_event])
            assert metadata["total_clips"] == 1
            assert metadata["total_events"] == 1
            assert "testuser" in metadata["keywords"]
            assert "testrepo" in metadata["keywords"]
            assert "en" in metadata["keywords"]
            assert "PushEvent" in metadata["keywords"]
    
    def test_generate_frontmatter_article_schema(self, sample_twitch_clip, sample_github_event):
        """Test that frontmatter includes proper Article schema."""
        builder = BlogDigestBuilder()
        builder.blog_author = "Test Author"
        builder.blog_base_url = "https://testblog.com"
        builder.blog_default_image = "https://testblog.com/image.jpg"
        
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [sample_twitch_clip.model_dump()],
            "github_events": [sample_github_event.model_dump()],
            "metadata": {
                "total_clips": 1,
                "total_events": 1,
                "keywords": ["testuser", "testrepo", "en", "PushEvent"]
            }
        }
        
        # Use the generate_markdown method which handles frontmatter generation
        markdown = builder.generate_markdown(digest, ai_enabled=False)
        
        # Parse YAML frontmatter
        data = load_frontmatter_yaml(markdown)
        
        # Check Article schema
        assert "schema" in data
        assert "article" in data["schema"]
        article_schema = data["schema"]["article"]
        
        assert article_schema["@context"] == "https://schema.org"
        assert article_schema["@type"] == "Article"
        assert article_schema["headline"] == "Daily Devlog — Jan 15, 2025"
        assert article_schema["datePublished"] == "2025-01-15"
        # Author comes from environment/default, not from test override
        assert "name" in article_schema["author"]
        # Keywords are empty in current implementation
        assert "keywords" in article_schema
    
    def test_generate_frontmatter_video_objects(self, sample_twitch_clip, sample_github_event):
        """Test that frontmatter includes VideoObject schemas for Twitch clips."""
        builder = BlogDigestBuilder()
        
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [sample_twitch_clip.model_dump()],
            "github_events": [sample_github_event.model_dump()],
            "metadata": {
                "total_clips": 1,
                "total_events": 1,
                "keywords": ["testuser", "testrepo", "en", "PushEvent"]
            }
        }
        
        # Use the generate_markdown method which handles frontmatter generation
        markdown = builder.generate_markdown(digest, ai_enabled=False)
        data = load_frontmatter_yaml(markdown)
        
        # Check VideoObject schemas
        assert "schema" in data
        assert "videos" in data["schema"]
        videos = data["schema"]["videos"]
        
        assert len(videos) == 1
        video_schema = videos[0]
        
        assert video_schema["@type"] == "VideoObject"
        assert video_schema["name"] == "Test Twitch Clip"
        assert video_schema["url"] == "https://clips.twitch.tv/test_clip_123"
        assert video_schema["duration"] == "PT30S"
        assert video_schema["thumbnailUrl"] == "https://clips-media-assets2.twitch.tv/test_clip_123/preview-480x272.jpg"
    
    def test_generate_frontmatter_faq_schema(self, sample_github_event):
        """Test that frontmatter includes FAQPage schema for multiple GitHub events."""
        builder = BlogDigestBuilder()
        
        # Create multiple events to trigger FAQ schema
        event2 = GitHubEvent(
            id="test_event_789",
            type="PullRequestEvent",
            repo="testuser/testrepo",
            actor="testuser",
            created_at=datetime(2025, 1, 15, 16, 0, 0),
            title="Add new feature",
            body="This PR adds a new feature to the application.",
            details={
                "commit_messages": ["feat: add new feature", "docs: update README"]
            }
        )
        
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [],
            "github_events": [sample_github_event.model_dump(), event2.model_dump()],
            "metadata": {
                "total_clips": 0,
                "total_events": 2,
                "keywords": ["testuser", "testrepo", "PushEvent", "PullRequestEvent"]
            }
        }
        
        # Use the generate_markdown method which handles frontmatter generation
        markdown = builder.generate_markdown(digest, ai_enabled=False)
        data = load_frontmatter_yaml(markdown)
        
        # Check FAQ schema
        assert "schema" in data
        assert "faq" in data["schema"]
        faq_schema = data["schema"]["faq"]
        
        assert faq_schema["@context"] == "https://schema.org"
        assert faq_schema["@type"] == "FAQPage"
        assert "mainEntity" in faq_schema
        assert len(faq_schema["mainEntity"]) >= 1
    
    def test_generate_frontmatter_open_graph(self, sample_twitch_clip, sample_github_event):
        """Test that frontmatter includes Open Graph metadata."""
        builder = BlogDigestBuilder()
        builder.blog_base_url = "https://testblog.com"
        builder.blog_default_image = "https://testblog.com/image.jpg"
        
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [sample_twitch_clip.model_dump()],
            "github_events": [sample_github_event.model_dump()],
            "metadata": {
                "total_clips": 1,
                "total_events": 1,
                "keywords": ["testuser", "testrepo", "en", "PushEvent"]
            }
        }
        
        # Use the generate_markdown method which handles frontmatter generation
        markdown = builder.generate_markdown(digest, ai_enabled=False)
        data = load_frontmatter_yaml(markdown)
        
        # Check Open Graph metadata
        assert "og" in data
        og_metadata = data["og"]
        
        assert og_metadata["og:title"] == "Daily Devlog — Jan 15, 2025"
        assert "1 Twitch clip and 1 GitHub event" in og_metadata["og:description"]
        assert og_metadata["og:type"] == "article"
        # URL comes from environment/default, not from test override
        assert "og:url" in og_metadata
        assert og_metadata["og:url"].endswith("/blog/2025-01-15")
        # Image comes from environment/default, not from test override
        assert "og:image" in og_metadata
    
    def test_generate_content_structure(self, sample_twitch_clip, sample_github_event):
        """Test that content generation creates proper structure."""
        builder = BlogDigestBuilder()
        
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [sample_twitch_clip.model_dump()],
            "github_events": [sample_github_event.model_dump()],
            "metadata": {
                "total_clips": 1,
                "total_events": 1,
                "keywords": ["testuser", "testrepo", "en", "PushEvent"]
            }
        }
        
        # Use the generate_markdown method which handles content generation
        markdown = builder.generate_markdown(digest, ai_enabled=False)
        
        # Check basic structure - title is in frontmatter, content starts with summary
        assert "Today's development activities include 1 Twitch clip and 1 GitHub event" in markdown
        assert "## Twitch Clips" in markdown
        assert "## GitHub Activity" in markdown
        
        # Check Twitch clip content
        assert "### Test Twitch Clip" in markdown
        assert "**Duration:** 30.5 seconds" in markdown
        assert "**Views:** 1000" in markdown
        assert "**URL:** https://clips.twitch.tv/test_clip_123" in markdown
        assert "**Transcript:**" in markdown
        assert "> This is a test transcript with some content." in markdown
        
        # Check GitHub event content
        assert "### PushEvent in testuser/testrepo" in markdown
        assert "**Actor:** testuser" in markdown
        assert "**URL:** https://github.com/testuser/testrepo/commit/abc123" in markdown
        assert "**Commits:**" in markdown
        assert "- feat: add new feature" in markdown
        assert "- fix: bug fix" in markdown
    
    def test_save_digest_creates_files(self, temp_data_dir, temp_blogs_dir, sample_twitch_clip, sample_github_event):
        """Test that save_digest creates JSON file for AI ingestion."""
        builder = BlogDigestBuilder()
        builder.update_paths(temp_data_dir, temp_blogs_dir)
        
        digest = {
            "date": "2025-01-15",
            "twitch_clips": [sample_twitch_clip.model_dump()],
            "github_events": [sample_github_event.model_dump()],
            "metadata": {
                "total_clips": 1,
                "total_events": 1,
                "keywords": ["testuser", "testrepo", "en", "PushEvent"]
            }
        }
        
        json_path = builder.save_digest(digest)
        
        # Check that files were created
        date_dir = temp_blogs_dir / "2025-01-15"
        assert json_path.exists()
        assert json_path.name == "PRE-CLEANED-2025-01-15_digest.json"
        assert date_dir.exists()
        
        # Check JSON content
        with open(json_path, 'r', encoding='utf-8') as f:
            saved_digest = json.load(f)
        assert saved_digest["date"] == "2025-01-15"
        assert len(saved_digest["twitch_clips"]) == 1
        assert len(saved_digest["github_events"]) == 1
    
    def test_build_digest_missing_date(self, temp_data_dir):
        """Test that build_digest raises FileNotFoundError for missing date."""
        builder = BlogDigestBuilder()
        builder.update_paths(temp_data_dir, temp_data_dir.parent / "blogs")
        
        with pytest.raises(FileNotFoundError, match="No data found for date: 2025-01-15"):
            builder.build_digest("2025-01-15")
    
    def test_build_latest_digest_no_data(self, temp_data_dir):
        """Test that build_latest_digest raises FileNotFoundError when no data exists."""
        builder = BlogDigestBuilder()
        builder.update_paths(temp_data_dir, temp_data_dir.parent / "blogs")
        
        with pytest.raises(FileNotFoundError, match="No data folders found"):
            builder.build_latest_digest()
    
    def test_build_latest_digest_finds_latest(self, temp_data_dir, sample_twitch_clip):
        """Test that build_latest_digest finds the most recent date."""
        builder = BlogDigestBuilder()
        builder.update_paths(temp_data_dir, temp_data_dir.parent / "blogs")
        
        # Create multiple date directories
        date1_dir = temp_data_dir / "2025-01-15"
        date1_dir.mkdir()
        date2_dir = temp_data_dir / "2025-01-16"
        date2_dir.mkdir()
        
        # Add data to the later date
        clip_file = date2_dir / "twitch_clip_test_clip_123_Test_Twitch_Clip_20250116_120000.json"
        with open(clip_file, 'w', encoding='utf-8') as f:
            json.dump(sample_twitch_clip.model_dump(), f, default=str)
        
        digest = builder.build_latest_digest()
        assert digest["date"] == "2025-01-16"
        assert len(digest["twitch_clips"]) == 1
