"""
File I/O operations for digest building.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from models import TwitchClip, GitHubEvent

logger = logging.getLogger(__name__)


class DigestIO:
    """Handle file I/O operations for digest building."""
    
    def __init__(self, data_dir: Path, blogs_dir: Path):
        self.data_dir = data_dir
        self.blogs_dir = blogs_dir
    
    def load_twitch_clips(self, date_path: Path) -> List[TwitchClip]:
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
    
    def load_github_events(self, date_path: Path) -> List[GitHubEvent]:
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
    
    def save_digest(self, digest: Dict[str, Any], target_date: str, *, cache_manager=None) -> Path:
        """
        Save digest as JSON file for AI ingestion.
        
        Args:
            digest: Digest data dictionary
            target_date: Date in YYYY-MM-DD format
            cache_manager: Optional cache manager instance (defaults to new instance)
            
        Returns:
            Path to the saved JSON file
        """
        # Create date subdirectory
        date_dir = self.blogs_dir / target_date
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON digest using atomic write
        json_path = date_dir / f"PRE-CLEANED-{target_date}_digest.json"
        if json_path.exists():
            logger.info("Overwriting existing digest: %s", json_path)
        
        # Ensure all data is JSON-serializable by converting to dict first
        serializable_digest = {}
        for key, value in digest.items():
            if hasattr(value, 'model_dump'):
                # Handle Pydantic models
                serializable_digest[key] = value.model_dump(mode='json')
            else:
                serializable_digest[key] = value
        
        # Save JSON directly to ensure proper serialization
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_digest, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Direct JSON save failed: {e}, falling back to cache manager")
            # Fall back to cache manager
            if cache_manager is None:
                from services.utils import CacheManager
                cache_manager = CacheManager()
            cache_manager.atomic_write_json(json_path, serializable_digest, overwrite=True)
        
        return json_path
    
    def save_markdown(self, date: str, markdown: str) -> Path:
        """
        Save markdown content to drafts directory.
        
        Args:
            date: Date in YYYY-MM-DD format
            markdown: Markdown content to save
            
        Returns:
            Path to the saved markdown file
        """
        # Create drafts directory if it doesn't exist
        drafts_dir = Path("drafts")
        drafts_dir.mkdir(exist_ok=True)
        
        # Save markdown file
        file_path = drafts_dir / f"{date}.md"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        logger.info(f"Saved markdown to {file_path}")
        return file_path
    
    def create_final_digest(self, target_date: str) -> Optional[Dict[str, Any]]:
        """
        Create FINAL version of digest with AI enhancements for API consumption.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Enhanced digest dictionary or None if failed
        """
        try:
            # Load the PRE-CLEANED digest
            pre_cleaned_path = self.blogs_dir / target_date / f"PRE-CLEANED-{target_date}_digest.json"
            if not pre_cleaned_path.exists():
                logger.error(f"PRE-CLEANED digest not found: {pre_cleaned_path}")
                return None
            
            with open(pre_cleaned_path, 'r') as f:
                digest = json.load(f)
            
            # Apply AI enhancements
            from .ai_inserts import AIInsertsService
            ai_service = AIInsertsService()
            
            # Enhance digest with AI content
            enhanced_digest = self._enhance_digest_with_ai(digest, ai_service)
            
            # Save as FINAL version
            final_path = self.blogs_dir / target_date / f"FINAL-{target_date}_digest.json"
            with open(final_path, 'w') as f:
                json.dump(enhanced_digest, f, indent=2, default=str)
            
            logger.info(f"Created FINAL digest: {final_path}")
            return enhanced_digest
            
        except Exception as e:
            logger.error(f"Failed to create FINAL digest: {e}")
            return None
    
    def _enhance_digest_with_ai(self, digest: Dict[str, Any], ai_service) -> Dict[str, Any]:
        """Enhance digest with AI-generated content."""
        try:
            target_date = digest["date"]
            frontmatter = digest["frontmatter"]
            story_packets = digest.get("story_packets", [])
            
            # Prepare inputs for AI
            story_titles = [packet.get("title_human", "") for packet in story_packets]
            inputs = {
                "title": frontmatter.get("title", ""),
                "tags_csv": ",".join(frontmatter.get("tags", [])),
                "lead": frontmatter.get("lead", ""),
                "story_titles_csv": ",".join(story_titles)
            }
            
            # Generate rich SEO description for og:description
            logger.info(f"Generating SEO description for {target_date}...")
            seo_description = ai_service.make_seo_description(target_date, inputs, force_ai=False)
            logger.info(f"Generated SEO description: {seo_description[:100]}...")
            
            # Update frontmatter og:description
            if "og" not in frontmatter:
                frontmatter["og"] = {}
            frontmatter["og"]["og:description"] = seo_description
            logger.info(f"Updated og:description in frontmatter")
            
            # Set frontmatter description
            if "description" not in frontmatter:
                frontmatter["description"] = seo_description
            logger.info(f"Set description in frontmatter")
            
            # Generate holistic intro paragraph
            holistic_intro = ai_service.make_holistic_intro(target_date, inputs, force_ai=False)
            if holistic_intro:
                frontmatter["holistic_intro"] = holistic_intro
            
            # Generate wrap-up paragraph
            wrap_up = ai_service.make_wrap_up(target_date, inputs, force_ai=False)
            if wrap_up:
                frontmatter["wrap_up"] = wrap_up
            
            # Generate AI-suggested tags
            suggested_tags = ai_service.suggest_tags(target_date, inputs, force_ai=False)
            if suggested_tags:
                # Merge with existing tags, avoiding duplicates
                existing_tags = set(frontmatter.get("tags", []))
                existing_tags.update(suggested_tags)
                frontmatter["tags"] = list(existing_tags)
                
                # Also update schema keywords
                if "schema" in frontmatter and "article" in frontmatter["schema"]:
                    frontmatter["schema"]["article"]["keywords"] = list(existing_tags)
            
            # Enhance story packets with AI-generated content
            enhanced_story_packets = []
            for packet in story_packets:
                enhanced_packet = packet.copy()
                
                # Generate story micro-intro
                story_inputs = {
                    "title": packet.get("title_human", ""),
                    "why": packet.get("why", ""),
                    "highlights_csv": ",".join(packet.get("highlights", []))
                }
                micro_intro = ai_service.make_story_micro_intro(target_date, story_inputs, force_ai=False)
                if micro_intro:
                    enhanced_packet["ai_micro_intro"] = micro_intro
                
                # Generate comprehensive story intro
                comprehensive_intro = ai_service.make_story_comprehensive_intro(target_date, story_inputs, force_ai=False)
                if comprehensive_intro:
                    enhanced_packet["ai_comprehensive_intro"] = comprehensive_intro
                
                enhanced_story_packets.append(enhanced_packet)
            
            # Update digest with enhanced content
            digest["frontmatter"] = frontmatter
            digest["story_packets"] = enhanced_story_packets
            
            logger.info(f"Enhanced digest for {target_date} with AI-generated content")
            logger.info(f"Added holistic_intro: {'holistic_intro' in frontmatter}")
            logger.info(f"Added wrap_up: {'wrap_up' in frontmatter}")
            logger.info(f"Enhanced {len(enhanced_story_packets)} story packets with AI content")
            
        except Exception as e:
            logger.warning(f"Failed to enhance digest with AI content: {e}")
            logger.warning(f"Exception details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.warning(f"Traceback: {traceback.format_exc()}")
            # Continue without AI enhancement - digest is still valid
        
        return digest
