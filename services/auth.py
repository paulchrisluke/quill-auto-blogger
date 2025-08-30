"""
Authentication service for Twitch and GitHub.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import httpx

from models import TwitchToken, GitHubToken


class AuthService:
    """Handles authentication for Twitch and GitHub APIs."""
    
    def __init__(self):
        self.cache_dir = Path.home() / ".cache" / "my-activity"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.twitch_token_file = self.cache_dir / "twitch_token.json"
        self.github_token_file = self.cache_dir / "github_token.json"
        
        # Load environment variables
        self.twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
        self.twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
        self.github_token = os.getenv('GITHUB_TOKEN')
    
    def get_twitch_token(self) -> Optional[str]:
        """Get a valid Twitch access token, refreshing if necessary."""
        token = self._load_twitch_token()
        
        if token is None or self._is_token_expired(token):
            token = self._refresh_twitch_token()
        
        return token.access_token if token else None
    
    def get_github_token(self) -> Optional[str]:
        """Get a valid GitHub token, checking expiration."""
        token = self._load_github_token()
        
        if token is None or self._is_github_token_expired(token):
            # For GitHub fine-grained tokens, we need user to refresh manually
            # since we can't refresh them programmatically
            print("⚠️  GitHub token expired. Please refresh your fine-grained token.")
            return None
        
        return token.token
    
    def _load_twitch_token(self) -> Optional[TwitchToken]:
        """Load Twitch token from cache."""
        if not self.twitch_token_file.exists():
            return None
        
        try:
            with open(self.twitch_token_file, 'r') as f:
                data = json.load(f)
                # Convert string back to datetime
                data['expires_at'] = datetime.fromisoformat(data['expires_at'])
                return TwitchToken(**data)
        except Exception:
            return None
    
    def _save_twitch_token(self, token: TwitchToken):
        """Save Twitch token to cache."""
        with open(self.twitch_token_file, 'w') as f:
            f.write(token.model_dump_json(indent=2))
    
    def _load_github_token(self) -> Optional[GitHubToken]:
        """Load GitHub token from cache."""
        if not self.github_token_file.exists():
            return None
        
        try:
            with open(self.github_token_file, 'r') as f:
                data = json.load(f)
                # Convert string back to datetime
                data['expires_at'] = datetime.fromisoformat(data['expires_at'])
                return GitHubToken(**data)
        except Exception:
            return None
    
    def _save_github_token(self, token: GitHubToken):
        """Save GitHub token to cache."""
        with open(self.github_token_file, 'w') as f:
            f.write(token.model_dump_json(indent=2))
    
    def cache_github_token(self, token: str, expires_at: datetime, permissions: dict = None):
        """Cache GitHub token with expiration info."""
        github_token = GitHubToken(
            token=token,
            expires_at=expires_at,
            permissions=permissions or {}
        )
        self._save_github_token(github_token)
    
    def initialize_github_token_from_env(self):
        """Initialize GitHub token from environment variable."""
        if not self.github_token:
            return False
        
        # For fine-grained tokens, we need to get expiration info from GitHub API
        try:
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            with httpx.Client() as client:
                # Get token info from GitHub API
                response = client.get("https://api.github.com/user", headers=headers)
                if response.status_code == 200:
                    # Fine-grained tokens don't have a direct expiration endpoint
                    # We'll set a default expiration (90 days from now)
                    # User should update this when they refresh their token
                    expires_at = datetime.now() + timedelta(days=90)
                    
                    self.cache_github_token(
                        token=self.github_token,
                        expires_at=expires_at,
                        permissions={}
                    )
                    return True
                else:
                    return False
                    
        except Exception:
            return False
    
    def _is_token_expired(self, token: TwitchToken) -> bool:
        """Check if token is expired (with 5 minute buffer)."""
        return datetime.now() >= token.expires_at - timedelta(minutes=5)
    
    def _is_github_token_expired(self, token: GitHubToken) -> bool:
        """Check if GitHub token is expired (with 1 day buffer)."""
        return datetime.now() >= token.expires_at - timedelta(days=1)
    
    def _refresh_twitch_token(self) -> Optional[TwitchToken]:
        """Refresh Twitch OAuth token using client credentials flow."""
        if not self.twitch_client_id or not self.twitch_client_secret:
            raise ValueError("Twitch client ID and secret not configured")
        
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            "client_id": self.twitch_client_id,
            "client_secret": self.twitch_client_secret,
            "grant_type": "client_credentials"
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(url, data=data)
                response.raise_for_status()
                
                token_data = response.json()
                expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
                
                token = TwitchToken(
                    access_token=token_data['access_token'],
                    expires_in=token_data['expires_in'],
                    token_type=token_data['token_type'],
                    expires_at=expires_at
                )
                
                self._save_twitch_token(token)
                return token
                
        except Exception as e:
            print(f"Error refreshing Twitch token: {e}")
            return None
    
    def validate_twitch_auth(self) -> bool:
        """Validate Twitch authentication."""
        try:
            token = self.get_twitch_token()
            if not token:
                return False
            
            # Test the token by making a simple API call
            headers = {
                "Client-ID": self.twitch_client_id,
                "Authorization": f"Bearer {token}"
            }
            
            with httpx.Client() as client:
                response = client.get("https://api.twitch.tv/helix/users", headers=headers)
                return response.status_code == 200
                
        except Exception:
            return False
    
    def validate_github_auth(self) -> bool:
        """Validate GitHub authentication."""
        token = self.get_github_token()
        if not token:
            return False
        
        try:
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            with httpx.Client() as client:
                response = client.get("https://api.github.com/user", headers=headers)
                return response.status_code == 200
                
        except Exception:
            return False
    
    def get_github_headers(self) -> dict:
        """Get headers for GitHub API requests."""
        token = self.get_github_token()
        if not token:
            raise ValueError("GitHub token not available or expired")
        
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def get_twitch_headers(self) -> dict:
        """Get headers for Twitch API requests."""
        token = self.get_twitch_token()
        return {
            "Client-ID": self.twitch_client_id,
            "Authorization": f"Bearer {token}"
        }
