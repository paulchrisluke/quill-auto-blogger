"""
Authentication service for Twitch, GitHub, and Cloudflare R2.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv

from models import TwitchToken, GitHubToken, CloudflareR2Credentials, DiscordCredentials

# Load environment variables
load_dotenv()


class AuthService:
    """Handles authentication for Twitch, GitHub, Cloudflare R2, and Discord APIs."""
    
    def __init__(self):
        self.cache_dir = Path.home() / ".cache" / "my-activity"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.twitch_token_file = self.cache_dir / "twitch_token.json"
        self.github_token_file = self.cache_dir / "github_token.json"
        self.discord_credentials_file = self.cache_dir / "discord_credentials.json"
        
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
    
    def get_r2_credentials(self) -> Optional[CloudflareR2Credentials]:
        """Get R2 credentials using existing Cloudflare API credentials."""
        # Use existing Cloudflare credentials for R2 access
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        bucket = os.getenv("R2_BUCKET")
        public_base_url = os.getenv("R2_PUBLIC_BASE_URL")
        
        if not all([account_id, api_token, bucket]):
            return None
        
        # Create endpoint URL from account ID
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        
        credentials = CloudflareR2Credentials(
            access_key_id=account_id,  # Use account ID as access key
            secret_access_key=api_token,  # Use API token as secret
            endpoint=endpoint,
            bucket=bucket,
            region="auto",
            public_base_url=public_base_url
        )
        
        return credentials
    
    def get_discord_credentials(self) -> Optional[DiscordCredentials]:
        """Get Discord credentials from cache or environment."""
        credentials = self._load_discord_credentials()
        
        if credentials is None:
            # Try to initialize from environment variables
            credentials = self._initialize_discord_credentials_from_env()
        
        return credentials
    
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
    

    
    def _load_discord_credentials(self) -> Optional[DiscordCredentials]:
        """Load Discord credentials from cache."""
        if not self.discord_credentials_file.exists():
            return None
        
        try:
            with open(self.discord_credentials_file, 'r') as f:
                data = json.load(f)
                # Convert string back to datetime
                data['created_at'] = datetime.fromisoformat(data['created_at'])
                return DiscordCredentials(**data)
        except Exception:
            return None
    
    def _save_discord_credentials(self, credentials: DiscordCredentials):
        """Save Discord credentials to cache."""
        with open(self.discord_credentials_file, 'w') as f:
            f.write(credentials.model_dump_json(indent=2))
    
    def _initialize_discord_credentials_from_env(self) -> Optional[DiscordCredentials]:
        """Initialize Discord credentials from environment variables."""
        application_id = os.getenv("DISCORD_APPLICATION_ID")
        public_key = os.getenv("DISCORD_PUBLIC_KEY")
        token = os.getenv("DISCORD_TOKEN")
        guild_id = os.getenv("DISCORD_GUILD_ID")
        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        mention_target = os.getenv("DISCORD_MENTION_TARGET")
        
        if not all([application_id, public_key, token, guild_id, channel_id]):
            return None
        
        credentials = DiscordCredentials(
            application_id=application_id,
            public_key=public_key,
            token=token,
            guild_id=guild_id,
            channel_id=channel_id,
            webhook_url=webhook_url,
            mention_target=mention_target
        )
        
        self._save_discord_credentials(credentials)
        return credentials
    
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
    
    def validate_r2_auth(self) -> bool:
        """Validate R2 authentication by testing bucket access."""
        credentials = self.get_r2_credentials()
        if not credentials:
            return False
        
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=credentials.access_key_id,
                aws_secret_access_key=credentials.secret_access_key,
                endpoint_url=credentials.endpoint,
                region_name=credentials.region
            )
            
            # Test by listing objects (limited to 1 to minimize data transfer)
            s3_client.list_objects_v2(Bucket=credentials.bucket, MaxKeys=1)
            return True
            
        except (ClientError, ImportError, Exception):
            return False
    
    def validate_discord_auth(self) -> bool:
        """Validate Discord authentication by testing bot access."""
        credentials = self.get_discord_credentials()
        if not credentials:
            return False
        
        try:
            headers = {
                "Authorization": f"Bot {credentials.token}",
                "Content-Type": "application/json"
            }
            
            with httpx.Client() as client:
                response = client.get("https://discord.com/api/v10/users/@me", headers=headers)
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
    
    def get_discord_headers(self) -> dict:
        """Get headers for Discord API requests."""
        credentials = self.get_discord_credentials()
        if not credentials:
            raise ValueError("Discord credentials not available")
        
        return {
            "Authorization": f"Bot {credentials.token}",
            "Content-Type": "application/json"
        }
