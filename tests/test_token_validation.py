"""
Tests for token validation in AI client.
"""

import pytest
import os
from unittest.mock import patch, MagicMock

from services.ai_client import CloudflareAIClient, TokenLimitExceededError, AIClientError


class TestTokenValidation:
    """Test token validation functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'CLOUDFLARE_ACCOUNT_ID': 'test_account',
            'CLOUDFLARE_API_TOKEN': 'test_token',
            'CLOUDFLARE_AI_MODEL': 'openai/llama-3.1-8b-instruct',
            'AI_VALIDATE_TOKENS': 'true',
            'AI_MAX_INPUT_TOKENS': '1000',  # Small limit for testing
        })
        self.env_patcher.start()
    
    def teardown_method(self):
        """Clean up test environment."""
        self.env_patcher.stop()
    
    def test_token_validation_enabled(self):
        """Test that token validation is enabled by default."""
        client = CloudflareAIClient()
        assert client.validate_tokens is True
        assert client.max_input_tokens == 1000
    
    def test_token_validation_disabled(self):
        """Test that token validation can be disabled."""
        with patch.dict(os.environ, {'AI_VALIDATE_TOKENS': 'false'}):
            client = CloudflareAIClient()
            assert client.validate_tokens is False
    
    def test_token_counting_with_tiktoken(self):
        """Test token counting with tiktoken."""
        client = CloudflareAIClient()
        
        # Test with a simple text
        text = "Hello, world! This is a test."
        token_count = client._count_tokens(text)
        
        # Should return a positive integer
        assert isinstance(token_count, int)
        assert token_count > 0
    
    def test_token_counting_fallback(self):
        """Test token counting fallback when tiktoken fails."""
        client = CloudflareAIClient()
        client.tokenizer = None  # Simulate tiktoken failure
        
        text = "Hello, world! This is a test."
        token_count = client._count_tokens(text)
        
        # Should fall back to character-based estimation
        assert isinstance(token_count, int)
        assert token_count > 0
        assert token_count == len(text) // 4  # Character-based estimation
    
    def test_token_validation_success(self):
        """Test successful token validation."""
        client = CloudflareAIClient()
        
        # Small prompt that should pass validation
        system = "You are a helpful assistant."
        prompt = "Hello, how are you?"
        
        # Should not raise an exception
        client._validate_token_limits(system, prompt, 100)
    
    def test_token_validation_input_limit_exceeded(self):
        """Test token validation when input limit is exceeded."""
        client = CloudflareAIClient()
        
        # Large prompt that should exceed the 1000 token limit
        large_text = "This is a test. " * 1000  # Very large text
        system = large_text
        prompt = large_text
        
        with pytest.raises(TokenLimitExceededError) as exc_info:
            client._validate_token_limits(system, prompt, 100)
        
        assert "Input tokens" in str(exc_info.value)
        assert "exceed model limit" in str(exc_info.value)
    
    def test_token_validation_context_window_exceeded(self):
        """Test token validation when context window is exceeded."""
        client = CloudflareAIClient()
        
        # Set a very small context window for testing
        client.model_config = {"context_window": 100, "max_output_tokens": 50}
        
        system = "You are a helpful assistant."
        prompt = "Hello, how are you?"
        
        with pytest.raises(TokenLimitExceededError) as exc_info:
            client._validate_token_limits(system, prompt, 100)  # 100 output tokens
        
        assert "Total tokens" in str(exc_info.value)
        assert "exceed context window" in str(exc_info.value)
    
    def test_token_validation_output_limit_exceeded(self):
        """Test token validation when output limit is exceeded."""
        client = CloudflareAIClient()
        
        # Set a very small max output tokens for testing
        client.model_config = {"context_window": 100000, "max_output_tokens": 50}
        
        system = "You are a helpful assistant."
        prompt = "Hello, how are you?"
        
        with pytest.raises(TokenLimitExceededError) as exc_info:
            client._validate_token_limits(system, prompt, 100)  # 100 output tokens
        
        assert "Output tokens" in str(exc_info.value)
        assert "exceed model limit" in str(exc_info.value)
    
    @patch('requests.post')
    def test_generate_with_validation(self, mock_post):
        """Test that generate method validates tokens before making request."""
        client = CloudflareAIClient()
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "result": {
                "response": "Test response",
                "usage": {"input_tokens": 0, "output_tokens": 0}
            }
        }
        mock_post.return_value = mock_response
        
        # Small prompt that should pass validation
        system = "You are a helpful assistant."
        prompt = "Hello, how are you?"
        
        result = client.generate(prompt, system, max_tokens=100)
        
        assert result == "Test response"
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_generate_with_validation_failure(self, mock_post):
        """Test that generate method fails fast on token validation."""
        client = CloudflareAIClient()
        
        # Large prompt that should fail validation
        large_text = "This is a test. " * 1000  # Very large text
        system = large_text
        prompt = large_text
        
        with pytest.raises(TokenLimitExceededError):
            client.generate(prompt, system, max_tokens=100)
        
        # Should not make the HTTP request
        mock_post.assert_not_called()
