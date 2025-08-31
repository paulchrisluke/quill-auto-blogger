"""
Tests for authentication service.
"""

import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from pathlib import Path

from services.auth import AuthService
from models import TwitchToken, GitHubToken
from pydantic import SecretStr


class TestAuthService:
    """Test cases for AuthService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.auth_service = AuthService()
        self.auth_service.twitch_client_id = "test_client_id"
        self.auth_service.twitch_client_secret = "test_client_secret"
        self.auth_service.github_token = "test_github_token"
    
    def test_load_twitch_token_nonexistent(self):
        """Test loading Twitch token when file doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            token = self.auth_service._load_twitch_token()
            assert token is None
    
    def test_load_twitch_token_valid(self):
        """Test loading valid Twitch token from file."""
        test_token = TwitchToken(
            access_token=SecretStr("test_token"),
            expires_in=3600,
            token_type="bearer",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', create=True) as mock_open:
                # Create the JSON data that would be saved by the new method
                data = test_token.model_dump()
                data['access_token'] = test_token.access_token.get_secret_value()
                import json
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(data, default=str)
                
                token = self.auth_service._load_twitch_token()
                assert token is not None
                assert token.access_token.get_secret_value() == "test_token"
    
    def test_is_token_expired_future(self):
        """Test token expiration check for future token."""
        future_token = TwitchToken(
            access_token=SecretStr("test_token"),
            expires_in=3600,
            token_type="bearer",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        assert not self.auth_service._is_token_expired(future_token)
    
    def test_is_token_expired_past(self):
        """Test token expiration check for expired token."""
        past_token = TwitchToken(
            access_token=SecretStr("test_token"),
            expires_in=3600,
            token_type="bearer",
            expires_at=datetime.now() - timedelta(hours=1)
        )
        
        assert self.auth_service._is_token_expired(past_token)
    
    @patch('httpx.Client')
    @patch('httpx.Timeout')
    def test_refresh_twitch_token_success(self, mock_timeout, mock_client):
        """Test successful Twitch token refresh."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
            "token_type": "bearer"
        }
        mock_response.raise_for_status.return_value = None
        
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with patch('builtins.open', create=True) as mock_open:
            token = self.auth_service._refresh_twitch_token()
            
            assert token is not None
            assert token.access_token.get_secret_value() == "new_token"
            assert token.expires_in == 3600
    
    @patch('httpx.Client')
    @patch('httpx.Timeout')
    def test_refresh_twitch_token_failure(self, mock_timeout, mock_client):
        """Test Twitch token refresh failure."""
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = Exception("API Error")
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        token = self.auth_service._refresh_twitch_token()
        assert token is None
    
    @patch('httpx.Client')
    @patch('httpx.Timeout')
    def test_validate_twitch_auth_success(self, mock_timeout, mock_client):
        """Test successful Twitch authentication validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with patch.object(self.auth_service, 'get_twitch_token', return_value="test_token"):
            result = self.auth_service.validate_twitch_auth()
            assert result is True
    
    @patch('httpx.Client')
    @patch('httpx.Timeout')
    def test_validate_twitch_auth_failure(self, mock_timeout, mock_client):
        """Test failed Twitch authentication validation."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with patch.object(self.auth_service, 'get_twitch_token', return_value="test_token"):
            result = self.auth_service.validate_twitch_auth()
            assert result is False
    
    @patch('httpx.Client')
    @patch('httpx.Timeout')
    def test_validate_github_auth_success(self, mock_timeout, mock_client):
        """Test successful GitHub authentication validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with patch.object(self.auth_service, 'get_github_token', return_value="test_token") as mock_get_token:
            result = self.auth_service.validate_github_auth()
            assert result is True
            
            # Verify get_github_token was called
            mock_get_token.assert_called_once()
            
            # Verify the HTTP request was made with correct headers
            mock_client_instance.get.assert_called_once()
            call_args = mock_client_instance.get.call_args
            assert call_args[0][0] == "https://api.github.com/user"  # URL
            assert call_args[1]['headers']['Authorization'] == "token test_token"
            assert call_args[1]['headers']['Accept'] == "application/vnd.github.v3+json"
    
    @patch('httpx.Client')
    @patch('httpx.Timeout')
    def test_validate_github_auth_failure(self, mock_timeout, mock_client):
        """Test failed GitHub authentication validation."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        with patch.object(self.auth_service, 'get_github_token', return_value="test_token"):
            result = self.auth_service.validate_github_auth()
            assert result is False
    
    def test_validate_github_auth_no_token(self):
        """Test GitHub authentication validation with no token."""
        with patch.object(self.auth_service, 'get_github_token', return_value=None):
            result = self.auth_service.validate_github_auth()
            assert result is False
    

    
    def test_get_twitch_headers(self):
        """Test Twitch headers generation."""
        with patch.object(self.auth_service, 'get_twitch_token', return_value="test_token"):
            headers = self.auth_service.get_twitch_headers()
            assert headers["Client-ID"] == "test_client_id"
            assert headers["Authorization"] == "Bearer test_token"
    
    def test_get_github_token(self):
        """Test GitHub token retrieval."""
        test_token = GitHubToken(
            token=SecretStr("test_github_token"),
            expires_at=datetime.now() + timedelta(days=30)
        )
        
        with patch.object(self.auth_service, '_load_github_token', return_value=test_token):
            token = self.auth_service.get_github_token()
            assert token == "test_github_token"
    
    def test_get_github_token_expired(self):
        """Test GitHub token retrieval when expired."""
        expired_token = GitHubToken(
            token=SecretStr("test_github_token"),
            expires_at=datetime.now() - timedelta(days=1)
        )
        
        with patch.object(self.auth_service, '_load_github_token', return_value=expired_token):
            with patch('builtins.print') as mock_print:
                token = self.auth_service.get_github_token()
                assert token is None
                mock_print.assert_called_with("⚠️  GitHub token expired. Please refresh your fine-grained token.")
    
    def test_get_github_headers(self):
        """Test GitHub headers generation."""
        with patch.object(self.auth_service, 'get_github_token', return_value="test_github_token"):
            headers = self.auth_service.get_github_headers()
            assert headers["Authorization"] == "token test_github_token"
            assert headers["Accept"] == "application/vnd.github.v3+json"
    
    def test_get_github_headers_no_token(self):
        """Test GitHub headers generation when no token available."""
        with patch.object(self.auth_service, 'get_github_token', return_value=None):
            with pytest.raises(ValueError, match="GitHub token not available or expired"):
                self.auth_service.get_github_headers()
    
    def test_get_obs_credentials(self, tmp_path, monkeypatch):
        """Test getting OBS credentials."""
        # Use temporary file for OBS credentials to avoid affecting real credentials
        temp_obs_file = tmp_path / "obs_credentials.json"
        monkeypatch.setattr(AuthService, "obs_credentials_file", temp_obs_file)
        
        with patch.dict(os.environ, {
            'OBS_HOST': '127.0.0.1',
            'OBS_PORT': '4455',
            'OBS_PASSWORD': 'test_password',
            'OBS_SCENE': 'test_scene',
            'OBS_DRY_RUN': 'false'
        }):
            auth_service = AuthService()
            credentials = auth_service.get_obs_credentials()
            assert credentials is not None
            assert credentials.host == '127.0.0.1'
            assert credentials.port == 4455
            assert credentials.password.get_secret_value() == 'test_password'
            assert credentials.scene == 'test_scene'
            assert not credentials.dry_run
    
    def test_validate_obs_auth_dry_run(self, tmp_path, monkeypatch):
        """Test OBS auth validation in dry run mode."""
        # Use temporary file for OBS credentials to avoid affecting real credentials
        temp_obs_file = tmp_path / "obs_credentials.json"
        monkeypatch.setattr(AuthService, "obs_credentials_file", temp_obs_file)
        
        with patch.dict(os.environ, {
            'OBS_HOST': '127.0.0.1',
            'OBS_PORT': '4455',
            'OBS_PASSWORD': 'test_password',
            'OBS_SCENE': 'test_scene',
            'OBS_DRY_RUN': 'true'
        }):
            auth_service = AuthService()
            assert auth_service.validate_obs_auth() is True
