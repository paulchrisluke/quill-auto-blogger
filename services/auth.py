"""
Authentication service for Twitch, GitHub, Cloudflare R2, and Discord.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv

from models import TwitchToken, GitHubToken, CloudflareR2Credentials, DiscordCredentials, OBSCredentials
from pydantic import SecretStr

# Load environment variables
load_dotenv()


class AuthService:
    """Handles authentication for Twitch, GitHub, Cloudflare R2, and Discord APIs."""
    
    def __init__(self):
        self.cache_dir = Path.home() / ".cache" / "quill-auto-blogger"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.twitch_token_file = self.cache_dir / "twitch_token.json"
        self.github_token_file = self.cache_dir / "github_token.json"
        self.discord_credentials_file = self.cache_dir / "discord_credentials.json"
        self.obs_credentials_file = self.cache_dir / "obs_credentials.json"
        
        # Load environment variables
        self.twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
        self.twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
        self.github_token = os.getenv('GITHUB_TOKEN')
    
    def get_twitch_token(self) -> Optional[str]:
        """Get a valid Twitch access token, refreshing if necessary."""
        token = self._load_twitch_token()
        
        if token is None or self._is_token_expired(token):
            token = self._refresh_twitch_token()
        
        return token.access_token.get_secret_value() if token else None
    
    def get_github_token(self) -> Optional[str]:
        """Get a valid GitHub token, checking expiration."""
        token = self._load_github_token()
        
        if token is None or self._is_github_token_expired(token):
            # For GitHub fine-grained tokens, we need user to refresh manually
            # since we can't refresh them programmatically
            print("⚠️  GitHub token expired. Please refresh your fine-grained token.")
            return None
        
        return token.token.get_secret_value()
    
    def get_r2_credentials(self) -> Optional[CloudflareR2Credentials]:
        """Get R2 credentials from environment variables."""
        access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        endpoint = os.getenv("R2_S3_ENDPOINT")
        bucket = os.getenv("R2_BUCKET")
        region = os.getenv("R2_REGION", "auto")
        public_base_url = os.getenv("R2_PUBLIC_BASE_URL")
        
        if not all([access_key_id, secret_access_key, endpoint, bucket]):
            return None
        
        credentials = CloudflareR2Credentials(
            access_key_id=access_key_id,
            secret_access_key=SecretStr(secret_access_key),
            endpoint=endpoint,
            bucket=bucket,
            region=region,
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
    
    def get_obs_credentials(self) -> Optional[OBSCredentials]:
        """Get OBS credentials from cache or environment."""
        credentials = self._load_obs_credentials()
        
        if credentials is None:
            # Try to initialize from environment variables
            credentials = self._initialize_obs_credentials_from_env()
        
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
                # Convert plain string back to SecretStr
                data['access_token'] = SecretStr(data['access_token'])
                return TwitchToken(**data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None
    
    def _save_twitch_token(self, token: TwitchToken):
        """Save Twitch token to cache."""
        # Convert SecretStr to plain string for storage
        data = token.model_dump()
        data['access_token'] = token.access_token.get_secret_value()
        
        with open(self.twitch_token_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        try:
            os.chmod(self.twitch_token_file, 0o600)
        except OSError:
            pass
    
    def _load_github_token(self) -> Optional[GitHubToken]:
        """Load GitHub token from cache."""
        if not self.github_token_file.exists():
            return None
        
        try:
            with open(self.github_token_file, 'r') as f:
                data = json.load(f)
                # Convert string back to datetime
                data['expires_at'] = datetime.fromisoformat(data['expires_at'])
                # Convert plain string back to SecretStr
                data['token'] = SecretStr(data['token'])
                return GitHubToken(**data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None
    
    def _save_github_token(self, token: GitHubToken):
        """Save GitHub token to cache."""
        # Convert SecretStr to plain string for storage
        data = token.model_dump()
        data['token'] = token.token.get_secret_value()
        
        with open(self.github_token_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        try:
            os.chmod(self.github_token_file, 0o600)
        except OSError:
            pass
    

    
    def _load_discord_credentials(self) -> Optional[DiscordCredentials]:
        """Load Discord credentials from cache."""
        if not self.discord_credentials_file.exists():
            return None
        
        try:
            with open(self.discord_credentials_file, 'r') as f:
                data = json.load(f)
                # Convert string back to datetime
                data['created_at'] = datetime.fromisoformat(data['created_at'])
                # Convert plain string back to SecretStr
                data['token'] = SecretStr(data['token'])
                return DiscordCredentials(**data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None
    
    def _save_discord_credentials(self, credentials: DiscordCredentials):
        """Save Discord credentials to cache."""
        # Convert SecretStr to plain string for storage
        data = credentials.model_dump()
        data['token'] = credentials.token.get_secret_value()
        
        with open(self.discord_credentials_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        try:
            os.chmod(self.discord_credentials_file, 0o600)
        except OSError:
            pass
    
    def _load_obs_credentials(self) -> Optional[OBSCredentials]:
        """Load OBS credentials from cache."""
        if not self.obs_credentials_file.exists():
            return None
        
        try:
            with open(self.obs_credentials_file, 'r') as f:
                data = json.load(f)
                # Convert string back to datetime
                data['created_at'] = datetime.fromisoformat(data['created_at'])
                # Convert plain string back to SecretStr
                data['password'] = SecretStr(data['password'])
                return OBSCredentials(**data)
        except (json.JSONDecodeError, KeyError, OSError, ValueError):
            return None
    
    def _save_obs_credentials(self, credentials: OBSCredentials):
        """Save OBS credentials to cache."""
        # Convert SecretStr to plain string for storage
        data = credentials.model_dump()
        data['password'] = credentials.password.get_secret_value()
        
        with open(self.obs_credentials_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        try:
            os.chmod(self.obs_credentials_file, 0o600)
        except OSError:
            pass
    
    def _initialize_discord_credentials_from_env(self) -> Optional[DiscordCredentials]:
        """Initialize Discord credentials from environment variables."""
        application_id = os.getenv("DISCORD_APPLICATION_ID")
        public_key = os.getenv("DISCORD_PUBLIC_KEY")
        
        # Use DISCORD_BOT_TOKEN with fallback to legacy DISCORD_TOKEN
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            token = os.getenv("DISCORD_TOKEN")
            if token:
                import warnings
                warnings.warn(
                    "DISCORD_TOKEN is deprecated and will be removed in a future version. "
                    "Please use DISCORD_BOT_TOKEN instead.",
                    DeprecationWarning,
                    stacklevel=2
                )
        
        guild_id = os.getenv("DISCORD_GUILD_ID")
        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        mention_target = os.getenv("DISCORD_MENTION_TARGET")
        
        if not all([application_id, public_key, token, guild_id, channel_id]):
            return None
        
        credentials = DiscordCredentials(
            application_id=application_id,
            public_key=public_key,
            token=SecretStr(token),
            guild_id=guild_id,
            channel_id=channel_id,
            webhook_url=webhook_url,
            mention_target=mention_target
        )
        
        self._save_discord_credentials(credentials)
        return credentials
    
    def _initialize_obs_credentials_from_env(self) -> Optional[OBSCredentials]:
        """Initialize OBS credentials from environment variables."""
        host = os.getenv("OBS_HOST", "127.0.0.1")
        
        # Safely parse port with fallback to default
        port_str = os.getenv("OBS_PORT", "4455")
        try:
            port = int(port_str) if port_str else 4455
        except ValueError:
            port = 4455
        
        password = os.getenv("OBS_PASSWORD", "")
        scene = os.getenv("OBS_SCENE", "")
        dry_run = os.getenv("OBS_DRY_RUN", "false").lower() == "true"
        
        # Only save credentials if we have non-default values or essential config
        has_custom_config = (
            os.getenv("OBS_HOST") is not None or
            os.getenv("OBS_PORT") is not None or
            os.getenv("OBS_PASSWORD") is not None or
            os.getenv("OBS_SCENE") is not None or
            os.getenv("OBS_DRY_RUN") is not None
        )
        
        credentials = OBSCredentials(
            host=host,
            port=port,
            password=SecretStr(password),
            scene=scene,
            dry_run=dry_run
        )
        
        # Only cache if we have custom configuration
        if has_custom_config:
            self._save_obs_credentials(credentials)
        
        return credentials
    
    def cache_github_token(self, token: str, expires_at: datetime, permissions: dict = None):
        """Cache GitHub token with expiration info."""
        github_token = GitHubToken(
            token=SecretStr(token),
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
            
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
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
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
                response = client.post(url, data=data)
                response.raise_for_status()
                
                token_data = response.json()
                expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
                
                token = TwitchToken(
                    access_token=SecretStr(token_data['access_token']),
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
            
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
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
            
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
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
                aws_secret_access_key=credentials.secret_access_key.get_secret_value(),
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
                "Authorization": f"Bot {credentials.token.get_secret_value()}",
                "Content-Type": "application/json"
            }
            
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
                response = client.get("https://discord.com/api/v10/users/@me", headers=headers)
                return response.status_code == 200
                
        except Exception:
            return False
    
    def validate_obs_auth(self) -> bool:
        """Validate OBS authentication by testing WebSocket connection."""
        credentials = self.get_obs_credentials()
        if not credentials:
            return False
        
        if credentials.dry_run:
            return True
        
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((credentials.host, credentials.port))
            sock.close()
            return result == 0
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
            "Authorization": f"Bot {credentials.token.get_secret_value()}",
            "Content-Type": "application/json"
        }
