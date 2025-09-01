#!/usr/bin/env python3
"""
Tests for HTML→PNG renderer (M3).
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to Python path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.renderer_html import (
    HtmlSlideRenderer, VideoComposer, render_for_packet,
    truncate_text, sanitize_story_id, clamp_text_length, validate_text_quality,
    validate_packet_content, get_renderer_config
)


class TestHtmlSlideRenderer:
    """Test HTML slide rendering functionality."""
    
    def test_truncate_text(self):
        """Test text truncation functionality."""
        # Short text should not be truncated
        assert truncate_text("Hello world", 20) == "Hello world"
        
        # Long text should be truncated with ellipsis
        long_text = "This is a very long text that should be truncated"
        truncated = truncate_text(long_text, 20)
        assert len(truncate_text(long_text, 20)) == 20
        assert truncated.endswith("...")
        assert truncated == "This is a very lo..."
        
        # Empty text should return empty string
        assert truncate_text("", 20) == ""
        assert truncate_text(None, 20) == ""
    
    def test_clamp_text_length(self):
        """Test text length clamping functionality."""
        # Normal text should be unchanged
        assert clamp_text_length("Hello world", 20, 5) == "Hello world"
        
        # Long text should be truncated
        long_text = "This is a very long text that should be clamped"
        clamped = clamp_text_length(long_text, 20, 5)
        assert len(clamped) <= 20
        assert clamped.endswith("...")
        
        # Short text should be padded
        short_text = "Hi"
        clamped = clamp_text_length(short_text, 20, 10)
        assert len(clamped) >= 10
        assert "Hi" in clamped
        
        # Empty text should get default
        assert clamp_text_length("", 20, 10) == "No content"
    
    def test_validate_text_quality(self):
        """Test text quality validation."""
        # Good text should pass
        assert validate_text_quality("This is good text", 5) == True
        assert validate_text_quality("Multiple words here", 5) == True
        
        # Bad text should fail
        assert validate_text_quality("", 5) == False
        assert validate_text_quality("Hi", 5) == False  # Too short
        assert validate_text_quality("A", 5) == False   # Single character
        assert validate_text_quality("   ", 5) == False # Only whitespace
    
    def test_validate_packet_content(self):
        """Test packet content validation and fallbacks."""
        # Valid packet should pass through unchanged
        valid_packet = {
            "title_human": "Valid Title with Good Length",
            "why": "This is a valid why field with sufficient length to pass validation",
            "highlights": ["Valid highlight 1", "Valid highlight 2"]
        }
        
        validated = validate_packet_content(valid_packet)
        assert validated["title_human"] == valid_packet["title_human"]
        assert validated["why"] == valid_packet["why"]
        assert len(validated["highlights"]) == 2
        
        # Invalid packet should get fallbacks
        invalid_packet = {
            "title_human": "Short",
            "why": "Too short",
            "highlights": []
        }
        
        validated = validate_packet_content(invalid_packet)
        assert validated["title_human"] == "Untitled Story"
        assert "important work" in validated["why"]
        assert len(validated["highlights"]) == 1
        assert "improvements" in validated["highlights"][0]
    
    def test_sanitize_story_id(self):
        """Test story ID sanitization."""
        # Normal ID should be unchanged
        assert sanitize_story_id("story_20250101_pr123") == "story_20250101_pr123"
        
        # Special characters should be replaced
        assert sanitize_story_id("story/with/path") == "story_with_path"
        
        # Multiple special characters should be handled
        assert sanitize_story_id("story@#$%^&*()") == "story"
        
        # Empty ID should return "unknown"
        assert sanitize_story_id("") == "unknown"
        assert sanitize_story_id(None) == "unknown"
    
    @patch('tools.renderer_html.render_html_to_png')
    def test_render_intro(self, mock_render):
        """Test intro slide rendering."""
        renderer = HtmlSlideRenderer()
        
        packet = {
            "title_human": "Test Title",
            "repo": "test/repo",
            "pr_number": "123",
            "date": "2025-01-01"
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "intro.png"
            result = renderer.render_intro(packet, out_path)
            
            assert result == out_path
            mock_render.assert_called_once()
            
            # Check that HTML was generated with correct data
            call_args = mock_render.call_args[0]
            html_content = call_args[0]
            assert "Test Title" in html_content
            assert "test/repo • PR #123 • 2025-01-01" in html_content
    
    @patch('tools.renderer_html.render_html_to_png')
    def test_render_why(self, mock_render):
        """Test why slide rendering."""
        renderer = HtmlSlideRenderer()
        
        packet = {"why": "This is why it matters"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "why.png"
            result = renderer.render_why(packet, out_path)
            
            assert result == out_path
            mock_render.assert_called_once()
            
            # Check that HTML was generated with correct data
            call_args = mock_render.call_args[0]
            html_content = call_args[0]
            assert "Why it matters" in html_content
            assert "This is why it matters" in html_content
    
    @patch('tools.renderer_html.render_html_to_png')
    def test_render_highlights(self, mock_render):
        """Test highlights slide rendering."""
        renderer = HtmlSlideRenderer()
        
        packet = {
            "highlights": [
                "First highlight",
                "Second highlight", 
                "Third highlight",
                "Fourth highlight"
            ]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            story_id = "test_story"
            
            results = renderer.render_highlights(packet, out_dir, story_id)
            
            # Should create 2 slides (3 highlights per slide, max 3 slides)
            assert len(results) == 2
            assert mock_render.call_count == 2
            
            # Check file names
            assert results[0].name == "test_story_hl_01.png"
            assert results[1].name == "test_story_hl_02.png"
    
    @patch('tools.renderer_html.render_html_to_png')
    def test_render_outro(self, mock_render):
        """Test outro slide rendering."""
        renderer = HtmlSlideRenderer()
        
        packet = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "outro.png"
            result = renderer.render_outro(packet, out_path)
            
            assert result == out_path
            mock_render.assert_called_once()
            
            # Check that HTML was generated with correct content
            call_args = mock_render.call_args[0]
            html_content = call_args[0]
            assert "Full write-up on the blog" in html_content
            assert "Recorded with OBS" in html_content


class TestVideoComposer:
    """Test video composition functionality."""
    
    @patch('subprocess.run')
    def test_stitch(self, mock_run):
        """Test video stitching with FFmpeg."""
        composer = VideoComposer()
        
        # Create mock PNG files
        with tempfile.TemporaryDirectory() as temp_dir:
            slide1 = Path(temp_dir) / "slide1.png"
            slide2 = Path(temp_dir) / "slide2.png"
            slide1.touch()
            slide2.touch()
            
            out_path = Path(temp_dir) / "output.mp4"
            
            composer.stitch([slide1, slide2], out_path)
            
            # Verify FFmpeg was called
            mock_run.assert_called_once()
            
            # Check command structure
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "ffmpeg"
            assert "-filter_complex" in cmd
            assert "concat" in cmd[cmd.index("-filter_complex") + 1]
    
    def test_stitch_no_slides(self):
        """Test stitching with no slides should raise error."""
        composer = VideoComposer()
        
        with pytest.raises(ValueError, match="No slides provided"):
            composer.stitch([], Path("output.mp4"))


class TestRenderForPacket:
    """Test complete packet rendering."""
    
    @patch('tools.renderer_html.HtmlSlideRenderer')
    @patch('tools.renderer_html.VideoComposer')
    def test_render_for_packet(self, mock_composer_class, mock_renderer_class):
        """Test complete packet rendering workflow."""
        # Setup mocks
        mock_renderer = MagicMock()
        mock_composer = MagicMock()
        mock_renderer_class.return_value = mock_renderer
        mock_composer_class.return_value = mock_composer
        
        # Mock slide rendering
        mock_renderer.render_intro.return_value = Path("intro.png")
        mock_renderer.render_why.return_value = Path("why.png")
        mock_renderer.render_highlights.return_value = [Path("hl1.png"), Path("hl2.png")]
        mock_renderer.render_outro.return_value = Path("outro.png")
        
        packet = {
            "id": "test_story_123",
            "title_human": "Test Title",
            "why": "Test why",
            "highlights": ["Highlight 1", "Highlight 2", "Highlight 3", "Highlight 4"]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            result = render_for_packet(packet, out_dir)
            
            # Verify renderer was called for each slide type
            mock_renderer.render_intro.assert_called_once()
            mock_renderer.render_why.assert_called_once()
            mock_renderer.render_highlights.assert_called_once()
            mock_renderer.render_outro.assert_called_once()
            
            # Verify composer was called
            mock_composer.stitch.assert_called_once()
            
            # Check that stitch was called with all slides
            stitch_args = mock_composer.stitch.call_args[0]
            slide_paths = stitch_args[0]
            assert len(slide_paths) == 5  # intro + why + 2 highlights + outro
            
            # Check output path
            assert result.endswith("test_story_123.mp4")
    
    @patch('tools.renderer_html.HtmlSlideRenderer')
    @patch('tools.renderer_html.VideoComposer')
    def test_render_for_packet_idempotency(self, mock_composer_class, mock_renderer_class):
        """Test that rendering is idempotent (skips if video exists)."""
        # Setup mocks
        mock_renderer = MagicMock()
        mock_composer = MagicMock()
        mock_renderer_class.return_value = mock_renderer
        mock_composer_class.return_value = mock_composer
        
        packet = {
            "id": "test_story_123",
            "title_human": "Test Title",
            "why": "Test why",
            "highlights": ["Highlight 1", "Highlight 2"]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            
            # Create a fake video file to simulate existing render
            fake_video = out_dir / "test_story_123.mp4"
            fake_video.touch()
            
            result = render_for_packet(packet, out_dir)
            
            # Should not call renderer or composer since video exists
            mock_renderer.render_intro.assert_not_called()
            mock_renderer.render_why.assert_not_called()
            mock_renderer.render_highlights.assert_not_called()
            mock_renderer.render_outro.assert_not_called()
            mock_composer.stitch.assert_not_called()
            
            # Should return the existing path
            assert result == str(fake_video)
    
    def test_theme_support(self):
        """Test theme support in renderer configuration."""
        import os
        
        # Test default theme
        os.environ.pop("RENDERER_THEME", None)  # Clear any existing env var
        config = get_renderer_config()
        assert config["theme"] == "light"
        
        # Test dark theme
        os.environ["RENDERER_THEME"] = "dark"
        config = get_renderer_config()
        assert config["theme"] == "dark"
        
        # Clean up
        os.environ.pop("RENDERER_THEME", None)


class TestRendererIntegration:
    """Integration tests for the HTML renderer."""
    
    def test_end_to_end_rendering(self, tmp_path):
        """Test complete end-to-end rendering workflow."""
        # Create test packet
        test_packet = {
            "id": "integration_test_story",
            "title_human": "Integration Test: Complete Workflow",
            "repo": "test/repo",
            "pr_number": "999",
            "date": "2025-01-15",
            "why": "This is a comprehensive integration test that validates the complete HTML→PNG rendering workflow with proper content validation and fallbacks.",
            "highlights": [
                "End-to-end rendering from packet to video",
                "Content validation and fallback mechanisms",
                "Theme support and brand token application",
                "File organization and naming conventions",
                "Idempotent operation and force override"
            ]
        }
        
        # Render the packet
        result = render_for_packet(test_packet, tmp_path)
        
        # Verify output files exist
        expected_files = [
            "integration_test_story_01_intro.png",
            "integration_test_story_02_why.png",
            "integration_test_story_hl_01.png",
            "integration_test_story_hl_02.png",
            "integration_test_story_99_outro.png",
            "integration_test_story.mp4"
        ]
        
        for filename in expected_files:
            file_path = tmp_path / filename
            assert file_path.exists(), f"Expected file {filename} not found"
            assert file_path.stat().st_size > 0, f"File {filename} is empty"
        
        # Verify video file properties
        video_path = tmp_path / "integration_test_story.mp4"
        assert video_path.stat().st_size > 100000, "Video file too small"
        
        # Verify result path
        assert result == str(video_path)
    
    def test_theme_rendering_difference(self, tmp_path):
        """Test that light and dark themes produce different outputs."""
        import os
        
        test_packet = {
            "id": "theme_test_story",
            "title_human": "Theme Test",
            "why": "Testing theme differences",
            "highlights": ["Theme test"]
        }
        
        # Render with light theme
        os.environ["RENDERER_THEME"] = "light"
        light_result = render_for_packet(test_packet, tmp_path / "light")
        
        # Render with dark theme
        os.environ["RENDERER_THEME"] = "dark"
        dark_result = render_for_packet(test_packet, tmp_path / "dark")
        
        # Compare file sizes (should be different due to theme)
        light_intro = tmp_path / "light" / "theme_test_story_01_intro.png"
        dark_intro = tmp_path / "dark" / "theme_test_story_01_intro.png"
        
        assert light_intro.exists() and dark_intro.exists()
        assert light_intro.stat().st_size != dark_intro.stat().st_size, "Theme files should have different sizes"
        
        # Clean up
        os.environ.pop("RENDERER_THEME", None)
    
    def test_content_validation_fallbacks(self, tmp_path):
        """Test content validation and fallback mechanisms."""
        # Test packet with minimal content
        minimal_packet = {
            "id": "minimal_test",
            "title_human": "Short",
            "why": "Too short",
            "highlights": []
        }
        
        # Should still render with fallbacks
        result = render_for_packet(minimal_packet, tmp_path)
        
        # Verify files were created despite minimal content
        expected_files = [
            "minimal_test_01_intro.png",
            "minimal_test_02_why.png",
            "minimal_test_hl_01.png",
            "minimal_test_99_outro.png",
            "minimal_test.mp4"
        ]
        
        for filename in expected_files:
            file_path = tmp_path / filename
            assert file_path.exists(), f"Fallback file {filename} not found"
    
    def test_idempotent_operation(self, tmp_path):
        """Test that rendering is idempotent."""
        test_packet = {
            "id": "idempotent_test",
            "title_human": "Idempotent Test",
            "why": "Testing idempotent operation",
            "highlights": ["Idempotent test"]
        }
        
        # First render
        result1 = render_for_packet(test_packet, tmp_path)
        
        # Second render (should be skipped)
        result2 = render_for_packet(test_packet, tmp_path)
        
        # Results should be identical
        assert result1 == result2
        
        # File timestamps should be the same (no re-rendering)
        video_path = tmp_path / "idempotent_test.mp4"
        timestamp1 = video_path.stat().st_mtime
        
        # Small delay to ensure timestamp difference would be visible
        import time
        time.sleep(0.1)
        
        # Force re-render
        import os
        os.environ["RENDERER_FORCE"] = "true"
        render_for_packet(test_packet, tmp_path)
        os.environ.pop("RENDERER_FORCE", None)
        
        timestamp2 = video_path.stat().st_mtime
        assert timestamp2 > timestamp1, "Force render should update timestamp"


if __name__ == "__main__":
    pytest.main([__file__])
