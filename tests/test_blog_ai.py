"""
Tests for AI blog generation functionality.
"""

import json
import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
from datetime import datetime

from services.blog import BlogDigestBuilder


class TestBlogAIGeneration:
    """Test AI blog generation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.test_date = "2025-08-29"
        self.mock_ai_response = {
            "date": self.test_date,
            "frontmatter": {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": "Daily Devlog — Aug 29, 2025",
                "datePublished": self.test_date,
                "author": "Paul Chris Luke",
                "keywords": ["twitch", "github", "AI"],
                "video": [],
                "faq": [],
                "og": {
                    "title": "Daily Devlog — Aug 29, 2025",
                    "description": "Daily development log",
                    "type": "article",
                    "url": "https://paulchrisluke.com/2025-08-29",
                    "image": "https://paulchrisluke.com/default.jpg"
                }
            },
            "body": "# Daily Devlog — August 29, 2025\n\nToday was a productive day..."
        }
    
    @patch.dict('os.environ', {'CLOUDFLARE_WORKER_URL': 'https://test-worker.workers.dev'})
    @patch('services.blog.requests.post')
    def test_generate_ai_blog_success(self, mock_post):
        """Test successful AI blog generation."""
        # Create builder after environment is patched
        builder = BlogDigestBuilder()
        
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = self.mock_ai_response
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Mock the build_digest method
        with patch.object(builder, 'build_digest') as mock_build:
            mock_build.return_value = {
                "date": self.test_date,
                "twitch_clips": [],
                "github_events": [],
                "metadata": {"total_clips": 0, "total_events": 0, "keywords": []}
            }
            
            result = builder.generate_ai_blog(self.test_date)
            
            # Verify the result
            assert result == self.mock_ai_response
            assert "frontmatter" in result
            assert "body" in result
            
            # Verify the request was made correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://test-worker.workers.dev/generate-blog"
            assert call_args[1]["headers"]["Content-Type"] == "application/json"
            assert call_args[1]["timeout"] == 60
    
    @patch.dict('os.environ', {'CLOUDFLARE_WORKER_URL': ''})
    def test_generate_ai_blog_no_worker_url(self):
        """Test AI blog generation without worker URL configured."""
        builder = BlogDigestBuilder()
        with pytest.raises(ValueError, match="CLOUDFLARE_WORKER_URL not configured"):
            builder.generate_ai_blog(self.test_date)
    
    @patch.dict('os.environ', {'CLOUDFLARE_WORKER_URL': 'https://test-worker.workers.dev'})
    @patch('services.blog.requests.post')
    def test_generate_ai_blog_http_error(self, mock_post):
        """Test AI blog generation with HTTP error."""
        builder = BlogDigestBuilder()
        
        # Mock HTTP error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_post.return_value = mock_response
        
        with patch.object(builder, 'build_digest'):
            with pytest.raises(Exception, match="HTTP Error"):
                builder.generate_ai_blog(self.test_date)
    
    @patch.dict('os.environ', {'CLOUDFLARE_WORKER_URL': 'https://test-worker.workers.dev'})
    @patch('services.blog.requests.post')
    def test_generate_ai_blog_invalid_response(self, mock_post):
        """Test AI blog generation with invalid response format."""
        builder = BlogDigestBuilder()
        
        # Mock invalid response
        mock_response = Mock()
        mock_response.json.return_value = "not a dict"
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        with patch.object(builder, 'build_digest'):
            with pytest.raises(RuntimeError, match="Invalid response from AI service"):
                builder.generate_ai_blog(self.test_date)
    
    @patch.dict('os.environ', {'CLOUDFLARE_WORKER_URL': 'https://test-worker.workers.dev'})
    @patch('services.blog.requests.post')
    def test_generate_ai_blog_missing_fields(self, mock_post):
        """Test AI blog generation with missing required fields."""
        builder = BlogDigestBuilder()
        
        # Mock response missing required fields
        mock_response = Mock()
        mock_response.json.return_value = {"date": self.test_date}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        with patch.object(builder, 'build_digest'):
            with pytest.raises(RuntimeError, match="Invalid response from AI service"):
                builder.generate_ai_blog(self.test_date)
    
    @patch('services.utils.CacheManager')
    def test_save_ai_draft(self, mock_cache_manager_class):
        """Test saving AI draft to file."""
        builder = BlogDigestBuilder()
        
        # Mock the cache manager
        mock_cache_manager = Mock()
        mock_cache_manager_class.return_value = mock_cache_manager
        
        # Mock Path.exists and mkdir
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(Path, 'mkdir') as mock_mkdir:
            
            result = builder.save_ai_draft(self.test_date, self.mock_ai_response)
            
            # Verify the draft was saved
            assert result == Path("drafts") / f"{self.test_date}-DRAFT.json"
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
            mock_cache_manager.atomic_write_json.assert_called_once()
    
    def test_load_digest_from_file_exists(self):
        """Test loading digest from file when it exists."""
        builder = BlogDigestBuilder()
        test_digest = {"date": self.test_date, "data": "test"}
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(test_digest))):
            
            result = builder.load_digest_from_file(self.test_date)
            assert result == test_digest
    
    def test_load_digest_from_file_not_exists(self):
        """Test loading digest from file when it doesn't exist."""
        builder = BlogDigestBuilder()
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(builder, 'build_digest') as mock_build:
            
            mock_build.return_value = {"date": self.test_date, "data": "built"}
            result = builder.load_digest_from_file(self.test_date)
            
            assert result == {"date": self.test_date, "data": "built"}
            mock_build.assert_called_once_with(self.test_date)
    
    def test_voice_prompt_path_configuration(self):
        """Test voice prompt path configuration."""
        # Test custom path from environment (current setting)
        with patch.dict('os.environ', {'BLOG_VOICE_PROMPT_PATH': 'prompts/paul_chris_luke.md'}):
            builder = BlogDigestBuilder()
            assert builder.voice_prompt_path == "prompts/paul_chris_luke.md"
        
        # Test default path when no environment variable is set
        with patch.dict('os.environ', {}, clear=True):
            builder = BlogDigestBuilder()
            assert builder.voice_prompt_path == "prompts/default_voice.md"
