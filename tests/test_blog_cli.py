"""
Tests for the blog CLI commands.
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, Mock
import pytest
from click.testing import CliRunner

from cli.devlog import devlog


class TestBlogCLI:
    """Test cases for blog CLI commands."""
    
    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()
    
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
    def sample_digest(self):
        """Sample digest data for testing."""
        return {
            "version": "2",
            "date": "2025-01-15",
            "twitch_clips": [],
            "github_events": [],
            "metadata": {
                "total_clips": 0,
                "total_events": 0,
                "keywords": [],
                "date_parsed": "2025-01-15"
            },
            "frontmatter": {
                "title": "Daily Devlog — Jan 15, 2025",
                "date": "2025-01-15",
                "author": "Test Author",
                "tags": ["feat"],
                "lead": "Today's development work focused on new features."
            },
            "story_packets": []
        }
    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_generate_with_date(self, mock_builder_class, runner, temp_data_dir, temp_blogs_dir, sample_digest):
        """Test blog generate command with specific date."""
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.save_markdown.return_value = Path("drafts/2025-01-15.md")
        mock_builder_class.return_value = mock_builder
        
        # Mock Path to return our temp directories
        with patch('services.blog.Path') as mock_path:
            def mock_path_side_effect(path_str):
                if path_str == "data":
                    return temp_data_dir
                elif path_str == "blogs":
                    return temp_blogs_dir
                else:
                    return Path(path_str)
            
            mock_path.side_effect = mock_path_side_effect
            
            result = runner.invoke(devlog, ['blog', 'generate', '--date', '2025-01-15'])
        
        assert result.exit_code == 0
        assert "Generated blog post: drafts/2025-01-15.md" in result.output
        assert "Title: Daily Devlog — Jan 15, 2025" in result.output
        assert "Stories: 0" in result.output
        
        # Verify the builder was called correctly
        mock_builder.build_digest.assert_called_once_with("2025-01-15")
        mock_builder.generate_markdown.assert_called_once_with(
            sample_digest,
            ai_enabled=True,
            force_ai=False,
            related_enabled=True,
            jsonld_enabled=True
        )
        mock_builder.save_markdown.assert_called_once_with("2025-01-15", "# Test Blog Post\n\nContent here.")
    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_generate_without_date(self, mock_builder_class, runner, temp_data_dir, temp_blogs_dir, sample_digest):
        """Test blog generate command without date (uses latest)."""
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_latest_digest.return_value = sample_digest
        mock_builder.build_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.save_markdown.return_value = Path("drafts/2025-01-15.md")
        mock_builder_class.return_value = mock_builder
        
        # Mock Path to return our temp directories
        with patch('services.blog.Path') as mock_path:
            def mock_path_side_effect(path_str):
                if path_str == "data":
                    return temp_data_dir
                elif path_str == "blogs":
                    return temp_blogs_dir
                else:
                    return Path(path_str)
            
            mock_path.side_effect = mock_path_side_effect
            
            result = runner.invoke(devlog, ['blog', 'generate'])
        
        assert result.exit_code == 0
        assert "Using latest date: 2025-01-15" in result.output
        assert "Generated blog post: drafts/2025-01-15.md" in result.output
        
        # Verify the builder was called correctly
        mock_builder.build_latest_digest.assert_called_once()
        mock_builder.build_digest.assert_called_once_with("2025-01-15")
    
    def test_blog_generate_invalid_date(self, runner):
        """Test blog generate command with invalid date format."""
        result = runner.invoke(devlog, ['blog', 'generate', '--date', 'invalid-date'])
        
        assert result.exit_code == 1
        assert "Invalid date format: invalid-date. Use YYYY-MM-DD" in result.output
    
    @patch('services.blog.BlogDigestBuilder')
    @patch('services.github_publisher.publish_markdown')
    def test_blog_publish_success(self, mock_publish, mock_builder_class, runner, sample_digest):
        """Test blog publish command success."""
        # Mock environment variables
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo',
            'BLOG_AUTHOR_NAME': 'Test Author',
            'BLOG_AUTHOR_EMAIL': 'test@example.com'
        }
        
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
        mock_builder_class.return_value = mock_builder
        
        # Mock the publisher
        mock_publish.return_value = {
            "action": "created",
            "sha": "abc123",
            "html_url": "https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md"
        }
        
        with patch.dict('os.environ', env_vars):
            result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15'])
        
        assert result.exit_code == 0
        assert "Generated fresh markdown for 2025-01-15" in result.output
        assert "Blog created: https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md" in result.output
        
        # Verify the publisher was called correctly
        mock_publish.assert_called_once_with(
            owner="testowner",
            repo="testrepo",
            branch="main",
            path="content/blog/2025/01/15.md",
            content_md="# Test Blog Post\n\nContent here.",
            commit_message="Add daily devlog for 2025-01-15",
            author_name="Test Author",
            author_email="test@example.com",
            create_pr=False,
            pr_title=None,
            pr_body=None,
            include_assets=False,
            assets_info=None
        )
    
    @patch('services.blog.BlogDigestBuilder')
    @patch('services.github_publisher.publish_markdown')
    def test_blog_publish_with_pr(self, mock_publish, mock_builder_class, runner, sample_digest):
        """Test blog publish command with pull request creation."""
        # Mock environment variables
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo',
            'BLOG_AUTHOR_NAME': 'Test Author',
            'BLOG_AUTHOR_EMAIL': 'test@example.com'
        }
        
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
        mock_builder.collect_assets_for_publishing.return_value = {}  # No assets for this test
        mock_builder_class.return_value = mock_builder
        
        # Mock the publisher with PR
        mock_publish.return_value = {
            "action": "created",
            "sha": "abc123",
            "html_url": "https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md",
            "pr_url": "https://github.com/testowner/testrepo/pull/123"
        }
        
        with patch.dict('os.environ', env_vars):
            result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15', '--pr'])
        
        assert result.exit_code == 0
        assert "Blog created: https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md" in result.output
        assert "Pull request created: https://github.com/testowner/testrepo/pull/123" in result.output
        
        # Verify the publisher was called with PR options
        mock_publish.assert_called_once_with(
            owner="testowner",
            repo="testrepo",
            branch="main",
            path="content/blog/2025/01/15.md",
            content_md="# Test Blog Post\n\nContent here.",
            commit_message="Add daily devlog for 2025-01-15",
            author_name="Test Author",
            author_email="test@example.com",
            create_pr=True,
            pr_title="Daily Devlog — 2025-01-15",
            pr_body="Automated blog post for 2025-01-15",
            include_assets=True,
            assets_info={}
        )
    
    @patch('services.blog.BlogDigestBuilder')
    @patch('services.github_publisher.publish_markdown')
    def test_blog_publish_skipped(self, mock_publish, mock_builder_class, runner, sample_digest):
        """Test blog publish command when content is identical (skipped)."""
        # Mock environment variables
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo'
        }
        
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
        mock_builder_class.return_value = mock_builder
        
        # Mock the publisher returning skipped
        mock_publish.return_value = {
            "action": "skipped",
            "sha": "existing_sha",
            "html_url": "https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md"
        }
        
        with patch.dict('os.environ', env_vars):
            result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15'])
        
        assert result.exit_code == 0
        assert "No changes needed - content is identical" in result.output
    
    def test_blog_publish_missing_repo(self, runner):
        """Test blog publish command without BLOG_TARGET_REPO."""
        # Mock the blog builder to avoid data loading issues
        with patch('services.blog.BlogDigestBuilder') as mock_builder_class:
            mock_builder = Mock()
            mock_builder.build_digest.return_value = {
                "frontmatter": {"title": "Test Title"}
            }
            mock_builder.generate_markdown.return_value = "# Test Content"
            mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
            mock_builder_class.return_value = mock_builder
            
            # Mock the GitHub publisher to prevent real API calls
            with patch('services.github_publisher.publish_markdown') as mock_publish:
                # Clear any existing BLOG_TARGET_REPO from environment
                with patch.dict('os.environ', {}, clear=True):
                    result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15'])
                    
                    assert result.exit_code == 1
                    assert "BLOG_TARGET_REPO environment variable is required" in result.output
    
    def test_blog_publish_invalid_repo_format(self, runner):
        """Test blog publish command with invalid repo format."""
        env_vars = {'BLOG_TARGET_REPO': 'invalid-repo-format'}
        
        with patch.dict('os.environ', env_vars):
            result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15'])
        
        assert result.exit_code == 1
        assert "BLOG_TARGET_REPO must be in format 'owner/repo'" in result.output
    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_publish_use_draft(self, mock_builder_class, runner):
        """Test blog publish command using existing draft file."""
        # Mock environment variables
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo'
        }
        
        # Create a temporary draft file
        with tempfile.TemporaryDirectory() as temp_dir:
            drafts_dir = Path(temp_dir) / "drafts"
            drafts_dir.mkdir()
            draft_file = drafts_dir / "2025-01-15.md"
            draft_file.write_text("# Draft Content\n\nThis is draft content.")
            
            # Mock the blog builder
            mock_builder = Mock()
            mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
            mock_builder_class.return_value = mock_builder
            
            # Mock the publisher
            with patch('services.github_publisher.publish_markdown') as mock_publish:
                mock_publish.return_value = {
                    "action": "created",
                    "sha": "abc123",
                    "html_url": "https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md"
                }
                
                # Mock the file reading to return our draft content
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = "# Draft Content\n\nThis is draft content."
                    
                    with patch('pathlib.Path.exists') as mock_exists:
                        mock_exists.return_value = True
                        
                        with patch.dict('os.environ', env_vars):
                            result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15', '--use-draft'])
                        
                        assert result.exit_code == 0
                        assert "Using existing draft: drafts/2025-01-15.md" in result.output
                
                # Verify the publisher was called with draft content
                mock_publish.assert_called_once()
                call_args = mock_publish.call_args[1]
                assert call_args['content_md'] == "# Draft Content\n\nThis is draft content."
    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_publish_draft_not_found(self, mock_builder_class, runner):
        """Test blog publish command when draft file doesn't exist."""
        # Mock environment variables
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo'
        }
        
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder_class.return_value = mock_builder
        
        with patch.dict('os.environ', env_vars):
            result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15', '--use-draft'])
        
        assert result.exit_code == 1
        assert "Draft file not found: drafts/2025-01-15.md" in result.output
    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_preview(self, mock_builder_class, runner, sample_digest):
        """Test blog preview command."""
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = """---
title: Daily Devlog — Jan 15, 2025
date: 2025-01-15
---

# Daily Devlog — Jan 15, 2025

Today's development work focused on new features.

## Stories

### New Features

#### Feature Implementation

**Why:** To improve user experience

**Highlights:**
- Added new functionality
- Improved performance
"""
        mock_builder_class.return_value = mock_builder
        
        result = runner.invoke(devlog, ['blog', 'preview', '--date', '2025-01-15'])
        
        assert result.exit_code == 0
        assert "Title: Daily Devlog — Jan 15, 2025" in result.output
        assert "Date: 2025-01-15" in result.output
        assert "Tags: feat" in result.output
        assert "Preview:" in result.output
        assert "  # Daily Devlog — Jan 15, 2025" in result.output
        assert "  Today's development work focused on new features." in result.output
    
    @patch('httpx.Client')
    def test_discord_notification_sent(self, mock_client, runner):
        """Test that Discord notification is sent on successful publish."""
        # Mock environment variables
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo',
            'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test'
        }
        
        # Mock the blog builder
        with patch('services.blog.BlogDigestBuilder') as mock_builder_class:
            mock_builder = Mock()
            mock_builder.build_digest.return_value = {
                "frontmatter": {"title": "Test Title"}
            }
            mock_builder.generate_markdown.return_value = "# Test Content"
            mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
            mock_builder_class.return_value = mock_builder
            
            # Mock the publisher
            with patch('services.github_publisher.publish_markdown') as mock_publish:
                mock_publish.return_value = {
                    "action": "created",
                    "html_url": "https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md"
                }
                
                # Mock Discord webhook
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client_instance = Mock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__enter__.return_value = mock_client_instance
                
                with patch.dict('os.environ', env_vars):
                    result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15'])
                
                assert result.exit_code == 0
                assert "Discord notification sent" in result.output
                
                # Verify Discord webhook was called
                mock_client_instance.post.assert_called_once()
                webhook_call = mock_client_instance.post.call_args
                assert webhook_call[0][0] == 'https://discord.com/api/webhooks/test'
                assert "Blog published" in webhook_call[1]['json']['content']
    
    def test_discord_notification_no_webhook(self, runner):
        """Test that no Discord notification is sent when webhook URL is not set."""
        # Mock environment variables (no Discord webhook)
        env_vars = {
            'BLOG_TARGET_REPO': 'testowner/testrepo'
        }
        
        # Mock the blog builder
        with patch('services.blog.BlogDigestBuilder') as mock_builder_class:
            mock_builder = Mock()
            mock_builder.build_digest.return_value = {
                "frontmatter": {"title": "Test Title"}
            }
            mock_builder.generate_markdown.return_value = "# Test Content"
            mock_builder.compute_target_path.return_value = "content/blog/2025/01/15.md"
            mock_builder_class.return_value = mock_builder
            
            # Mock the publisher
            with patch('services.github_publisher.publish_markdown') as mock_publish:
                mock_publish.return_value = {
                    "action": "created",
                    "html_url": "https://github.com/testowner/testrepo/blob/main/content/blog/2025/01/15.md"
                }
                
                # Mock httpx to prevent actual Discord webhook calls
                with patch('httpx.Client') as mock_httpx:
                    # Ensure DISCORD_WEBHOOK_URL is not set
                    with patch.dict('os.environ', env_vars, clear=True):
                        result = runner.invoke(devlog, ['blog', 'publish', '--date', '2025-01-15'])
                    
                    assert result.exit_code == 0
                    assert "Discord notification sent" not in result.output
