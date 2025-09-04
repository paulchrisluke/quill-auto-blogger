"""
Pydantic models for the activity fetcher and digest pipeline.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Union, Literal
from pydantic import BaseModel, Field, SecretStr


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
    access_token: SecretStr
    expires_in: int
    token_type: str
    expires_at: datetime


class GitHubToken(BaseModel):
    """Model for GitHub fine-grained token."""
    token: SecretStr
    expires_at: datetime
    permissions: Dict[str, str] = Field(default_factory=dict)


class CloudflareR2Credentials(BaseModel):
    """Model for Cloudflare R2 S3 credentials."""
    access_key_id: str
    secret_access_key: SecretStr
    endpoint: str
    bucket: str
    region: str = "auto"
    public_base_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class DiscordCredentials(BaseModel):
    """Model for Discord bot credentials."""
    application_id: str
    public_key: str
    token: SecretStr
    guild_id: str
    channel_id: str
    webhook_url: Optional[str] = None
    mention_target: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class OBSCredentials(BaseModel):
    """Model for OBS WebSocket credentials."""
    host: str = "127.0.0.1"
    port: int = 4455
    password: SecretStr
    scene: str = ""
    dry_run: bool = False
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


# ============================================================================
# Digest Pipeline Models - New Clean Architecture
# ============================================================================

class Meta(BaseModel):
    """Metadata for digest files with type and version information."""
    kind: Literal["RawEvents", "NormalizedDigest", "EnrichedDigest", "PublishPackage"]
    version: int = Field(default=1, ge=1)
    generated_at: datetime = Field(default_factory=datetime.now)


class RawEvents(BaseModel):
    """Raw Events: snapshot from sources before any transforms."""
    meta: Meta = Field(default_factory=lambda: Meta(kind="RawEvents"))
    twitch: Optional[List[Dict[str, Any]]] = None
    github: Optional[List[Dict[str, Any]]] = None


class StoryPacket(BaseModel):
    """Minimal story packet structure for normalized digest."""
    id: str
    title: str
    story_type: str
    why: str
    highlights: List[str] = Field(default_factory=list)
    video: Optional[Dict[str, Any]] = None


class NormalizedDigest(BaseModel):
    """Normalized Digest: structured, de-duplicated, no AI, no CDN."""
    meta: Meta = Field(default_factory=lambda: Meta(kind="NormalizedDigest"))
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    story_packets: List[StoryPacket] = Field(default_factory=list)


class EnrichedDigest(BaseModel):
    """Enriched Digest: normalized + AI text + resolved media + SEO fields."""
    meta: Meta = Field(default_factory=lambda: Meta(kind="EnrichedDigest"))
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    story_packets: List[Dict[str, Any]] = Field(default_factory=list)
    related_posts: Optional[List[Dict[str, Any]]] = None
    cdn: Optional[Dict[str, str]] = None


class PublishPackage(BaseModel):
    """Publish Package: Nuxt-ready, public API with canonical URLs."""
    meta: Meta = Field(default_factory=lambda: Meta(kind="PublishPackage"))
    context: str = Field(default="https://schema.org", alias="@context")
    type: str = Field(default="BlogPosting", alias="@type")
    url: str
    datePublished: str
    dateModified: str
    image: Union[str, List[str]]
    wordCount: int
    timeRequired: str  # ISO 8601 duration
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    content: Dict[str, str] = Field(default_factory=dict)
    story_packets: List[Dict[str, Any]] = Field(default_factory=list)
    related_posts: Optional[List[Dict[str, Any]]] = None
    seo_meta: Dict[str, str] = Field(default_factory=dict)
