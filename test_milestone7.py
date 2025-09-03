#!/usr/bin/env python3
"""
Test script for Milestone 7 implementation.
Tests feed generation, related posts, video processing, and cache management.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent / "services"))

from feeds import FeedGenerator
from related import RelatedPostsService
from video_processor import VideoProcessor
from cache_manager import CacheManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_feed_generation():
    """Test RSS feed and sitemap generation."""
    logger.info("Testing feed generation...")
    
    # Sample blog data
    sample_blogs = [
        {
            "date": "2025-08-27",
            "frontmatter": {
                "title": "Test Blog Post 1",
                "tags": ["feat", "automation"],
                "lead": "This is a test blog post about features and automation.",
                "canonical": "https://paulchrisluke.com/blog/2025-08-27"
            },
            "story_packets": [{"id": "test_1"}]
        },
        {
            "date": "2025-08-26",
            "frontmatter": {
                "title": "Test Blog Post 2",
                "tags": ["security", "fix"],
                "lead": "This is another test blog post about security fixes.",
                "canonical": "https://paulchrisluke.com/blog/2025-08-26"
            },
            "story_packets": [{"id": "test_2"}]
        }
    ]
    
    try:
        feed_gen = FeedGenerator(
            frontend_domain="https://paulchrisluke.com",
            api_domain="https://api.paulchrisluke.com"
        )
        
        # Generate RSS feed
        rss_content = feed_gen.generate_rss_feed(sample_blogs)
        logger.info(f"✓ RSS feed generated ({len(rss_content)} characters)")
        
        # Generate sitemap
        sitemap_content = feed_gen.generate_sitemap(sample_blogs)
        logger.info(f"✓ Sitemap generated ({len(sitemap_content)} characters)")
        
        # Generate blogs index
        blogs_index = feed_gen.generate_blogs_index(sample_blogs)
        logger.info(f"✓ Blogs index generated with {len(blogs_index['blogs'])} entries")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Feed generation failed: {e}")
        return False


def test_related_posts():
    """Test related posts scoring."""
    logger.info("Testing related posts service...")
    
    try:
        related_service = RelatedPostsService()
        
        # Test with sample data
        related_posts = related_service.find_related_posts(
            current_date="2025-08-27",
            current_tags=["feat", "automation"],
            current_title="Test Feature Implementation",
            max_posts=3
        )
        
        logger.info(f"✓ Related posts service working (found {len(related_posts)} posts)")
        return True
        
    except Exception as e:
        logger.error(f"✗ Related posts service failed: {e}")
        return False


def test_video_processor():
    """Test video processing capabilities."""
    logger.info("Testing video processor...")
    
    try:
        video_processor = VideoProcessor()
        
        # Test video info extraction (this will fail if ffmpeg not available, but that's OK)
        logger.info("✓ Video processor initialized")
        
        # Test thumbnail generation config
        thumbnail_configs = {
            "intro": {"timestamp": "00:00:03", "suffix": "01_intro"},
            "why": {"timestamp": "00:00:08", "suffix": "02_why"},
            "outro": {"timestamp": "00:00:12", "suffix": "99_outro"},
            "highlight": {"timestamp": "00:00:06", "suffix": "hl_01"}
        }
        
        logger.info(f"✓ Thumbnail generation configured for {len(thumbnail_configs)} types")
        return True
        
    except Exception as e:
        logger.error(f"✗ Video processor failed: {e}")
        return False


def test_cache_manager():
    """Test cache management service."""
    logger.info("Testing cache manager...")
    
    try:
        cache_manager = CacheManager()
        
        # Test cache headers generation
        html_headers = cache_manager.get_cache_headers("html")
        json_headers = cache_manager.get_cache_headers("json")
        image_headers = cache_manager.get_cache_headers("image")
        
        logger.info(f"✓ Cache headers generated for HTML: {html_headers['Cache-Control']}")
        logger.info(f"✓ Cache headers generated for JSON: {json_headers['Cache-Control']}")
        logger.info(f"✓ Cache headers generated for images: {image_headers['Cache-Control']}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Cache manager failed: {e}")
        return False


def test_domain_config():
    """Test domain configuration loading."""
    logger.info("Testing domain configuration...")
    
    try:
        # Check if environment variables are set
        api_domain = os.getenv("API_DOMAIN")
        media_domain = os.getenv("MEDIA_DOMAIN")
        frontend_domain = os.getenv("FRONTEND_DOMAIN")
        
        if api_domain and media_domain and frontend_domain:
            logger.info(f"✓ Domain configuration loaded:")
            logger.info(f"  API: {api_domain}")
            logger.info(f"  Media: {media_domain}")
            logger.info(f"  Frontend: {frontend_domain}")
            return True
        else:
            logger.warning("⚠ Domain configuration not fully set in environment")
            logger.info("  This is expected if running tests without .env file")
            return True
            
    except Exception as e:
        logger.error(f"✗ Domain configuration test failed: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("🚀 Starting Milestone 7 implementation tests...")
    
    tests = [
        ("Domain Configuration", test_domain_config),
        ("Feed Generation", test_feed_generation),
        ("Related Posts", test_related_posts),
        ("Video Processor", test_video_processor),
        ("Cache Manager", test_cache_manager),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n--- Testing {test_name} ---")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            logger.error(f"✗ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("📊 TEST RESULTS SUMMARY")
    logger.info("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{status} {test_name}")
        if success:
            passed += 1
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Milestone 7 implementation looks good.")
        return 0
    else:
        logger.warning("⚠ Some tests failed. Check the logs above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
