"""
Tests for the GitHub publisher service.
"""

import base64
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, Mock
import pytest
import httpx

from services.github_publisher import GitHubPublisher, publish_markdown


class TestGitHubPublisher:
    """Test cases for GitHubPublisher."""
    
    @pytest.fixture
    def publisher(self):
        """Create a GitHubPublisher instance with mocked token."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test_token'}):
            return GitHubPublisher()
    
    @pytest.fixture
    def sample_markdown(self):
        """Sample markdown content for testing."""
        return """# Test Blog Post

This is a test blog post content.

## Section 1

Some content here.

## Section 2

More content here."""
    
    def test_init_without_token(self):
        """Test that __init__ raises error without GITHUB_TOKEN."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="GITHUB_TOKEN environment variable is required"):
                GitHubPublisher()
    
    def test_init_with_token(self):
        """Test that __init__ works with valid token."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test_token'}):
            publisher = GitHubPublisher()
            assert publisher.github_token == 'test_token'
            assert publisher.base_url == 'https://api.github.com'
            assert publisher.headers['Authorization'] == 'Bearer test_token'
    
    @patch('httpx.Client')
    def test_publish_markdown_create_new_file(self, mock_client, publisher, sample_markdown):
        """Test creating a new file."""
        # Mock file not existing (404)
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        # Mock successful file creation
        mock_response_201 = Mock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "content": {
                "sha": "abc123",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
            }
        }
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response_404
        mock_client_instance.put.return_value = mock_response_201
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        result = publisher.publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit"
        )
        
        assert result["action"] == "created"
        assert result["sha"] == "abc123"
        assert result["html_url"] == "https://github.com/owner/repo/blob/main/path/file.md"
        
        # Verify API calls
        mock_client_instance.get.assert_called_once()
        mock_client_instance.put.assert_called_once()
        
        # Verify content was base64 encoded
        put_call = mock_client_instance.put.call_args
        content_b64 = put_call[1]['json']['content']
        decoded = base64.b64decode(content_b64).decode('utf-8')
        assert decoded == sample_markdown
    
    @patch('httpx.Client')
    def test_publish_markdown_update_existing_file(self, mock_client, publisher, sample_markdown):
        """Test updating an existing file."""
        # Mock file existing with different content
        existing_content = "old content"
        existing_content_b64 = base64.b64encode(existing_content.encode('utf-8')).decode('utf-8')
        
        mock_response_get = Mock()
        mock_response_get.status_code = 200
        mock_response_get.json.return_value = {
            "sha": "old_sha",
            "content": existing_content_b64,
            "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
        }
        
        # Mock successful file update
        mock_response_put = Mock()
        mock_response_put.status_code = 200
        mock_response_put.json.return_value = {
            "content": {
                "sha": "new_sha",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
            }
        }
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response_get
        mock_client_instance.put.return_value = mock_response_put
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        result = publisher.publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit"
        )
        
        assert result["action"] == "updated"
        assert result["sha"] == "new_sha"
        
        # Verify SHA was included in update
        put_call = mock_client_instance.put.call_args
        assert put_call[1]['json']['sha'] == "old_sha"
    
    @patch('httpx.Client')
    def test_publish_markdown_skip_identical_content(self, mock_client, publisher, sample_markdown):
        """Test skipping when content is identical."""
        # Mock file existing with identical content
        content_b64 = base64.b64encode(sample_markdown.encode('utf-8')).decode('utf-8')
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sha": "existing_sha",
            "content": content_b64,
            "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
        }
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        result = publisher.publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit"
        )
        
        assert result["action"] == "skipped"
        assert result["sha"] == "existing_sha"
        
        # Verify no PUT call was made
        mock_client_instance.put.assert_not_called()
    
    @patch('httpx.Client')
    def test_publish_markdown_with_author_info(self, mock_client, publisher, sample_markdown):
        """Test publishing with author information."""
        # Mock file not existing
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        mock_response_201 = Mock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "content": {
                "sha": "abc123",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
            }
        }
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response_404
        mock_client_instance.put.return_value = mock_response_201
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        result = publisher.publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit",
            author_name="Test Author",
            author_email="test@example.com"
        )
        
        # Verify author info was included
        put_call = mock_client_instance.put.call_args
        assert put_call[1]['json']['author'] == {
            "name": "Test Author",
            "email": "test@example.com"
        }
    
    @patch('httpx.Client')
    def test_publish_markdown_with_pr(self, mock_client, publisher, sample_markdown):
        """Test publishing with pull request creation."""
        # Mock file not existing
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        # Mock successful file creation
        mock_response_201 = Mock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "content": {
                "sha": "abc123",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
            }
        }
        
        # Mock branch creation
        mock_response_branch = Mock()
        mock_response_branch.status_code = 201
        
        # Mock PR creation
        mock_response_pr = Mock()
        mock_response_pr.status_code = 201
        mock_response_pr.json.return_value = {
            "html_url": "https://github.com/owner/repo/pull/123"
        }
        
        # Mock branch reference response
        mock_response_ref = Mock()
        mock_response_ref.status_code = 200
        mock_response_ref.json.return_value = {
            "object": {
                "sha": "main_sha_123"
            }
        }
        
        mock_client_instance = Mock()
        mock_client_instance.get.side_effect = [
            mock_response_404,  # File check
            mock_response_ref,  # Branch reference
            mock_response_pr  # PR creation
        ]
        mock_client_instance.put.return_value = mock_response_201
        mock_client_instance.post.side_effect = [
            mock_response_branch,  # Branch creation
            mock_response_pr  # PR creation
        ]
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        result = publisher.publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit",
            create_pr=True,
            pr_title="Test PR",
            pr_body="Test PR body"
        )
        
        assert result["action"] == "created"
        assert result["pr_url"] == "https://github.com/owner/repo/pull/123"
    
    @patch('httpx.Client')
    def test_publish_markdown_authentication_error(self, mock_client, publisher, sample_markdown):
        """Test handling of authentication errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=Mock(), response=mock_response
        )
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with pytest.raises(RuntimeError, match="Failed to check file existence"):
            publisher.publish_markdown(
                owner="owner",
                repo="repo",
                path="path/file.md",
                content_md=sample_markdown,
                commit_message="Test commit"
            )
    
    @patch('httpx.Client')
    def test_publish_markdown_permission_error(self, mock_client, publisher, sample_markdown):
        """Test handling of permission errors."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=Mock(), response=mock_response
        )
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with pytest.raises(RuntimeError, match="Failed to check file existence"):
            publisher.publish_markdown(
                owner="owner",
                repo="repo",
                path="path/file.md",
                content_md=sample_markdown,
                commit_message="Test commit"
            )
    
    @patch('httpx.Client')
    def test_publish_markdown_repo_not_found(self, mock_client, publisher, sample_markdown):
        """Test handling of repository not found errors."""
        # Mock file not existing (404)
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        # Mock successful file creation
        mock_response_201 = Mock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "content": {
                "sha": "abc123",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
            }
        }
        
        mock_client_instance = Mock()
        mock_client_instance.get.return_value = mock_response_404
        mock_client_instance.put.return_value = mock_response_201
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        result = publisher.publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit"
        )
        
        assert result["action"] == "created"
        assert result["sha"] == "abc123"
    
    def test_publish_markdown_validation_errors(self, publisher):
        """Test input validation."""
        with pytest.raises(ValueError, match="owner and repo are required"):
            publisher.publish_markdown(
                owner="",
                repo="repo",
                path="path/file.md",
                content_md="content",
                commit_message="commit"
            )
        
        with pytest.raises(ValueError, match="path is required"):
            publisher.publish_markdown(
                owner="owner",
                repo="repo",
                path="",
                content_md="content",
                commit_message="commit"
            )
        
        with pytest.raises(ValueError, match="content_md is required"):
            publisher.publish_markdown(
                owner="owner",
                repo="repo",
                path="path/file.md",
                content_md="",
                commit_message="commit"
            )
        
        with pytest.raises(ValueError, match="commit_message is required"):
            publisher.publish_markdown(
                owner="owner",
                repo="repo",
                path="path/file.md",
                content_md="content",
                commit_message=""
            )


class TestPublishMarkdownFunction:
    """Test cases for the convenience function."""
    
    @patch('services.github_publisher.GitHubPublisher')
    def test_publish_markdown_function(self, mock_publisher_class):
        """Test the convenience function."""
        sample_markdown = "# Test Content"
        mock_publisher = Mock()
        mock_publisher.publish_markdown.return_value = {
            "action": "created",
            "sha": "abc123",
            "html_url": "https://github.com/owner/repo/blob/main/path/file.md"
        }
        mock_publisher_class.return_value = mock_publisher
        
        result = publish_markdown(
            owner="owner",
            repo="repo",
            path="path/file.md",
            content_md=sample_markdown,
            commit_message="Test commit"
        )
        
        mock_publisher.publish_markdown.assert_called_once()
        assert result["action"] == "created"
