"""
Tests for the API v3 serializer to ensure it produces the correct JSON shape.
"""

import pytest
import json
from datetime import datetime, timezone
from services.serializers.api_v3 import build


class TestApiV3Serializer:
    """Test the API v3 serializer produces the correct target JSON shape."""
    
    @pytest.fixture
    def mock_normalized_digest(self):
        """Create a mock normalized digest for testing."""
        return {
            'date': '2025-08-25',
            'frontmatter': {
                'title': 'PCL Labs Devlog: AI-Powered Blog Generation',
                'description': 'A comprehensive look at AI-powered blog generation with schema automation.',
                'tags': ['ai', 'blog', 'automation', 'schema', 'devlog']
            },
            'story_packets': [
                {
                    'id': 'story_20250825_pr29',
                    'title_human': 'Improve API Landing Page',
                    'why': 'Enhanced the API landing page with better documentation and examples.',
                    'highlights': [
                        'Added comprehensive API documentation',
                        'Improved error handling and validation',
                        'Enhanced user experience with better examples'
                    ],
                    'merged_at': '2025-08-25T10:00:00Z',
                    'video': {
                        'status': 'rendered',
                        'path': 'https://media.paulchrisluke.com/stories/2025/08/25/story_20250825_pr29.mp4',
                        'thumbnails': {
                            'intro': 'https://media.paulchrisluke.com/stories/2025/08/25/story_20250825_pr29_01_intro.png'
                        }
                    }
                },
                {
                    'id': 'story_20250825_pr30',
                    'title_human': 'Schema SEO Improvements',
                    'why': 'Implemented better schema.org markup for improved SEO.',
                    'highlights': [
                        'Added structured data for blog posts',
                        'Improved search engine visibility',
                        'Enhanced social media sharing'
                    ],
                    'merged_at': '2025-08-25T11:00:00Z',
                    'video': {
                        'status': 'rendered',
                        'path': 'https://media.paulchrisluke.com/stories/2025/08/25/story_20250825_pr30.mp4',
                        'thumbnails': {
                            'intro': 'https://media.paulchrisluke.com/stories/2025/08/25/story_20250825_pr30_01_intro.png'
                        }
                    }
                }
            ],
            'related_posts': [
                {
                    'title': 'Previous Devlog: Automation Setup',
                    'url': 'https://paulchrisluke.com/blog/2025/08/24/automation-setup/',
                    'image': 'https://media.paulchrisluke.com/related.jpg',
                    'score': 0.85
                }
            ],
            'content': {
                'body': 'This is a comprehensive blog post about AI-powered blog generation. It covers various aspects of automation, schema markup, and content generation. The post includes detailed explanations and examples of how the system works.'
            }
        }
    
    def test_serializer_produces_correct_structure(self, mock_normalized_digest):
        """Test that the serializer produces the exact target JSON shape."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        # Check top-level structure
        expected_keys = {
            '_meta', 'url', 'datePublished', 'dateModified', 'wordCount', 
            'timeRequired', 'content', 'media', 'stories', 'related', 
            'schema', 'headers'
        }
        assert set(result.keys()) == expected_keys
        
        # Check _meta structure
        assert result['_meta']['kind'] == 'PublishPackage'
        assert result['_meta']['version'] == 1
        assert 'generated_at' in result['_meta']
        
        # Check content structure
        content = result['content']
        assert 'title' in content
        assert 'summary' in content
        assert 'body' in content
        assert 'tags' in content
        assert isinstance(content['tags'], list)
        
        # Check media structure
        media = result['media']
        assert 'hero' in media
        assert 'videos' in media
        assert 'image' in media['hero']
        assert isinstance(media['videos'], list)
        
        # Check stories structure
        stories = result['stories']
        assert isinstance(stories, list)
        assert len(stories) == 2
        
        for story in stories:
            assert 'id' in story
            assert 'title' in story
            assert 'why' in story
            assert 'highlights' in story
            assert 'videoId' in story
            assert 'mergedAt' in story
            assert isinstance(story['highlights'], list)
        
        # Check related structure
        related = result['related']
        assert isinstance(related, list)
        assert len(related) == 1
        assert 'title' in related[0]
        assert 'url' in related[0]
        assert 'image' in related[0]
        assert 'score' in related[0]
        
        # Check schema structure
        schema = result['schema']
        assert schema['@type'] == 'BlogPosting'
        assert 'headline' in schema
        assert 'description' in schema
        assert 'image' in schema
        assert 'url' in schema
        assert 'video' in schema
        assert isinstance(schema['video'], list)
        
        # Check headers structure
        headers = result['headers']
        assert 'X-Robots-Tag' in headers
        assert 'Cache-Control' in headers
        assert 'ETag' in headers
    
    def test_no_deprecated_fields(self, mock_normalized_digest):
        """Test that no deprecated fields are present in the output."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        # Check that deprecated fields are NOT present
        deprecated_fields = ['frontmatter', 'seo_meta', 'articleBody', 'headline', 'description', 'image', 'video']
        for field in deprecated_fields:
            assert field not in result, f"Deprecated field '{field}' should not be present"
    
    def test_video_references_work_correctly(self, mock_normalized_digest):
        """Test that story video references work correctly."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        # Get video IDs from media.videos
        video_ids = {video['id'] for video in result['media']['videos']}
        assert len(video_ids) == 2
        assert 'story_20250825_pr29' in video_ids
        assert 'story_20250825_pr30' in video_ids
        
        # Check that stories reference correct video IDs
        for story in result['stories']:
            if story['videoId']:
                assert story['videoId'] in video_ids
                assert story['videoId'] == story['id']
    
    def test_canonical_url_generation(self, mock_normalized_digest):
        """Test that canonical URLs are generated correctly."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        url = result['url']
        assert url.startswith('https://paulchrisluke.com/blog/2025/08/25/')
        assert url.endswith('/')
        
        # Check that schema.url matches root url
        assert result['schema']['url'] == url
    
    def test_word_count_and_time_required(self, mock_normalized_digest):
        """Test that word count and time required are calculated correctly."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        word_count = result['wordCount']
        time_required = result['timeRequired']
        
        assert isinstance(word_count, int)
        assert word_count > 0
        assert time_required.startswith('PT')
        assert time_required.endswith('M')
        
        # Check that schema has the same word count
        assert result['schema']['wordCount'] == word_count
    
    def test_hero_image_selection(self, mock_normalized_digest):
        """Test that hero image is selected from first video thumbnail."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        hero_image = result['media']['hero']['image']
        first_video_thumb = result['media']['videos'][0]['thumb']
        
        assert hero_image == first_video_thumb
        assert hero_image.startswith('https://media.paulchrisluke.com')
    
    def test_ai_placeholder_cleanup(self, mock_normalized_digest):
        """Test that AI placeholders are cleaned up."""
        # Add AI placeholders to the mock data
        mock_normalized_digest['content']['body'] = 'This is content with [AI_GENERATE_LEAD] placeholder text.'
        mock_normalized_digest['frontmatter']['description'] = 'Description with [AI_GENERATE_SEO_DESCRIPTION] placeholder.'
        
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        # Check that placeholders are removed
        assert '[AI_GENERATE_LEAD]' not in result['content']['body']
        assert '[AI_GENERATE_SEO_DESCRIPTION]' not in result['content']['summary']
    
    def test_etag_generation(self, mock_normalized_digest):
        """Test that ETag is generated correctly."""
        result = build(
            mock_normalized_digest,
            'Paul Chris Luke',
            'https://paulchrisluke.com',
            'https://media.paulchrisluke.com'
        )
        
        etag = result['headers']['ETag']
        assert etag.startswith('"')
        assert etag.endswith('"')
        assert len(etag) > 10  # Should be a reasonable length hash
