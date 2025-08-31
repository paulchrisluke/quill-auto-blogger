"""
Tests for the Publisher service.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from services.publisher import Publisher


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
                'CLOUDFLARE_ACCOUNT_ID': 'test-account-id',
                'CLOUDFLARE_API_TOKEN': 'test-api-token',
                'R2_BUCKET': 'test-bucket'
            }),
            ('R2', {
                'CLOUDFLARE_ACCOUNT_ID': 'test-account-id',
                'CLOUDFLARE_API_TOKEN': 'test-api-token',
                'R2_BUCKET': 'test-bucket'
            }),
            (' R2 ', {
                'CLOUDFLARE_ACCOUNT_ID': 'test-account-id',
                'CLOUDFLARE_API_TOKEN': 'test-api-token',
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
    
    def test_r2_credentials_validation_missing_account_id(self):
        """Test that missing CLOUDFLARE_ACCOUNT_ID raises ValueError when target is r2."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'CLOUDFLARE_API_TOKEN': 'test-token',
            'R2_BUCKET': 'test-bucket'
        }, clear=True):
            with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
                Publisher()
    
    def test_r2_credentials_validation_missing_api_token(self):
        """Test that missing CLOUDFLARE_API_TOKEN raises ValueError when target is r2."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'CLOUDFLARE_ACCOUNT_ID': 'test-account-id',
            'R2_BUCKET': 'test-bucket'
        }, clear=True):
            with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
                Publisher()
    
    def test_r2_credentials_validation_missing_bucket(self):
        """Test that missing R2_BUCKET raises ValueError when target is r2."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'CLOUDFLARE_ACCOUNT_ID': 'test-account-id',
            'CLOUDFLARE_API_TOKEN': 'test-token'
        }, clear=True):
            with pytest.raises(ValueError, match="R2_BUCKET"):
                Publisher()
    
    def test_r2_credentials_validation_success(self):
        """Test that valid R2 credentials are accepted."""
        with patch.dict(os.environ, {
            'PUBLISH_TARGET': 'r2',
            'CLOUDFLARE_ACCOUNT_ID': 'test-account-id',
            'CLOUDFLARE_API_TOKEN': 'test-api-token',
            'R2_BUCKET': 'test-bucket'
        }, clear=True):
            publisher = Publisher()
            assert publisher.publish_target == 'r2'
            assert publisher.cloudflare_account_id == 'test-account-id'
            assert publisher.cloudflare_api_token == 'test-api-token'
            assert publisher.r2_bucket == 'test-bucket'
    
    def test_local_target_no_r2_credentials_required(self):
        """Test that R2 credentials are not required when target is local."""
        with patch.dict(os.environ, {'PUBLISH_TARGET': 'local'}, clear=True):
            publisher = Publisher()
            assert publisher.publish_target == 'local'
            # Should not raise any exceptions even if R2 credentials are missing
