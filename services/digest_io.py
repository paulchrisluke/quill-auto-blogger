"""
File I/O operations for digest building.
"""

import json
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import ValidationError
from models import TwitchClip, GitHubEvent
from .ai_inserts import AIInsertsService
from .ai_client import AIClientError
from services.utils import CacheManager

logger = logging.getLogger(__name__)


class DigestIO:
    """Handle file I/O operations for digest building."""

    def __init__(self, data_dir: Path, blogs_dir: Path):
        self.data_dir = data_dir
        self.blogs_dir = blogs_dir
        self.cache = CacheManager()

    def load_twitch_clips(self, date_path: Path) -> List[TwitchClip]:
        """Load Twitch clips for a given date."""
        clips = []
        for fp in sorted(date_path.glob("twitch_clip_*.json")):
            try:
                clips.append(TwitchClip(**json.loads(fp.read_text())))
            except (json.JSONDecodeError, OSError, ValidationError) as e:
                logger.warning(f"Skipping bad Twitch clip {fp}: {e}")
        return clips

    def load_github_events(self, date_path: Path) -> List[GitHubEvent]:
        """Load GitHub events for a given date."""
        events = []
        for fp in sorted(date_path.glob("github_event_*.json")):
            try:
                events.append(GitHubEvent(**json.loads(fp.read_text())))
            except (json.JSONDecodeError, OSError, ValidationError) as e:
                logger.warning(f"Skipping bad GitHub event {fp}: {e}")
        return events

    def save_digest(self, digest: Dict[str, Any], target_date: str) -> Path:
        """Save PRE-CLEANED digest as JSON."""
        date_dir = self.blogs_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / f"PRE-CLEANED-{target_date}_digest.json"

        # Convert Pydantic models to dicts
        serializable = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in digest.items()
        }
        self.cache.atomic_write_json(path, serializable, overwrite=True)
        return path

    def save_markdown(self, date: str, markdown: str) -> Path:
        """Save markdown content to drafts/DATE.md."""
        drafts = Path("drafts")
        drafts.mkdir(exist_ok=True)
        path = drafts / f"{date}.md"
        path.write_text(markdown, encoding="utf-8")
        logger.info(f"Saved markdown to {path}")
        return path

    def enhance_with_ai(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Public method to enhance digest data with AI content.
        Idempotent: skips fields that already exist.
        
        Args:
            data: Digest data dictionary
            
        Returns:
            Enhanced digest data with AI content
        """
        try:
            # Extract date from data for AI service
            target_date = data.get("date", "")
            if not target_date:
                logger.warning("No date found in digest data, skipping AI enhancement")
                return data
            
            ai = AIInsertsService()
            return self._enhance_with_ai(target_date, data, ai)
        except (AIClientError, requests.exceptions.RequestException, ValueError, RuntimeError) as e:
            logger.exception(f"AI enhancement failed: {e}")
            return data  # Return original data on error

    def create_final_digest(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Enhance digest with AI and save FINAL version."""
        pre_path = self.blogs_dir / target_date / f"PRE-CLEANED-{target_date}_digest.json"
        if not pre_path.exists():
            logger.error(f"No PRE-CLEANED digest at {pre_path}")
            return None

        digest = json.loads(pre_path.read_text())
        
        try:
            digest = self.enhance_with_ai(digest)
            final_path = self.blogs_dir / target_date / f"FINAL-{target_date}_digest.json"
            self.cache.atomic_write_json(final_path, digest, overwrite=True)
            logger.info(f"Created FINAL digest: {final_path}")
            return digest
        except Exception as e:
            logger.exception(f"FINAL digest creation failed: {e}")
            return None

    def _enhance_with_ai(self, date: str, digest: Dict[str, Any], ai: AIInsertsService) -> Dict[str, Any]:
        """Inject AI-generated content into digest. Idempotent - skips existing fields."""
        front = digest.get("frontmatter", {})
        packets = digest.get("story_packets", [])

        story_titles = [p.get("title_human", "") for p in packets]
        inputs = {
            "title": front.get("title", ""),
            "tags_csv": ",".join(front.get("tags", [])),
            "lead": front.get("lead", ""),
            "story_titles_csv": ",".join(story_titles),
        }

        # SEO description - only if missing or placeholder
        if not front.get("description") or "[AI_GENERATE_SEO_DESCRIPTION]" in front.get("description", ""):
            desc = ai.make_seo_description(date, inputs, force_ai=True)
            if desc:
                front["description"] = desc
                front.setdefault("og", {})["og:description"] = desc

        # Holistic intro - only if missing
        if not front.get("holistic_intro"):
            holistic_intro = ai.make_holistic_intro(date, inputs, force_ai=True)
            if holistic_intro:
                front["holistic_intro"] = holistic_intro

        # Story intros - ensure ai_comprehensive_intro is populated
        enhanced_packets = []
        for p in packets:
            # Only generate if missing or empty
            if not p.get("ai_comprehensive_intro"):
                s_inputs = {
                    "title": p.get("title_human", ""),
                    "why": p.get("why", ""),
                    "highlights_csv": ",".join(p.get("highlights", [])),
                }
                intro = ai.make_story_comprehensive_intro(date, s_inputs, force_ai=True)
                if intro:
                    p["ai_comprehensive_intro"] = intro
            enhanced_packets.append(p)

        digest["frontmatter"] = front
        digest["story_packets"] = enhanced_packets

        # Update schema description if present
        if "schema" in front:
            if "blogPosting" in front["schema"]:
                # Old format: schema contains blogPosting dict
                front["schema"]["blogPosting"]["description"] = front["description"]
            else:
                # New format: schema is the BlogPosting object directly
                front["schema"]["description"] = front["description"]

        # Add related posts (Python processing, no AI needed) - only if missing
        if not digest.get("related_posts"):
            from .related import RelatedPostsService
            related_service = RelatedPostsService()
            current_tags = front.get("tags", [])
            current_title = front.get("title", "")
            
            related_posts = related_service.find_related_posts(
                current_date=date,
                current_tags=current_tags,
                current_title=current_title,
                max_posts=3
            )
            digest["related_posts"] = related_posts

        return digest

    def build_digest(self, target_date: str, kind: str = "PRE-CLEANED") -> Path:
        """
        Build a digest for a specific date and kind.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            kind: Kind of digest to build (PRE-CLEANED, FINAL, etc.)
            
        Returns:
            Path to the built digest file
        """
        # Import here to avoid circular imports
        from .blog import BlogDigestBuilder
        
        # Create BlogDigestBuilder instance
        builder = BlogDigestBuilder()
        builder.update_paths(self.data_dir, self.blogs_dir)
        
        # Build the digest
        digest = builder.build_digest(target_date)
        
        # Save it with the specified kind
        path = self.save_digest(digest, target_date, kind)
        return path

    def get_digest_path(self, target_date: str, kind: str = "PRE-CLEANED") -> Path:
        """
        Get the path for a digest file.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            kind: Kind of digest (PRE-CLEANED, FINAL, etc.)
            
        Returns:
            Path to the digest file
        """
        date_dir = self.blogs_dir / target_date
        return date_dir / f"{kind}-{target_date}_digest.json"

    def load_digest(self, path: Path) -> Dict[str, Any]:
        """
        Load digest data from a file.
        
        Args:
            path: Path to the digest file
            
        Returns:
            Digest data dictionary
        """
        if not path.exists():
            raise FileNotFoundError(f"Digest file not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_digest(self, data: Dict[str, Any], target_date: str, kind: str = "PRE-CLEANED") -> Path:
        """
        Save digest data to a file.
        
        Args:
            data: Digest data dictionary
            target_date: Date in YYYY-MM-DD format
            kind: Kind of digest (PRE-CLEANED, FINAL, etc.)
            
        Returns:
            Path to the saved digest file
        """
        date_dir = self.blogs_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / f"{kind}-{target_date}_digest.json"
        
        # Convert Pydantic models to dicts
        serializable = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in data.items()
        }
        self.cache.atomic_write_json(path, serializable, overwrite=True)
        return path
