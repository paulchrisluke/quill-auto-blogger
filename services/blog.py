"""
Blog digest builder service for generating daily blog posts with frontmatter.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from models import TwitchClip, GitHubEvent

if TYPE_CHECKING:
    from services.utils import CacheManager

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class BlogDigestBuilder:
    """Builds daily digest blog posts from Twitch clips and GitHub events."""
    
    def __init__(self):
        self.data_dir = Path("data")
        self.blogs_dir = Path("blogs")
        self.blogs_dir.mkdir(parents=True, exist_ok=True)
        
        # Blog metadata from environment
        self.blog_author = os.getenv("BLOG_AUTHOR", "Unknown Author")
        self.blog_base_url = os.getenv("BLOG_BASE_URL", "https://example.com").rstrip("/")
        self.blog_default_image = os.getenv("BLOG_DEFAULT_IMAGE", "https://example.com/default.jpg")
    
    def build_digest(self, target_date: str) -> Dict[str, Any]:
        """
        Build a digest for a specific date.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary containing digest data and metadata
        """
        # Validate date format early
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"target_date must be YYYY-MM-DD, got: {target_date}") from exc
        date_path = self.data_dir / target_date
        
        if not date_path.exists():
            raise FileNotFoundError(f"No data found for date: {target_date}")
        
        # Load all data for the date
        twitch_clips = self._load_twitch_clips(date_path)
        github_events = self._load_github_events(date_path)
        
        if not twitch_clips and not github_events:
            raise FileNotFoundError(f"No data files found in {date_path} for {target_date}")
        
        # Build digest structure
        digest = {
            "date": target_date,
            "twitch_clips": [clip.model_dump() for clip in twitch_clips],
            "github_events": [event.model_dump() for event in github_events],
            "metadata": self._generate_metadata(target_date, twitch_clips, github_events)
        }
        
        return digest
    
    def build_latest_digest(self) -> Dict[str, Any]:
        """
        Build digest for the most recent date with data.
        
        Returns:
            Dictionary containing digest data and metadata
        """
        # Find the most recent date folder
        if not self.data_dir.exists():
            raise FileNotFoundError("No data folders found")
        date_folders = [d for d in self.data_dir.iterdir() if d.is_dir()]

        candidates = []
        for d in date_folders:
            try:
                candidates.append((datetime.strptime(d.name, "%Y-%m-%d").date(), d.name))
            except ValueError:
                logger.debug("Skipping non-date folder: %s", d.name)

        if not candidates:
            raise FileNotFoundError("No data folders found")

        latest_date = max(candidates)[1]
        return self.build_digest(latest_date)
    
    def generate_markdown(self, digest: Dict[str, Any]) -> str:
        """
        Generate Markdown content with frontmatter from digest data.
        
        Args:
            digest: Digest data dictionary
            
        Returns:
            Markdown string with frontmatter
        """
        frontmatter = self._generate_frontmatter(digest)
        content = self._generate_content(digest)
        
        return f"{frontmatter}\n\n{content}"
    
    def save_digest(self, digest: Dict[str, Any], *, cache_manager: Optional[CacheManager] = None) -> Path:
        """
        Save digest as JSON file for AI ingestion.
        
        Args:
            digest: Digest data dictionary
            cache_manager: Optional cache manager instance (defaults to new instance)
            
        Returns:
            Path to the saved JSON file
        """
        target_date = digest["date"]
        
        # Create date subdirectory
        date_dir = self.blogs_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON digest using atomic write
        json_path = date_dir / f"PRE-CLEANED-{target_date}_digest.json"
        if json_path.exists():
            logger.info("Overwriting existing digest: %s", json_path)
        
        # Use the cache manager's atomic write method
        if cache_manager is None:
            from services.utils import CacheManager
            cache_manager = CacheManager()
        cache_manager.atomic_write_json(json_path, digest, overwrite=True)
        
        return json_path
    
    def _load_twitch_clips(self, date_path: Path) -> List[TwitchClip]:
        """Load all Twitch clips for a given date."""
        clips = []
        
        for file_path in sorted(date_path.glob("twitch_clip_*.json")):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    clip = TwitchClip(**data)
                    clips.append(clip)
            except (json.JSONDecodeError, OSError, ValidationError) as e:
                logger.warning(f"Could not load Twitch clip {file_path}: {e}", exc_info=True)
        
        return clips
    
    def _load_github_events(self, date_path: Path) -> List[GitHubEvent]:
        """Load all GitHub events for a given date."""
        events = []
        
        for file_path in sorted(date_path.glob("github_event_*.json")):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    event = GitHubEvent(**data)
                    events.append(event)
            except (json.JSONDecodeError, OSError, ValidationError) as e:
                logger.warning(f"Could not load GitHub event {file_path}: {e}", exc_info=True)
        
        return events
    
    def _generate_metadata(self, target_date: str, clips: List[TwitchClip], events: List[GitHubEvent]) -> Dict[str, Any]:
        """Generate metadata for the digest."""
        # Extract keywords from data
        keywords = set()
        
        # Add repo names from GitHub events
        for event in events:
            # Validate repo format before splitting
            owner, separator, repo_name = event.repo.partition('/')
            if separator and owner and repo_name:
                keywords.add(owner)  # owner
                keywords.add(repo_name)  # repo name
            else:
                logger.warning(f"Invalid repo format '{event.repo}' for event {event.id}, skipping repo keywords")
        
        # Add languages from Twitch clips
        for clip in clips:
            if clip.language:
                keywords.add(clip.language)
        
        # Add event types
        for event in events:
            keywords.add(event.type)
        
        return {
            "total_clips": len(clips),
            "total_events": len(events),
            "keywords": sorted(keywords),
            "date_parsed": datetime.strptime(target_date, "%Y-%m-%d").date()
        }
    
    def _generate_frontmatter(self, digest: Dict[str, Any]) -> str:
        """Generate YAML frontmatter with schema.org metadata."""
        target_date = digest["date"]
        metadata = digest["metadata"]
        clips = digest["twitch_clips"]
        events = digest["github_events"]
        
        # Parse date
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Generate headline
        headline = f"Daily Devlog — {date_obj.strftime('%b %d, %Y')}"
        
        # Build schema.org Article
        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": headline,
            "datePublished": target_date,
            "author": {
                "@type": "Person",
                "name": self.blog_author
            },
            "keywords": metadata["keywords"],
            "url": f"{self.blog_base_url}/blog/{target_date}",
            "image": self.blog_default_image
        }
        
        # Build VideoObject schemas for Twitch clips
        video_objects = []
        for clip in clips:
            upload_date = clip.get("created_at")
            if isinstance(upload_date, (datetime, date)):
                upload_date = upload_date.isoformat()
            video_schema = {
                "@type": "VideoObject",
                "name": clip["title"],
                "description": clip.get("transcript", "")[:200] + "..." if clip.get("transcript") else "",
                "url": clip["url"],
                "uploadDate": upload_date,
                "duration": (
                    f"PT{int(round(float(clip.get('duration', 0.0))))}S"
                    if clip.get("duration") is not None else None
                ),
                "thumbnailUrl": f"https://clips-media-assets2.twitch.tv/{clip['id']}/preview-480x272.jpg"
            }
            # Remove None values
            video_schema = {k: v for k, v in video_schema.items() if v is not None}
            video_objects.append(video_schema)
        
        # Build FAQPage schema if there are multiple GitHub events
        faq_schema = None
        if len(events) > 1:
            faq_entries = []
            for event in events:
                if event.get("title") or event.get("details", {}).get("commit_messages"):
                    question = event.get("title", f"{event.get('type', 'unknown')} in {event.get('repo', '')}")
                    answer = event.get("body", "")
                    if not answer and event.get("details", {}).get("commit_messages"):
                        answer = "\n".join(event.get("details", {}).get("commit_messages", []))
                    
                    if answer:
                        faq_entries.append({
                            "@type": "Question",
                            "name": question,
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": answer
                            }
                        })
            
            if faq_entries:
                faq_schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": faq_entries
                }
        
        # Build Open Graph metadata
        og_metadata = {
            "og:title": headline,
            "og:description": (
                f"Daily development log with {metadata['total_clips']} "
                f"Twitch {'clip' if metadata['total_clips']==1 else 'clips'} and "
                f"{metadata['total_events']} GitHub {'event' if metadata['total_events']==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.blog_base_url}/blog/{target_date}",
            "og:image": self.blog_default_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Combine all metadata
        frontmatter_data = {
            "title": headline,
            "date": target_date,
            "author": self.blog_author,
            "schema": {
                "article": article_schema,
                "videos": video_objects
            },
            "og": og_metadata
        }
        
        # Add FAQ schema if available
        if faq_schema:
            frontmatter_data["schema"]["faq"] = faq_schema
        
        # Convert to YAML
        yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return f"---\n{yaml_content}---\n"
    
    def _generate_content(self, digest: Dict[str, Any]) -> str:
        """Generate the main content of the blog post."""
        target_date = digest["date"]
        clips = digest["twitch_clips"]
        events = digest["github_events"]
        
        content_parts = []
        
        # Add header
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        content_parts.append(f"# Daily Devlog — {date_obj.strftime('%B %d, %Y')}")
        content_parts.append("")
        
        # Add summary
        content_parts.append(
            f"Today's development activities include {len(clips)} Twitch "
            f"{'clip' if len(clips)==1 else 'clips'} and {len(events)} GitHub "
            f"{'event' if len(events)==1 else 'events'}."
        )
        content_parts.append("")
        
        # Add Twitch clips section
        if clips:
            content_parts.append("## Twitch Clips")
            content_parts.append("")
            
            for clip in clips:
                content_parts.append(f"### {clip.get('title', 'Untitled Clip')}")
                if clip.get('duration') is not None:
                    content_parts.append(f"**Duration:** {clip['duration']} seconds")
                content_parts.append(f"**Views:** {clip.get('view_count', 'Unknown')}")
                content_parts.append(f"**URL:** {clip.get('url', '')}")
                content_parts.append("")
                
                if clip.get('transcript'):
                    content_parts.append("**Transcript:**")
                    content_parts.append(f"> {clip.get('transcript', '')}")
                    content_parts.append("")
        
        # Add GitHub events section
        if events:
            content_parts.append("## GitHub Activity")
            content_parts.append("")
            
            for event in events:
                content_parts.append(f"### {event.get('type', 'unknown')} in {event.get('repo', '')}")
                content_parts.append(f"**Actor:** {event.get('actor', 'Unknown')}")
                created = event.get('created_at', 'Unknown')
                if isinstance(created, (datetime, date)):
                    created = created.isoformat()
                content_parts.append(f"**Time:** {created}")
                
                if event.get('url'):
                    content_parts.append(f"**URL:** {event.get('url', '')}")
                
                if event.get('title'):
                    content_parts.append(f"**Title:** {event.get('title', '')}")
                
                if event.get('body'):
                    content_parts.append(f"**Description:** {event.get('body', '')}")
                
                # Add commit messages if available
                if event.get('details', {}).get('commit_messages'):
                    content_parts.append("**Commits:**")
                    for msg in event.get('details', {}).get('commit_messages', []):
                        content_parts.append(f"- {msg}")
                
                content_parts.append("")
        
        return "\n".join(content_parts)
