"""
Pydantic models for the activity fetcher.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class TwitchClip(BaseModel):
    """Model for Twitch clip data."""
    id: str
    title: str
    url: str
    broadcaster_name: str
    created_at: datetime
    transcript: Optional[str] = None
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    duration: Optional[float] = None
    view_count: Optional[int] = None
    language: Optional[str] = None


class GitHubEvent(BaseModel):
    """Model for GitHub activity events."""
    id: str
    type: str
    repo: str
    actor: str
    created_at: datetime
    details: Dict[str, Any] = Field(default_factory=dict)
    url: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


class TwitchToken(BaseModel):
    """Model for Twitch OAuth token."""
    access_token: str
    expires_in: int
    token_type: str
    expires_at: datetime


class GitHubToken(BaseModel):
    """Model for GitHub fine-grained token."""
    token: str
    expires_at: datetime
    permissions: Dict[str, str] = Field(default_factory=dict)


class CloudflareR2Credentials(BaseModel):
    """Model for Cloudflare R2 S3 credentials."""
    access_key_id: str
    secret_access_key: str
    endpoint: str
    bucket: str
    region: str = "auto"
    public_base_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class DiscordCredentials(BaseModel):
    """Model for Discord bot credentials."""
    application_id: str
    public_key: str
    token: str
    guild_id: str
    channel_id: str
    webhook_url: Optional[str] = None
    mention_target: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class CacheEntry(BaseModel):
    """Model for cache entries."""
    id: str
    type: str  # 'twitch_clip' or 'github_event'
    created_at: datetime
    data: Dict[str, Any]


class SeenIds(BaseModel):
    """Model for tracking seen IDs to prevent duplicates."""
    twitch_clips: List[str] = Field(default_factory=list)
    github_events: List[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.now)
