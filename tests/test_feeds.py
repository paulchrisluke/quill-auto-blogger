"""
Tests for the feeds service.
"""

import pytest
from datetime import datetime
from services.feeds import FeedGenerator


class TestFeedGenerator:
    """Test cases for FeedGenerator class."""
    
    @pytest.fixture
    def feed_generator(self):
        """Create FeedGenerator instance with test domains."""
        return FeedGenerator(
            frontend_domain="https://testblog.com",
            api_domain="https://api.testblog.com"
        )
    
    @pytest.fixture
    def sample_blogs_data(self):
        """Sample blog data for testing."""
        return [
            {
                "date": "2025-08-27",
                "frontmatter": {
                    "title": "Test Blog Post 1",
                    "tags": ["feat", "automation"],
                    "lead": "This is a test blog post about features and automation.",
                    "canonical": "https://testblog.com/blog/2025-08-27"
                },
                "story_packets": [{"id": "test_1"}]
            },
            {
                "date": "2025-08-26",
                "frontmatter": {
                    "title": "Test Blog Post 2",
                    "tags": ["security", "fix"],
                    "lead": "This is another test blog post about security fixes.",
                    "canonical": "https://testblog.com/blog/2025-08-26"
                },
                "story_packets": [{"id": "test_2"}]
            }
        ]
    
    def test_init(self, feed_generator):
        """Test FeedGenerator initialization."""
        assert feed_generator.frontend_domain == "https://testblog.com"
        assert feed_generator.api_domain == "https://api.testblog.com"
    
    def test_generate_rss_feed(self, feed_generator, sample_blogs_data):
        """Test RSS feed generation."""
        rss_content = feed_generator.generate_rss_feed(sample_blogs_data)
        
        # Check basic RSS structure
        assert '<?xml version="1.0" encoding="UTF-8"?>' in rss_content
        assert '<rss version="2.0"' in rss_content
        assert '<channel>' in rss_content
        assert '</channel>' in rss_content
        
        # Check channel metadata
        assert '<title>Paul Chris Luke - PCL Labs</title>' in rss_content
        assert '<link>https://testblog.com</link>' in rss_content
        assert '<description>Daily development log with AI-enhanced content, Twitch clips, and GitHub events. Featuring automation, programming insights, and technical tutorials from PCL Labs.</description>' in rss_content
        
        # Check items
        assert '<item>' in rss_content
        assert 'Test Blog Post 1' in rss_content
        assert 'Test Blog Post 2' in rss_content
        
        # Check canonical URLs
        assert 'https://testblog.com/blog/2025-08-27' in rss_content
        assert 'https://testblog.com/blog/2025-08-26' in rss_content
    
    def test_generate_sitemap(self, feed_generator, sample_blogs_data):
        """Test sitemap generation."""
        sitemap_content = feed_generator.generate_sitemap(sample_blogs_data)
        
        # Check basic sitemap structure
        assert '<?xml version="1.0" encoding="UTF-8"?>' in sitemap_content
        assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in sitemap_content
        assert '</urlset>' in sitemap_content
        
        # Check homepage entry
        assert '<loc>https://testblog.com</loc>' in sitemap_content
        
        # Check blog entries
        assert 'https://testblog.com/blog/2025-08-27' in sitemap_content
        assert 'https://testblog.com/blog/2025-08-26' in sitemap_content
        
        # Check dates
        assert '2025-08-27' in sitemap_content
        assert '2025-08-26' in sitemap_content
    
    def test_generate_blogs_index(self, feed_generator, sample_blogs_data):
        """Test blogs index generation."""
        blogs_index = feed_generator.generate_blogs_index(sample_blogs_data)
        
        # Check metadata
        assert 'meta' in blogs_index
        assert blogs_index['meta']['total_blogs'] == 2
        assert blogs_index['meta']['frontend_domain'] == 'https://testblog.com'
        assert blogs_index['meta']['api_domain'] == 'https://api.testblog.com'
        
        # Check blogs array
        assert 'blogs' in blogs_index
        assert len(blogs_index['blogs']) == 2
        
        # Check first blog entry
        first_blog = blogs_index['blogs'][0]
        assert first_blog['date'] == '2025-08-27'
        assert first_blog['title'] == 'Test Blog Post 1'
        assert first_blog['canonical_url'] == 'https://testblog.com/blog/2025-08-27'
        assert first_blog['tags'] == ['feat', 'automation']
        assert first_blog['story_count'] == 1
        assert first_blog['has_video'] is False
    
    def test_empty_blogs_data(self, feed_generator):
        """Test handling of empty blogs data."""
        empty_data = []
        
        # RSS feed
        rss_content = feed_generator.generate_rss_feed(empty_data)
        assert '<channel>' in rss_content
        assert '<item>' not in rss_content
        
        # Sitemap
        sitemap_content = feed_generator.generate_sitemap(empty_data)
        assert '<urlset' in sitemap_content
        assert 'https://testblog.com' in sitemap_content  # Homepage should still be there
        
        # Blogs index
        blogs_index = feed_generator.generate_blogs_index(empty_data)
        assert blogs_index['meta']['total_blogs'] == 0
        assert len(blogs_index['blogs']) == 0
    
    def test_blogs_with_missing_frontmatter(self, feed_generator):
        """Test handling of blogs with missing frontmatter."""
        incomplete_data = [
            {
                "date": "2025-08-27",
                "frontmatter": {
                    "title": "Valid Post",
                    "canonical": "https://testblog.com/blog/2025-08-27"
                }
            },
            {
                "date": "2025-08-26"
                # Missing frontmatter
            }
        ]
        
        # Should handle gracefully
        rss_content = feed_generator.generate_rss_feed(incomplete_data)
        sitemap_content = feed_generator.generate_sitemap(incomplete_data)
        blogs_index = feed_generator.generate_blogs_index(incomplete_data)
        
        # Valid post should be included
        assert 'Valid Post' in rss_content
        assert 'https://testblog.com/blog/2025-08-27' in sitemap_content
        assert len(blogs_index['blogs']) == 1
    
    def test_domain_stripping(self):
        """Test that domains are properly stripped of trailing slashes."""
        feed_gen = FeedGenerator(
            frontend_domain="https://testblog.com/",
            api_domain="https://api.testblog.com/"
        )
        
        assert feed_gen.frontend_domain == "https://testblog.com"
        assert feed_gen.api_domain == "https://api.testblog.com"
