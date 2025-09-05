"""
File I/O operations for digest building with new clean architecture.
"""

import json
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

from pydantic import ValidationError
from models import TwitchClip, GitHubEvent, Meta, RawEvents, NormalizedDigest, EnrichedDigest, PublishPackage
from .comprehensive_blog_generator import ComprehensiveBlogGenerator
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

    def save_raw_events(self, events: Dict[str, Any], target_date: str) -> Path:
        """Save Raw Events as JSON."""
        date_dir = self.data_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / "raw_events.json"
        
        # Ensure proper meta structure
        if "meta" not in events:
            events["meta"] = {"kind": "RawEvents", "version": 1, "generated_at": datetime.now().isoformat()}
        
        self.cache.atomic_write_json(path, events, overwrite=True)
        return path

    def save_normalized_digest(self, digest: Dict[str, Any], target_date: str) -> Path:
        """Save Normalized Digest as JSON."""
        date_dir = self.data_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / "digest.normalized.json"
        
        # Ensure proper meta structure
        if "meta" not in digest:
            digest["meta"] = {"kind": "NormalizedDigest", "version": 1, "generated_at": datetime.now().isoformat()}
        
        # Convert Pydantic models to dicts
        serializable = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in digest.items()
        }
        self.cache.atomic_write_json(path, serializable, overwrite=True)
        return path

    def save_enriched_digest(self, digest: Dict[str, Any], target_date: str) -> Path:
        """Save Enriched Digest as JSON."""
        date_dir = self.data_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / "digest.enriched.json"
        
        # Ensure proper meta structure
        if "meta" not in digest:
            digest["meta"] = {"kind": "EnrichedDigest", "version": 1, "generated_at": datetime.now().isoformat()}
        
        # Convert Pydantic models to dicts
        serializable = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in digest.items()
        }
        self.cache.atomic_write_json(path, serializable, overwrite=True)
        return path

    def save_publish_package(self, package: Dict[str, Any], target_date: str) -> Path:
        """Save Publish Package as JSON."""
        date_dir = self.data_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / f"{target_date}_page.publish.json"
        
        # Ensure proper meta structure (check for _meta for API v3 format)
        if "_meta" not in package and "meta" not in package:
            package["_meta"] = {"kind": "PublishPackage", "version": 1, "generated_at": datetime.now().isoformat()}
        
        # Convert Pydantic models to dicts
        serializable = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in package.items()
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

    def _validate_meta_kind(self, data: Dict[str, Any], expected_kind: str) -> None:
        """Validate that data has the expected meta kind."""
        # Support both "meta" and "_meta" keys (prefer "meta" if present)
        meta = data.get("meta") or data.get("_meta", {})
        actual_kind = meta.get("kind")
        if actual_kind != expected_kind:
            raise ValueError(f"Expected {expected_kind} but got {actual_kind}")

    def load_raw_events(self, target_date: str) -> Dict[str, Any]:
        """Load Raw Events for a date."""
        path = self.data_dir / target_date / "raw_events.json"
        if not path.exists():
            raise FileNotFoundError(f"Raw events not found: {path}")
        
        data = json.loads(path.read_text())
        self._validate_meta_kind(data, "RawEvents")
        return data

    def load_normalized_digest(self, target_date: str) -> Dict[str, Any]:
        """Load Normalized Digest for a date."""
        path = self.data_dir / target_date / "digest.normalized.json"
        if not path.exists():
            raise FileNotFoundError(f"Normalized digest not found: {path}")
        
        data = json.loads(path.read_text())
        self._validate_meta_kind(data, "NormalizedDigest")
        return data

    def load_enriched_digest(self, target_date: str) -> Dict[str, Any]:
        """Load Enriched Digest for a date."""
        path = self.data_dir / target_date / "digest.enriched.json"
        if not path.exists():
            raise FileNotFoundError(f"Enriched digest not found: {path}")
        
        data = json.loads(path.read_text())
        self._validate_meta_kind(data, "EnrichedDigest")
        return data

    def load_publish_package(self, target_date: str) -> Dict[str, Any]:
        """Load Publish Package for a date."""
        path = self.data_dir / target_date / f"{target_date}_page.publish.json"
        if not path.exists():
            raise FileNotFoundError(f"Publish package not found: {path}")
        
        data = json.loads(path.read_text())
        self._validate_meta_kind(data, "PublishPackage")
        return data

    def create_enriched_digest(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Enhance normalized digest with AI and save enriched version."""
        try:
            # Load normalized digest
            digest = self.load_normalized_digest(target_date)
            
            # Enhance with AI using ComprehensiveBlogGenerator
            generator = ComprehensiveBlogGenerator()
            ai_content = generator.generate_blog_content(
                target_date, 
                digest.get('twitch_clips', []), 
                digest.get('github_events', [])
            )
            
            # Merge AI content with original digest data
            enriched_digest = digest.copy()
            enriched_digest.update(ai_content)
            
            # Ensure the meta kind is correct for enriched digest
            enriched_digest["meta"] = {
                "kind": "EnrichedDigest",
                "version": 1,
                "generated_at": ai_content.get("meta", {}).get("generated_at", "")
            }
            
            # Save enriched digest
            self.save_enriched_digest(enriched_digest, target_date)
            logger.info(f"Created enriched digest for {target_date}")
            return enriched_digest
        except Exception as e:
            logger.exception(f"Enriched digest creation failed: {e}")
            return None

    def create_final_digest(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Create final digest with AI enhancements (alias for create_enriched_digest)."""
        return self.create_enriched_digest(target_date)



    def buildNormalizedDigest(self, target_date: str, kind: str = "normalized") -> Path:
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
        digest = builder.build_normalized_digest(target_date)
        
        # Save it with the specified kind
        path = self.save_digest(digest, target_date, kind)
        return path

    def get_digest_path(self, target_date: str, kind: str = "normalized") -> Path:
        """
        Get the path for a digest file.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            kind: Kind of digest (normalized, enriched, etc.)
            
        Returns:
            Path to the digest file
        """
        date_dir = self.data_dir / target_date
        return date_dir / f"digest.{kind}.json"

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

    def save_digest(self, data: Dict[str, Any], target_date: str, kind: str = "normalized") -> Path:
        """
        Save digest data to a file.
        
        Args:
            data: Digest data dictionary
            target_date: Date in YYYY-MM-DD format
            kind: Kind of digest (normalized, enriched, etc.)
            
        Returns:
            Path to the saved digest file
        """
        date_dir = self.data_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        path = date_dir / f"digest.{kind}.json"
        
        # Convert Pydantic models to dicts
        serializable = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in data.items()
        }
        self.cache.atomic_write_json(path, serializable, overwrite=True)
        return path
