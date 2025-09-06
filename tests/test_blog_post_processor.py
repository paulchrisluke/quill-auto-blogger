"""
Tests for BlogPostProcessor domain validation and XSS prevention.
"""

import pytest
import os
from unittest.mock import patch
from services.blog_post_processor import BlogPostProcessor


class TestBlogPostProcessorDomainValidation:
    """Test domain validation and XSS prevention in BlogPostProcessor."""
    
    def test_validate_and_escape_domains_valid_domains(self):
        """Test validation with valid domain formats."""
        processor = BlogPostProcessor()
        
        # Test basic domains
        result = processor._validate_and_escape_domains("example.com,www.example.com")
        assert result == "example.com,www.example.com"
        
        # Test domains with ports
        result = processor._validate_and_escape_domains("example.com:8080,test.org:443")
        assert result == "example.com%3A8080,test.org%3A443"
        
        # Test domains with hyphens
        result = processor._validate_and_escape_domains("my-site.com,sub-domain.example.org")
        assert result == "my-site.com,sub-domain.example.org"
        
        # Test single domain
        result = processor._validate_and_escape_domains("paulchrisluke.com")
        assert result == "paulchrisluke.com"
    
    def test_validate_and_escape_domains_invalid_domains(self):
        """Test validation rejects invalid domain formats."""
        processor = BlogPostProcessor()
        
        # Test domains with invalid characters
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,evil<script>alert('xss')</script>.com")
        
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,test.com&malicious=1")
        
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,test.com\"onload=\"alert('xss')")
        
        # Test domains starting with invalid characters
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,-invalid.com")
        
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,.invalid.com")
        
        # Test domains ending with invalid characters
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,invalid-.com")
        
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,invalid..com")
        
        # Test domains with only special characters
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,---")
        
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com,...")
        
        # Test empty domains
        with pytest.raises(ValueError, match="Empty domains string provided"):
            processor._validate_and_escape_domains("")
        
        with pytest.raises(ValueError, match="No valid domains found"):
            processor._validate_and_escape_domains(",,,")
    
    def test_validate_and_escape_domains_xss_attempts(self):
        """Test that XSS attempts are properly rejected."""
        processor = BlogPostProcessor()
        
        # Common XSS payloads in domain names
        xss_attempts = [
            "example.com<script>alert('xss')</script>",
            "example.com\"onload=\"alert('xss')",
            "example.com'><script>alert('xss')</script>",
            "example.com&parent=evil.com",
            "example.com;alert('xss')",
            "example.com|alert('xss')",
            "example.com%3Cscript%3Ealert('xss')%3C/script%3E",
        ]
        
        for xss_attempt in xss_attempts:
            with pytest.raises(ValueError, match="Invalid domain format"):
                processor._validate_and_escape_domains(f"example.com,{xss_attempt}")
    
    def test_validate_and_escape_domains_whitespace_handling(self):
        """Test that whitespace is properly handled."""
        processor = BlogPostProcessor()
        
        # Test domains with various whitespace
        result = processor._validate_and_escape_domains(" example.com , www.example.com ")
        assert result == "example.com,www.example.com"
        
        # Test domains with tabs and newlines
        result = processor._validate_and_escape_domains("\texample.com\t,\nwww.example.com\n")
        assert result == "example.com,www.example.com"
    
    def test_validate_and_escape_domains_port_validation(self):
        """Test port number validation."""
        processor = BlogPostProcessor()
        
        # Valid ports
        result = processor._validate_and_escape_domains("example.com:80,test.com:443,api.com:8080")
        assert result == "example.com%3A80,test.com%3A443,api.com%3A8080"
        
        # Invalid ports (too high)
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com:99999")
        
        # Invalid ports (non-numeric)
        with pytest.raises(ValueError, match="Invalid domain format"):
            processor._validate_and_escape_domains("example.com:abc")
    
    @patch.dict(os.environ, {'TWITCH_EMBED_DOMAINS': 'example.com,www.example.com'})
    def test_get_twitch_embed_domains_from_env(self):
        """Test getting domains from environment variable."""
        processor = BlogPostProcessor()
        assert processor.twitch_embed_domains == 'example.com,www.example.com'
    
    @patch.dict(os.environ, {}, clear=True)
    def test_get_twitch_embed_domains_fallback(self):
        """Test fallback domains when environment variable is not set."""
        processor = BlogPostProcessor()
        assert processor.twitch_embed_domains == "paulchrisluke.com,www.paulchrisluke.com"
    
    def test_domain_validation_integration(self):
        """Test that domain validation is properly integrated into iframe generation."""
        processor = BlogPostProcessor()
        
        # Mock the domains to test validation integration
        processor.twitch_embed_domains = "example.com,www.example.com"
        
        # This should not raise an exception
        safe_domains = processor._validate_and_escape_domains(processor.twitch_embed_domains)
        assert safe_domains == "example.com,www.example.com"
        
        # Test with malicious domains
        processor.twitch_embed_domains = "example.com,<script>alert('xss')</script>"
        
        with pytest.raises(ValueError):
            processor._validate_and_escape_domains(processor.twitch_embed_domains)
