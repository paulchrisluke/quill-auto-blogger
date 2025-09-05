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
                "title": "PCL-Labs — Jan 15, 2025",
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
        mock_builder.build_normalized_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.save_markdown.return_value = Path("drafts/2025-01-15.md")
        
        # Mock the io object and its methods
        mock_io = Mock()
        mock_io.save_digest.return_value = Path("data/2025-01-15/digest.normalized.json")
        mock_builder.io = mock_io
        
        # Mock additional methods called by the CLI
        mock_builder.create_final_digest.return_value = {
            "ai_generated_content": {
                "title": "PCL-Labs — Jan 15, 2025",
                "description": "Today's development work focused on new features.",
                "tags": ["feat"]
            }
        }
        mock_builder.assemble_publish_package.return_value = {
            "content": {"title": "PCL-Labs — Jan 15, 2025"}
        }
        
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
        assert "Saved normalized digest: data/2025-01-15/digest.normalized.json" in result.output
        assert "Created FINAL digest with AI enhancements" in result.output
        assert "AI-generated blog content available" in result.output
        assert "Title: PCL-Labs — Jan 15, 2025" in result.output
        
        # Verify the builder was called correctly
        mock_builder.build_normalized_digest.assert_called_once_with("2025-01-15")
        mock_builder.io.save_digest.assert_called_once()
        mock_builder.create_final_digest.assert_called_once_with("2025-01-15")
        mock_builder.assemble_publish_package.assert_called_once_with("2025-01-15")
    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_generate_without_date(self, mock_builder_class, runner, temp_data_dir, temp_blogs_dir, sample_digest):
        """Test blog generate command without date (uses latest)."""
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_latest_digest.return_value = sample_digest
        mock_builder.build_normalized_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = "# Test Blog Post\n\nContent here."
        mock_builder.save_markdown.return_value = Path("drafts/2025-01-15.md")
        
        # Mock the io object and its methods
        mock_io = Mock()
        mock_io.save_digest.return_value = Path("data/2025-01-15/digest.normalized.json")
        mock_builder.io = mock_io
        
        # Mock additional methods called by the CLI
        mock_builder.create_final_digest.return_value = {
            "ai_generated_content": {
                "title": "PCL-Labs — Jan 15, 2025",
                "description": "Today's development work focused on new features.",
                "tags": ["feat"]
            }
        }
        mock_builder.assemble_publish_package.return_value = {
            "content": {"title": "PCL-Labs — Jan 15, 2025"}
        }
        
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
        assert "Saved normalized digest: data/2025-01-15/digest.normalized.json" in result.output
        assert "Created FINAL digest with AI enhancements" in result.output
        
        # Verify the builder was called correctly
        mock_builder.build_latest_digest.assert_called_once()
        mock_builder.build_normalized_digest.assert_called_once_with("2025-01-15")
        mock_builder.io.save_digest.assert_called_once()
        mock_builder.create_final_digest.assert_called_once_with("2025-01-15")
        mock_builder.assemble_publish_package.assert_called_once_with("2025-01-15")
    
    def test_blog_generate_invalid_date(self, runner):
        """Test blog generate command with invalid date format."""
        result = runner.invoke(devlog, ['blog', 'generate', '--date', 'invalid-date'])
        
        assert result.exit_code == 1
        assert "Invalid date format: invalid-date. Use YYYY-MM-DD" in result.output
    

    

    

    

    

    

    

    
    @patch('services.blog.BlogDigestBuilder')
    def test_blog_preview(self, mock_builder_class, runner, sample_digest):
        """Test blog preview command."""
        # Mock the blog builder
        mock_builder = Mock()
        mock_builder.build_normalized_digest.return_value = sample_digest
        mock_builder.generate_markdown.return_value = """---
title: PCL-Labs — Jan 15, 2025
date: 2025-01-15
---

# PCL-Labs — Jan 15, 2025

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
        assert "Title: PCL-Labs — Jan 15, 2025" in result.output
        assert "Date: 2025-01-15" in result.output
        assert "Tags: feat" in result.output
        assert "Preview:" in result.output
        assert "  # PCL-Labs — Jan 15, 2025" in result.output
        assert "  Today's development work focused on new features." in result.output
    

