"""
Tests for the Publisher service.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from services.publisher import Publisher, sanitize_story_id


class TestPublisher:
    """Test cases for Publisher class."""
    
    def test_publish_target_normalization(self):
        """Test that PUBLISH_TARGET is normalized to lowercase."""
        with patch.dict(os.environ, {'PUBLISH_TARGET': 'LOCAL'}, clear=True):
            publisher = Publisher()
            assert publisher.publish_target == 'local'
    
    def test_publish_target_validation_valid(self):
        """Test that valid publish targets are accepted."""
        test_cases = [
            ('local', {}),
            ('LOCAL', {}),
            (' Local ', {}),
            ('r2', {
                'R2_ACCESS_KEY_ID': 'test-access-key-id',
                'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
                'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
                'R2_BUCKET': 'test-bucket'
            }),
            ('R2', {
                'R2_ACCESS_KEY_ID': 'test-access-key-id',
                'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
                'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
                'R2_BUCKET': 'test-bucket'
            }),
            (' R2 ', {
                'R2_ACCESS_KEY_ID': 'test-access-key-id',
                'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
                'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
                'R2_BUCKET': 'test-bucket'
            })
        ]
        
        for target, credentials in test_cases:
            env_vars = {'PUBLISH_TARGET': target}
            env_vars.update(credentials)
            with patch.dict(os.environ, env_vars, clear=True):
                publisher = Publisher()
                assert publisher.publish_target in ['local', 'r2']
    
    def test_publish_target_validation_invalid(self):
        """Test that invalid publish targets raise ValueError."""
        invalid_targets = ['s3', 'cloudflare', 'invalid', '']
        
        for target in invalid_targets:
            with patch.dict(os.environ, {'PUBLISH_TARGET': target}, clear=True):
                with pytest.raises(ValueError, match="Invalid PUBLISH_TARGET"):
                    Publisher()
    
    def test_r2_credentials_validation_missing_access_key_id(self):
        """Test that missing R2_ACCESS_KEY_ID raises ValueError when target is r2."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'R2_SECRET_ACCESS_KEY': 'test-secret-key',
            'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
            'R2_BUCKET': 'test-bucket'
        }, clear=True):
            with pytest.raises(ValueError, match="R2 credentials not found"):
                Publisher()
    
    def test_r2_credentials_validation_missing_secret_access_key(self):
        """Test that missing R2_SECRET_ACCESS_KEY raises ValueError when target is r2."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'R2_ACCESS_KEY_ID': 'test-access-key-id',
            'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
            'R2_BUCKET': 'test-bucket'
        }, clear=True):
            with pytest.raises(ValueError, match="R2 credentials not found"):
                Publisher()
    
    def test_r2_credentials_validation_missing_bucket(self):
        """Test that missing R2_BUCKET raises ValueError when target is r2."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'R2_ACCESS_KEY_ID': 'test-access-key-id',
            'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
            'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com'
        }, clear=True):
            with pytest.raises(ValueError, match="R2 credentials not found"):
                Publisher()
    
    def test_r2_credentials_validation_success(self):
        """Test that valid R2 credentials are accepted."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'R2_ACCESS_KEY_ID': 'test-access-key-id',
            'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
            'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
            'R2_BUCKET': 'test-bucket'
        }, clear=True):
            publisher = Publisher()
            assert publisher.publish_target == 'r2'
            assert publisher.r2_credentials is not None
            assert publisher.r2_credentials.access_key_id == 'test-access-key-id'
            assert publisher.r2_credentials.secret_access_key == 'test-secret-access-key'
            assert publisher.r2_credentials.endpoint == 'https://test-account-id.r2.cloudflarestorage.com'
            assert publisher.r2_credentials.bucket == 'test-bucket'
    
    def test_local_target_no_r2_credentials_required(self):
        """Test that R2 credentials are not required when target is local."""
        with patch.dict(os.environ, {'PUBLISH_TARGET': 'local'}, clear=True):
            publisher = Publisher()
            assert publisher.publish_target == 'local'
            # Should not raise any exceptions even if R2 credentials are missing
    
    def test_sanitize_story_id(self):
        """Test story_id sanitization."""
        # Test path traversal attempts
        assert sanitize_story_id("../../../etc/passwd") == "_________etc_passwd"
        assert sanitize_story_id("..\\..\\..\\windows\\system32") == "_________windows_system32"
        
        # Test special characters
        assert sanitize_story_id("story@#$%^&*()") == "story_________"
        assert sanitize_story_id("story with spaces") == "story_with_spaces"
        
        # Test empty and None
        assert sanitize_story_id("") == "unknown"
        assert sanitize_story_id(None) == "unknown"
        
        # Test normal cases
        assert sanitize_story_id("normal-story-id") == "normal-story-id"
        assert sanitize_story_id("story_123") == "story_123"
        
        # Test length limit
        long_id = "a" * 100
        assert len(sanitize_story_id(long_id)) == 50
    
    @patch('services.publisher.boto3.client')
    def test_r2_presigned_url_fallback(self, mock_boto3_client):
        """Test that presigned URLs are generated when R2_PUBLIC_BASE_URL is not set."""
        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client
        
        # Mock presigned URL generation
        mock_s3_client.generate_presigned_url.return_value = "https://presigned-url.example.com"
        mock_s3_client.head_object.return_value = {}
        
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'R2_ACCESS_KEY_ID': 'test-access-key-id',
            'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
            'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
            'R2_BUCKET': 'test-bucket'
            # Note: R2_PUBLIC_BASE_URL is intentionally not set
        }, clear=True):
            publisher = Publisher()
            
            # Mock file existence
            with patch('os.path.exists', return_value=True):
                result = publisher.publish_video('/fake/path.mp4', '2025-01-15', 'test-story')
                
                # Verify presigned URL was generated
                mock_s3_client.generate_presigned_url.assert_called_once()
                assert result == "https://presigned-url.example.com"
    
    @patch('services.publisher.boto3.client')
    def test_r2_presigned_url_failure(self, mock_boto3_client):
        """Test that RuntimeError is raised when presigned URL generation fails."""
        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client
        
        # Mock presigned URL generation failure
        mock_s3_client.generate_presigned_url.side_effect = Exception("Presigned URL generation failed")
        mock_s3_client.head_object.return_value = {}
        
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'R2_ACCESS_KEY_ID': 'test-access-key-id',
            'R2_SECRET_ACCESS_KEY': 'test-secret-access-key',
            'R2_S3_ENDPOINT': 'https://test-account-id.r2.cloudflarestorage.com',
            'R2_BUCKET': 'test-bucket'
            # Note: R2_PUBLIC_BASE_URL is intentionally not set
        }, clear=True):
            publisher = Publisher()
            
            # Mock file existence
            with patch('os.path.exists', return_value=True):
                with pytest.raises(RuntimeError, match="R2_PUBLIC_BASE_URL not configured"):
                    publisher.publish_video('/fake/path.mp4', '2025-01-15', 'test-story')
