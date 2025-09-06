"""
Tests for comprehensive blog generator markdown processing.
"""
import os
import pytest
import re
from unittest.mock import patch, MagicMock

# Disable AI client before importing the service
os.environ['AI_COMPREHENSIVE_ENABLED'] = 'false'
from services.comprehensive_blog_generator import ComprehensiveBlogGenerator


class TestMarkdownProcessing:
    """Test markdown processing to ensure code blocks, inline code, and URLs remain unchanged."""
    
    @patch('services.comprehensive_blog_generator.CloudflareAIClient')
    def test_bullet_fixing_preserves_code_blocks(self, mock_ai_client):
        """Test that bullet fixing doesn't alter content inside code blocks."""
        # Test with fenced code blocks
        content_with_fenced_code = """
Here are the features:

```python
def example():
    # This should not be changed: - bullet point
    return "value: - another"
```

And more content: - this should be fixed
"""
        
        # Test with indented code blocks
        content_with_indented_code = """
Here are the features:

    def example():
        # This should not be changed: - bullet point
        return "value: - another"

And more content: - this should be fixed
"""
        
        # Test the old problematic regex (should fail)
        result_fenced_old = re.sub(r': - ', ':\n\n- ', content_with_fenced_code)
        result_indented_old = re.sub(r': - ', ':\n\n- ', content_with_indented_code)
        
        # Test the new safe method
        generator = ComprehensiveBlogGenerator()
        result_fenced_new = generator._fix_bullet_points_safely(content_with_fenced_code)
        result_indented_new = generator._fix_bullet_points_safely(content_with_indented_code)
        
        # Old regex should alter code blocks (documenting the problem)
        assert ": - bullet point" not in result_fenced_old  # Gets changed by old regex
        assert "value: - another" not in result_fenced_old  # Gets changed by old regex
        
        # New regex should preserve code blocks
        assert ": - bullet point" in result_fenced_new  # Should remain unchanged
        assert "value: - another" in result_fenced_new  # Should remain unchanged
        assert ": - this should be fixed" not in result_fenced_new  # Should be changed
        
        assert ": - bullet point" in result_indented_new  # Should remain unchanged
        assert "value: - another" in result_indented_new  # Should remain unchanged
        assert ": - this should be fixed" not in result_indented_new  # Should be changed
    
    @patch('services.comprehensive_blog_generator.CloudflareAIClient')
    def test_bullet_fixing_preserves_inline_code(self, mock_ai_client):
        """Test that bullet fixing doesn't alter content inside inline code."""
        content_with_inline_code = """
The command is `echo "value: - test"` and the result: - should be fixed
Another example: `config: - setting` and more: - content
"""
        
        # Test old regex (should alter inline code)
        result_old = re.sub(r': - ', ':\n\n- ', content_with_inline_code)
        
        # Test new safe method
        generator = ComprehensiveBlogGenerator()
        result_new = generator._fix_bullet_points_safely(content_with_inline_code)
        
        # Old regex should alter inline code
        assert '`echo "value: - test"`' not in result_old  # Gets changed by old regex
        assert '`config: - setting`' not in result_old  # Gets changed by old regex
        
        # New regex should preserve inline code
        assert '`echo "value: - test"`' in result_new  # Should remain unchanged
        assert '`config: - setting`' in result_new  # Should remain unchanged
        assert ": - should be fixed" not in result_new  # Should be changed
        assert ": - content" not in result_new  # Should be changed
    
    @patch('services.comprehensive_blog_generator.CloudflareAIClient')
    def test_bullet_fixing_preserves_urls(self, mock_ai_client):
        """Test that bullet fixing doesn't alter URLs."""
        content_with_urls = """
Check out https://example.com: - path and http://test.com: - another
Also visit https://api.example.com: - endpoint for more info: - details
"""
        
        # Test old regex (should alter URLs)
        result_old = re.sub(r': - ', ':\n\n- ', content_with_urls)
        
        # Test new safe method
        generator = ComprehensiveBlogGenerator()
        result_new = generator._fix_bullet_points_safely(content_with_urls)
        
        # Old regex should alter URLs
        assert "https://example.com: - path" not in result_old  # Gets changed by old regex
        assert "http://test.com: - another" not in result_old  # Gets changed by old regex
        assert "https://api.example.com: - endpoint" not in result_old  # Gets changed by old regex
        
        # New regex should preserve URLs
        assert "https://example.com: - path" in result_new  # Should remain unchanged
        assert "http://test.com: - another" in result_new  # Should remain unchanged
        assert "https://api.example.com: - endpoint" in result_new  # Should remain unchanged
        assert ": - details" not in result_new  # Should be changed
    
    @patch('services.comprehensive_blog_generator.CloudflareAIClient')
    def test_bullet_fixing_preserves_markdown_links(self, mock_ai_client):
        """Test that bullet fixing doesn't alter markdown links."""
        content_with_links = """
Check out [this link](https://example.com: - path) and more: - content
Also see [another link](http://test.com: - another) and info: - details
"""
        
        # Test old regex (should alter markdown links)
        result_old = re.sub(r': - ', ':\n\n- ', content_with_links)
        
        # Test new safe method
        generator = ComprehensiveBlogGenerator()
        result_new = generator._fix_bullet_points_safely(content_with_links)
        
        # Old regex should alter markdown links
        assert '[this link](https://example.com: - path)' not in result_old  # Gets changed by old regex
        assert '[another link](http://test.com: - another)' not in result_old  # Gets changed by old regex
        
        # New regex should preserve markdown links
        assert '[this link](https://example.com: - path)' in result_new  # Should remain unchanged
        assert '[another link](http://test.com: - another)' in result_new  # Should remain unchanged
        assert ": - content" not in result_new  # Should be changed
        assert ": - details" not in result_new  # Should be changed
    
    @patch('services.comprehensive_blog_generator.CloudflareAIClient')
    def test_safe_bullet_fixing_with_new_method(self, mock_ai_client):
        """Test the improved bullet fixing using our new safe method."""
        content = """
Here are the features: - first item
Another list: - second item
Code example: `echo "value: - test"`
URL example: https://example.com: - path
Fenced code:
```python
def example():
    return "value: - another"
```
Indented code:
    def example():
        return "value: - another"
"""
        
        # Use our new safe method
        generator = ComprehensiveBlogGenerator()
        result = generator._fix_bullet_points_safely(content)
        
        # Should fix bullets at start of lines
        assert ": - first item" not in result
        assert ":\n\n- first item" in result
        assert ": - second item" not in result
        assert ":\n\n- second item" in result
        
        # Should preserve inline code
        assert '`echo "value: - test"`' in result
        
        # Should preserve URLs
        assert "https://example.com: - path" in result
        
        # Should preserve fenced code blocks
        assert 'return "value: - another"' in result
        
        # Should preserve indented code blocks
        assert '    return "value: - another"' in result
    
    def test_multiline_bullet_fixing(self):
        """Test bullet fixing with MULTILINE flag."""
        content = """Here are the features: - first item
Another list: - second item
Code example: `echo "value: - test"`
"""
        
        # Use MULTILINE flag with ^ anchor
        safe_pattern = r'^([^`\n]*?): - '
        result = re.sub(safe_pattern, r'\1:\n\n- ', content, flags=re.MULTILINE)
        
        # Should fix bullets at start of lines
        assert ": - first item" not in result
        assert ":\n\n- first item" in result
        assert ": - second item" not in result
        assert ":\n\n- second item" in result
        
        # Should preserve inline code
        assert '`echo "value: - test"`' in result
