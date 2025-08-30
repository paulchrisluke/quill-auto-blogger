"""
Blog digest builder service for generating daily blog posts with frontmatter.
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
from dotenv import load_dotenv

from models import TwitchClip, GitHubEvent

# Load environment variables
load_dotenv()


class BlogDigestBuilder:
    """Builds daily digest blog posts from Twitch clips and GitHub events."""
    
    def __init__(self):
        self.data_dir = Path("data")
        self.blogs_dir = Path("blogs")
        self.blogs_dir.mkdir(exist_ok=True)
        
        # Blog metadata from environment
        self.blog_author = os.getenv("BLOG_AUTHOR", "Unknown Author")
        self.blog_base_url = os.getenv("BLOG_BASE_URL", "https://example.com")
        self.blog_default_image = os.getenv("BLOG_DEFAULT_IMAGE", "https://example.com/default.jpg")
    
    def build_digest(self, target_date: str) -> Dict[str, Any]:
        """
        Build a digest for a specific date.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary containing digest data and metadata
        """
        date_path = self.data_dir / target_date
        
        if not date_path.exists():
            raise FileNotFoundError(f"No data found for date: {target_date}")
        
        # Load all data for the date
        twitch_clips = self._load_twitch_clips(date_path)
        github_events = self._load_github_events(date_path)
        
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
        date_folders = [d for d in self.data_dir.iterdir() if d.is_dir() and d.name != "__pycache__"]
        
        if not date_folders:
            raise FileNotFoundError("No data folders found")
        
        # Sort by date and get the most recent
        latest_date = sorted(date_folders, key=lambda x: x.name, reverse=True)[0].name
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
    
    def save_digest(self, digest: Dict[str, Any]) -> Path:
        """
        Save digest as JSON file for AI ingestion.
        
        Args:
            digest: Digest data dictionary
            
        Returns:
            Path to the saved JSON file
        """
        target_date = digest["date"]
        
        # Create date subdirectory
        date_dir = self.blogs_dir / target_date
        date_dir.mkdir(exist_ok=True)
        
        # Save JSON digest
        json_path = date_dir / f"PRE-CLEANED-{target_date}_digest.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(digest, f, indent=2, default=str)
        
        return json_path
    
    def _load_twitch_clips(self, date_path: Path) -> List[TwitchClip]:
        """Load all Twitch clips for a given date."""
        clips = []
        
        for file_path in date_path.glob("twitch_clip_*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    clip = TwitchClip(**data)
                    clips.append(clip)
            except Exception as e:
                print(f"Warning: Could not load Twitch clip {file_path}: {e}")
        
        return clips
    
    def _load_github_events(self, date_path: Path) -> List[GitHubEvent]:
        """Load all GitHub events for a given date."""
        events = []
        
        for file_path in date_path.glob("github_event_*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    event = GitHubEvent(**data)
                    events.append(event)
            except Exception as e:
                print(f"Warning: Could not load GitHub event {file_path}: {e}")
        
        return events
    
    def _generate_metadata(self, target_date: str, clips: List[TwitchClip], events: List[GitHubEvent]) -> Dict[str, Any]:
        """Generate metadata for the digest."""
        # Extract keywords from data
        keywords = set()
        
        # Add repo names from GitHub events
        for event in events:
            keywords.add(event.repo.split('/')[0])  # owner
            keywords.add(event.repo.split('/')[1])  # repo name
        
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
            "keywords": list(keywords),
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
            video_schema = {
                "@type": "VideoObject",
                "name": clip["title"],
                "description": clip.get("transcript", "")[:200] + "..." if clip.get("transcript") else "",
                "url": clip["url"],
                "uploadDate": clip["created_at"],
                "duration": f"PT{int(clip.get('duration', 0))}S" if clip.get("duration") else None,
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
                    question = event.get("title", f"{event['type']} in {event['repo']}")
                    answer = event.get("body", "")
                    if not answer and event.get("details", {}).get("commit_messages"):
                        answer = "\n".join(event["details"]["commit_messages"])
                    
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
            "og:description": f"Daily development log with {metadata['total_clips']} Twitch clips and {metadata['total_events']} GitHub events",
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
        yaml_content = yaml.dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return f"---\n{yaml_content}---"
    
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
        content_parts.append(f"Today's development activities include {len(clips)} Twitch clips and {len(events)} GitHub events.")
        content_parts.append("")
        
        # Add Twitch clips section
        if clips:
            content_parts.append("## Twitch Clips")
            content_parts.append("")
            
            for clip in clips:
                content_parts.append(f"### {clip['title']}")
                content_parts.append(f"**Duration:** {clip.get('duration', 'Unknown')} seconds")
                content_parts.append(f"**Views:** {clip.get('view_count', 'Unknown')}")
                content_parts.append(f"**URL:** {clip['url']}")
                content_parts.append("")
                
                if clip.get('transcript'):
                    content_parts.append("**Transcript:**")
                    content_parts.append(f"> {clip['transcript']}")
                    content_parts.append("")
        
        # Add GitHub events section
        if events:
            content_parts.append("## GitHub Activity")
            content_parts.append("")
            
            for event in events:
                content_parts.append(f"### {event['type']} in {event['repo']}")
                content_parts.append(f"**Actor:** {event['actor']}")
                content_parts.append(f"**Time:** {event['created_at']}")
                
                if event.get('url'):
                    content_parts.append(f"**URL:** {event['url']}")
                
                if event.get('title'):
                    content_parts.append(f"**Title:** {event['title']}")
                
                if event.get('body'):
                    content_parts.append(f"**Description:** {event['body']}")
                
                # Add commit messages if available
                if event.get('details', {}).get('commit_messages'):
                    content_parts.append("**Commits:**")
                    for msg in event['details']['commit_messages']:
                        content_parts.append(f"- {msg}")
                
                content_parts.append("")
        
        return "\n".join(content_parts)
