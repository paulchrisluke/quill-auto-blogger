"""
Tests for M5 AI inserts service.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from services.ai_inserts import AITranscriptionService, AIClientError


class TestAITranscriptionService:
    """Test AI inserts service functionality."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        temp_dir = tempfile.mkdtemp()
        cache_dir = Path(temp_dir) / "blogs" / ".cache" / "m5"
        cache_dir.mkdir(parents=True)
        yield cache_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def ai_service(self, temp_cache_dir, monkeypatch):
        """Create AI service with mocked environment."""
        monkeypatch.setenv("AI_POLISH_ENABLED", "true")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test_account")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test_token")
        
        with patch('services.ai_inserts.CloudflareAIClient'):
            service = AITranscriptionService()
            service.cache_dir = temp_cache_dir
            return service
    
    def test_init_with_ai_disabled(self, monkeypatch):
        """Test initialization when AI is disabled."""
        monkeypatch.setenv("AI_POLISH_ENABLED", "false")
        
        service = AITranscriptionService()
        assert not service.ai_enabled
        assert service.ai_client is None
    
    def test_init_with_ai_enabled(self, monkeypatch):
        """Test initialization when AI is enabled."""
        monkeypatch.setenv("AI_POLISH_ENABLED", "true")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test_account")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test_token")
        
        with patch('services.ai_inserts.CloudflareAIClient') as mock_client:
            mock_client.return_value.model = "test-model"
            service = AITranscriptionService()
            
            assert service.ai_enabled
            assert service.ai_client is not None
    
    def test_init_with_ai_client_error(self, monkeypatch):
        """Test initialization when AI client fails."""
        monkeypatch.setenv("AI_POLISH_ENABLED", "true")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test_account")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test_token")
        
        with patch('services.ai_inserts.CloudflareAIClient', side_effect=AIClientError("test error")):
            service = AITranscriptionService()
            
            assert not service.ai_enabled
            assert service.ai_client is None
    
    def test_make_seo_description_cache_hit(self, ai_service, temp_cache_dir):
        """Test SEO description generation with cache hit."""
        date = "2025-01-15"
        inputs = {
            "title": "Test Title",
            "tags_csv": "feat,fix",
            "lead": "Test lead",
            "story_titles_csv": "Story 1,Story 2"
        }
        
        # Create cached result
        cache_key = ai_service._compute_cache_key("seo_description", inputs)
        date_cache_dir = temp_cache_dir / date
        date_cache_dir.mkdir(exist_ok=True)
        
        cached_result = "This is a cached SEO description."
        with open(date_cache_dir / f"{cache_key}.txt", 'w') as f:
            f.write(cached_result)
        
        # Should return cached result
        result = ai_service.make_seo_description(date, inputs)
        assert result == cached_result
    
    def test_make_seo_description_ai_success(self, ai_service):
        """Test SEO description generation with AI success."""
        date = "2025-01-15"
        inputs = {
            "title": "Test Title",
            "tags_csv": "feat,fix",
            "lead": "Test lead",
            "story_titles_csv": "Story 1,Story 2"
        }
        
        # Mock AI client
        mock_client = Mock()
        mock_client.model = "test-model"
        mock_client.generate.return_value = "AI generated SEO description."
        ai_service.ai_client = mock_client
        
        result = ai_service.make_seo_description(date, inputs)
        
        # Should return AI result
        assert "AI generated SEO description" in result
        mock_client.generate.assert_called_once()
        
        # Should be cached
        cache_key = ai_service._compute_cache_key("seo_description", inputs)
        cache_file = ai_service.cache_dir / date / f"{cache_key}.txt"
        assert cache_file.exists()
    
    def test_make_seo_description_ai_failure_fallback(self, ai_service):
        """Test SEO description generation with AI failure and fallback."""
        date = "2025-01-15"
        inputs = {
            "title": "Test Title",
            "tags_csv": "feat,fix",
            "lead": "Test lead",
            "story_titles_csv": "Story 1,Story 2"
        }
        
        # Mock AI client to fail
        mock_client = Mock()
        mock_client.generate.side_effect = AIClientError("API error")
        ai_service.ai_client = mock_client
        
        result = ai_service.make_seo_description(date, inputs)
        
        # Should return fallback (uses lead when available)
        assert "Test lead" in result
    
    def test_punch_up_title_success(self, ai_service):
        """Test title punch-up with AI success."""
        date = "2025-01-15"
        title = "PCL-Labs — Jan 15, 2025"
        
        # Mock AI client
        mock_client = Mock()
        mock_client.model = "test-model"
        mock_client.generate.return_value = "PCL-Labs — Jan 15, 2025 (Enhanced)"
        ai_service.ai_client = mock_client
        
        result = ai_service.punch_up_title(date, title)
        
        # Should return improved title
        assert result is not None
        assert "PCL-Labs" in result
        assert "Jan 15" in result
        assert len(result) <= 80
    
    def test_punch_up_title_guardrail_violation(self, ai_service):
        """Test title punch-up with guardrail violation (only length)."""
        date = "2025-01-15"
        title = "PCL-Labs — Jan 15, 2025"
    
        # Test with a title that's too long - should be handled by sanitization
        long_title = "This is a very long title that exceeds the maximum allowed length of eighty characters exactly"
        assert len(long_title) > 80
        
        with patch.object(ai_service, '_sanitize_text') as mock_sanitize:
            # Mock sanitization to return a reasonable length title
            mock_sanitize.return_value = "This is a very long title that exceeds the maximum allowed length"
            
            mock_client = Mock()
            mock_client.model = "test-model"
            mock_client.generate.return_value = long_title
            ai_service.ai_client = mock_client
        
            result = ai_service.punch_up_title(date, title)
        
            # Should return sanitized title
            assert result == "This is a very long title that exceeds the maximum allowed length"
    
    def test_make_story_micro_intro_success(self, ai_service):
        """Test story micro-intro generation with AI success."""
        date = "2025-01-15"
        story_inputs = {
            "title": "Fix login bug",
            "why": "Users couldn't access the system",
            "highlights_csv": "Fixed authentication,Improved UX"
        }
        
        # Mock AI client
        mock_client = Mock()
        mock_client.model = "test-model"
        mock_client.generate.return_value = "This fix resolves critical authentication issues."
        ai_service.ai_client = mock_client
        
        result = ai_service.make_story_micro_intro(date, story_inputs)
        
        # Should return AI result
        assert "authentication" in result.lower()
        assert len(result) <= 160
        assert result.endswith('.')
    
    def test_make_story_micro_intro_fallback(self, ai_service):
        """Test story micro-intro generation uses fallback when AI is disabled."""
        date = "2025-01-15"
        story_inputs = {
            "title": "Fix login bug",
            "why": "Users couldn't access the system",
            "highlights_csv": "Fixed authentication,Improved UX"
        }
        
        # Disable AI
        ai_service.ai_enabled = False
        
        # Should return fallback when AI is disabled
        result = ai_service.make_story_micro_intro(date, story_inputs)
        assert result is not None
        assert len(result) > 0
        # Should be a simple fallback description
        assert "login bug" in result.lower() or "authentication" in result.lower()
    
    def test_sanitize_text_basic(self, ai_service):
        """Test basic text sanitization."""
        raw_text = "  *This* is `test` text  "
        
        result = ai_service._sanitize_text(raw_text, max_length=100, ensure_period=True)
        
        assert result == "This is test text."
        assert len(result) <= 100
    
    def test_sanitize_text_length_truncation(self, ai_service):
        """Test text truncation at word boundaries."""
        long_text = "This is a very long text that exceeds the maximum length limit"
        
        result = ai_service._sanitize_text(long_text, max_length=20, ensure_period=True)
        
        # Should truncate to fit within 20 characters including period
        assert len(result) <= 20
        assert result.endswith('.')
        # Should be truncated to something like "This is a very long."
        assert len(result) < len(long_text)
    
    def test_sanitize_text_quotes_removal(self, ai_service):
        """Test removal of surrounding quotes."""
        quoted_text = '"This text has quotes"'
        
        result = ai_service._sanitize_text(quoted_text, max_length=100, ensure_period=False)
        
        assert result == "This text has quotes"
        assert not result.startswith('"')
        assert not result.endswith('"')
    
    
    def test_fallback_seo_description_with_lead(self, ai_service):
        """Test fallback SEO description generation with lead."""
        inputs = {
            "lead": "This is a test lead paragraph.",
            "title": "Test Title",
            "story_titles_csv": "Story 1,Story 2"
        }
        
        result = ai_service._fallback_seo_description(inputs)
        
        assert result == "This is a test lead paragraph."
    
    def test_fallback_seo_description_without_lead(self, ai_service):
        """Test fallback SEO description generation without lead."""
        inputs = {
            "title": "Test Title",
            "story_titles_csv": "Story 1,Story 2"
        }
        
        result = ai_service._fallback_seo_description(inputs)
        
        assert "Test Title" in result
        assert "Story 1" in result
        assert result.endswith('.')
    
    def test_fallback_seo_description_length_clamp(self, ai_service):
        """Test fallback SEO description length clamping."""
        long_lead = "A" * 250  # Over 220 chars
        inputs = {
            "lead": long_lead,
            "title": "Test Title",
            "story_titles_csv": "Story 1,Story 2"
        }
        
        result = ai_service._fallback_seo_description(inputs)
        
        assert len(result) <= 220
        assert result.endswith('...')
    
    def test_fallback_story_micro_intro(self, ai_service):
        """Test fallback story micro-intro generation."""
        story_inputs = {
            "title": "Fix login bug",
            "why": "Users couldn't access the system"
        }
        
        result = ai_service._fallback_story_micro_intro(story_inputs)
        
        assert "Fix login bug" in result
        assert "Users couldn't access the system" in result
        assert result.endswith('.')
        assert len(result) <= 160
    
    def test_cache_key_deterministic(self, ai_service):
        """Test that cache keys are deterministic for same inputs."""
        inputs = {"key1": "value1", "key2": "value2"}
        
        key1 = ai_service._compute_cache_key("test_op", inputs)
        key2 = ai_service._compute_cache_key("test_op", inputs)
        
        assert key1 == key2
    
    def test_cache_key_different_operations(self, ai_service):
        """Test that different operations get different cache keys."""
        inputs = {"key1": "value1", "key2": "value2"}
        
        key1 = ai_service._compute_cache_key("op1", inputs)
        key2 = ai_service._compute_cache_key("op2", inputs)
        
        assert key1 != key2
    
    def test_cache_key_different_models(self, ai_service):
        """Test that different models get different cache keys."""
        inputs = {"key1": "value1", "key2": "value2"}
        
        # Mock different models
        ai_service.ai_client = Mock()
        ai_service.ai_client.model = "model1"
        key1 = ai_service._compute_cache_key("test_op", inputs)
        
        ai_service.ai_client.model = "model2"
        key2 = ai_service._compute_cache_key("test_op", inputs)
        
        assert key1 != key2
