"""
Blog digest builder service for generating daily blog posts with frontmatter.
"""

from __future__ import annotations

import html
import json
import logging
import os
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING, TypedDict
import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from models import TwitchClip, GitHubEvent
from story_schema import (
    StoryPacket, FrontmatterInfo, DigestV2, 
    make_story_packet, pair_with_clip, StoryType,
    _extract_why_and_highlights, VideoStatus
)
from services.publisher import StoryAssets

# M5: JSON-LD is handled in frontmatter via schema_data.article
import re

# Removed: JSON-LD serialization no longer needed

# Removed: JSON-LD injection no longer needed - handled in frontmatter

if TYPE_CHECKING:
    from services.utils import CacheManager

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class BlogAssets(TypedDict):
    """Type definition for blog assets structure."""
    stories: List[str]
    images: List[str]
    videos: List[str]


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
        self.worker_domain = os.getenv("WORKER_DOMAIN", "quill-blog-api.paulchrisluke.workers.dev")
    
    def build_digest(self, target_date: str) -> Dict[str, Any]:
        """
        Build a digest for a specific date with story packets (v2).
        First tries to load existing pre-cleaned digest, falls back to building from raw data.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary containing digest data, metadata, and story packets
        """
        # Validate date format early
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"target_date must be YYYY-MM-DD, got: {target_date}") from exc
        
        # First try to load existing pre-cleaned digest
        pre_cleaned_path = self.blogs_dir / target_date / f"PRE-CLEANED-{target_date}_digest.json"
        if pre_cleaned_path.exists():
            try:
                with open(pre_cleaned_path, 'r', encoding='utf-8') as f:
                    digest = json.load(f)
                logger.info(f"Loaded existing pre-cleaned digest for {target_date}")
                
                # Enhance existing digest with thumbnail URLs
                if digest.get("story_packets"):
                    enhanced_packets = self._enhance_existing_digest_with_thumbnails(digest, target_date)
                    digest["story_packets"] = enhanced_packets
                
                return digest
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load pre-cleaned digest for {target_date}: {e}")
        
        # Fall back to building from raw data
        date_path = self.data_dir / target_date
        
        if not date_path.exists():
            raise FileNotFoundError(f"No data found for date: {target_date}")
        
        # Load all data for the date
        twitch_clips = self._load_twitch_clips(date_path)
        github_events = self._load_github_events(date_path)
        
        if not twitch_clips and not github_events:
            raise FileNotFoundError(f"No data files found in {date_path} for {target_date}")
        
        # Convert to dict format for processing
        clips_data = [clip.model_dump(mode="json") for clip in twitch_clips]
        events_data = [event.model_dump(mode="json") for event in github_events]
        
        # Generate story packets from merged PRs
        story_packets = self._generate_story_packets(events_data, clips_data, target_date)
        
        # Generate pre-computed frontmatter
        frontmatter = self._generate_frontmatter_v2(target_date, clips_data, events_data, story_packets)
        
        # Enhance story packets with thumbnail URLs before serialization
        enhanced_story_packets = self._enhance_story_packets_with_thumbnails(story_packets, target_date)
        
        # Build v2 digest structure
        digest = {
            "version": "2",
            "date": target_date,
            "twitch_clips": clips_data,
            "github_events": events_data,
            "metadata": self._generate_metadata(target_date, twitch_clips, github_events),
            "frontmatter": frontmatter.model_dump(mode="json", by_alias=True),
            "story_packets": [packet.model_dump(mode="json") for packet in enhanced_story_packets]
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
    
    def generate_markdown(
        self, 
        digest: Dict[str, Any], 
        ai_enabled: bool = True,
        force_ai: bool = False,
        related_enabled: bool = True,
        jsonld_enabled: bool = True
    ) -> str:
        """
        Generate Markdown content with frontmatter from digest data.
        
        Args:
            digest: Digest data dictionary
            ai_enabled: Whether to enable AI-assisted content generation
            force_ai: Whether to ignore cache and force AI regeneration
            related_enabled: Whether to include related posts block
            jsonld_enabled: Whether to inject JSON-LD schema
            
        Returns:
            Markdown string with frontmatter
        """
        # Check if this is a v2 digest with pre-computed frontmatter
        if digest.get("version") == "2" and "frontmatter" in digest:
            # Use pre-computed frontmatter
            frontmatter_data = digest["frontmatter"]
            # Force long descriptions to be inline to prevent weird wrapping
            if "og" in frontmatter_data and "og:description" in frontmatter_data["og"]:
                desc = frontmatter_data["og"]["og:description"]
                # Only add quotes if not already quoted
                if not (desc.startswith('"') and desc.endswith('"')):
                    frontmatter_data["og"]["og:description"] = f'"{desc}"'
            if "description" in frontmatter_data:
                desc = frontmatter_data["description"]
                # Only add quotes if not already quoted
                if not (desc.startswith('"') and desc.endswith('"')):
                    frontmatter_data["description"] = f'"{desc}"'
            
            yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
            frontmatter = f"---\n{yaml_content}---\n"
        else:
            # Fall back to v1 frontmatter generation
            frontmatter = self._generate_frontmatter(digest)
        
        content = self._generate_content(digest)
        markdown = f"{frontmatter}\n\n{content}"
        
        # M5: Post-processing step for AI inserts and enhancements
        if digest.get("version") == "2":
            markdown = self._post_process_markdown(
                markdown, 
                digest, 
                ai_enabled, 
                force_ai, 
                related_enabled, 
                jsonld_enabled
            )
            
            # Regenerate frontmatter after AI modifications
            if ai_enabled:
                # Force long descriptions to be inline to prevent weird wrapping
                frontmatter_data = digest["frontmatter"].copy()
                if "og" in frontmatter_data and "og:description" in frontmatter_data["og"]:
                    desc = frontmatter_data["og"]["og:description"]
                    # Only add quotes if not already quoted
                    if not (desc.startswith('"') and desc.endswith('"')):
                        frontmatter_data["og"]["og:description"] = f'"{desc}"'
                if "description" in frontmatter_data:
                    desc = frontmatter_data["description"]
                    # Only add quotes if not already quoted
                    if not (desc.startswith('"') and desc.endswith('"')):
                        frontmatter_data["description"] = f'"{desc}"'
                
                yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
                new_frontmatter = f"---\n{yaml_content}---\n"
                # Replace the old frontmatter with the new one
                markdown = re.sub(r'^---\n.*?\n---\n', new_frontmatter, markdown, flags=re.DOTALL)
                
                # Now insert the holistic intro into the markdown body
                from .ai_inserts import AIInsertsService
                ai_service = AIInsertsService()
                story_titles = [packet.get("title_human", "") for packet in digest.get("story_packets", [])]
                inputs = {
                    "title": digest["frontmatter"].get("title", ""),
                    "tags_csv": ",".join(digest["frontmatter"].get("tags", [])),
                    "lead": digest["frontmatter"].get("lead", ""),
                    "story_titles_csv": ",".join(story_titles)
                }
                holistic_intro = ai_service.make_holistic_intro(digest["date"], inputs, force_ai)
                if holistic_intro:
                    markdown = self._insert_holistic_intro(markdown, holistic_intro)
                
                # Now insert the wrap-up
                wrap_up = ai_service.make_wrap_up(digest["date"], inputs, force_ai)
                if wrap_up:
                    markdown = self._insert_wrap_up(markdown, wrap_up)
        
        return markdown
    
    def _post_process_markdown(
        self,
        markdown: str,
        digest: Dict[str, Any],
        ai_enabled: bool,
        force_ai: bool,
        related_enabled: bool,
        jsonld_enabled: bool
    ) -> str:
        """
        M5: Post-process markdown with AI inserts and enhancements.
        
        Args:
            markdown: Raw markdown content
            digest: Digest data dictionary
            ai_enabled: Whether AI is enabled
            force_ai: Whether to force AI regeneration
            related_enabled: Whether to include related posts
            jsonld_enabled: Whether to inject JSON-LD
            
        Returns:
            Enhanced markdown content
        """
        try:
            from .ai_inserts import AIInsertsService
            from .related import RelatedPostsService
            
            target_date = digest["date"]
            frontmatter = digest["frontmatter"]
            story_packets = digest.get("story_packets", [])
            
            # 1. SEO Description (if AI enabled)
            if ai_enabled:
                ai_service = AIInsertsService()
                # Prepare inputs for AI
                story_titles = [packet.get("title_human", "") for packet in story_packets]
                inputs = {
                    "title": frontmatter.get("title", ""),
                    "tags_csv": ",".join(frontmatter.get("tags", [])),
                    "lead": frontmatter.get("lead", ""),
                    "story_titles_csv": ",".join(story_titles)
                }
                
                # Generate rich SEO description for og:description
                seo_description = ai_service.make_seo_description(target_date, inputs, force_ai)
                
                # Update frontmatter og:description
                if "og" not in frontmatter:
                    frontmatter["og"] = {}
                frontmatter["og"]["og:description"] = seo_description
                
                # Set frontmatter description
                if "description" not in frontmatter:
                    frontmatter["description"] = seo_description
                
                # Update frontmatter images with smart selection
                best_image = self._select_best_image(story_packets)
                if "og" in frontmatter:
                    frontmatter["og"]["og:image"] = best_image
                if "schema" in frontmatter and "article" in frontmatter["schema"]:
                    frontmatter["schema"]["article"]["image"] = best_image
                
                # Generate holistic intro paragraph (store for later insertion)
                holistic_intro = ai_service.make_holistic_intro(target_date, inputs, force_ai)
                
                # Generate AI-suggested tags
                suggested_tags = ai_service.suggest_tags(target_date, inputs, force_ai)
                if suggested_tags:
                    # Merge with existing tags, avoiding duplicates
                    existing_tags = set(frontmatter.get("tags", []))
                    existing_tags.update(suggested_tags)
                    frontmatter["tags"] = list(existing_tags)
                    
                    # Also update schema keywords
                    if "schema" in frontmatter and "article" in frontmatter["schema"]:
                        frontmatter["schema"]["article"]["keywords"] = list(existing_tags)
                
                # 2. Title punch-up (optional)
                current_title = frontmatter.get("title", "")
                improved_title = ai_service.punch_up_title(target_date, current_title, force_ai)
                
                if improved_title:
                    # Update frontmatter and H1
                    frontmatter["title"] = improved_title
                    # Also update og:title and headline in frontmatter
                    if "og" in frontmatter:
                        frontmatter["og"]["og:title"] = improved_title
                    if "schema" in frontmatter and "article" in frontmatter["schema"]:
                        frontmatter["schema"]["article"]["headline"] = improved_title
                    markdown = self._update_title_in_markdown(markdown, improved_title)
                
                # 3. Story micro-intros
                markdown = self._insert_story_micro_intros(markdown, story_packets, ai_service, target_date, force_ai)
                
                # 4. Insert holistic intro after all frontmatter processing
                # Store the holistic intro to insert after the markdown is fully generated
                if holistic_intro:
                    # We'll insert this after the markdown is generated, not before
                    pass
            
            # 4. Related posts block
            if related_enabled:
                related_service = RelatedPostsService()
                
                # Extract repo from GitHub events to check for related posts
                repo = None
                if digest.get("github_events"):
                    # Get the first GitHub event's repo
                    first_event = digest["github_events"][0]
                    if first_event.get("repo"):
                        repo = first_event["repo"]
                
                related_posts = related_service.find_related_posts(
                    target_date,
                    frontmatter.get("tags", []),
                    frontmatter.get("title", ""),
                    repo=repo
                )
                
                if related_posts:
                    markdown = self._append_related_posts(markdown, related_posts)
                else:
                    # Add a note when no related posts are found
                    markdown = self._append_no_related_posts(markdown)
            
            # 5. JSON-LD injection (already handled in frontmatter)
            # The schema_data.article in frontmatter provides the JSON-LD structure
            # No need to inject additional JSON-LD into the markdown body
            
            return markdown
            
        except Exception as e:
            logger.warning(f"M5 post-processing failed: {e}")
            return markdown  # Return original markdown on error
    
    def _insert_seo_description(self, markdown: str, description: str) -> str:
        """Insert SEO description as first paragraph under H1."""
        # Split markdown into lines to find H1 and insert description
        lines = markdown.splitlines()
        
        for i, line in enumerate(lines):
            if line.startswith('# ') and not line.startswith('##'):
                # Found H1, insert description after it
                lines.insert(i + 1, '')
                lines.insert(i + 2, description)
                lines.insert(i + 3, '')
                break
        
        return '\n'.join(lines)
    
    def _insert_holistic_intro(self, markdown: str, intro: str) -> str:
        """Insert holistic intro paragraph after the lead but before GitHub/Twitch stats."""
        lines = markdown.splitlines()
        
        # Find the line with "Today's development activities include..." or similar
        # This should be in the markdown body, not frontmatter
        for i, line in enumerate(lines):
            if "Today's development activities include" in line or "Twitch clips" in line or "GitHub events" in line:
                # Insert holistic intro before this line
                lines.insert(i, '')
                lines.insert(i, intro)
                lines.insert(i, '')
                break
        else:
            # If we can't find the stats line, insert after the first paragraph after H1
            for i, line in enumerate(lines):
                if line.startswith('# ') and not line.startswith('##'):
                    # Found H1, look for the next non-empty line (should be the lead)
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() and not lines[j].startswith('---'):
                            # Insert holistic intro after the lead
                            lines.insert(j + 1, '')
                            lines.insert(j + 2, intro)
                            lines.insert(j + 3, '')
                            break
                    break
        
        return '\n'.join(lines)
    
    def _update_title_in_markdown(self, markdown: str, new_title: str) -> str:
        """Update both frontmatter and H1 title."""
        # Update H1
        h1_pattern = r"^(# ).+$"
        replacement = r"\1" + new_title
        markdown = re.sub(h1_pattern, replacement, markdown, flags=re.MULTILINE)
        
        # Update og:title (exact format: 2 spaces + og:title:)
        og_title_pattern = r"^  og:title:\s*.+$"
        replacement = f"  og:title: {new_title}"
        markdown = re.sub(og_title_pattern, replacement, markdown, flags=re.MULTILINE)
        
        # Update schema.article.headline (exact format: 4 spaces + headline:)
        headline_pattern = r"^    headline:\s*.+$"
        replacement = f"    headline: {new_title}"
        markdown = re.sub(headline_pattern, replacement, markdown, flags=re.MULTILINE)
        
        return markdown
    
    def _insert_story_micro_intros(
        self, 
        markdown: str, 
        story_packets: List[Dict[str, Any]], 
        ai_service: Any, 
        target_date: str,
        force_ai: bool = False
    ) -> str:
        """Insert comprehensive story intros under each story heading."""
        for packet in story_packets:
            story_title = packet.get("title_human", "")
            if not story_title:
                continue
            
            # Find the story heading
            heading_pattern = rf"^(#### {re.escape(story_title)})$"
            
            # Prepare inputs for AI
            story_inputs = {
                "title": story_title,
                "why": packet.get("why", ""),
                "highlights_csv": ",".join(packet.get("highlights", []))
            }
            
            comprehensive_intro = ai_service.make_story_comprehensive_intro(target_date, story_inputs, force_ai)
            
            # Insert comprehensive intro after heading
            replacement = rf"\1\n\n{comprehensive_intro}\n"
            markdown = re.sub(heading_pattern, replacement, markdown, flags=re.MULTILINE)
        
        return markdown
    
    def _insert_wrap_up(self, markdown: str, wrap_up: str) -> str:
        """Insert wrap-up section before the Related posts section."""
        lines = markdown.splitlines()
        
        # Find the "Related posts" section
        for i, line in enumerate(lines):
            if line.strip() == "## Related posts":
                # Insert wrap-up section before Related posts
                # Insert in correct order: header, blank, content, blank
                lines.insert(i, "## Wrap-Up")
                lines.insert(i + 1, '')
                lines.insert(i + 2, wrap_up)
                lines.insert(i + 3, '')
                break
        else:
            # If no Related posts section, append at the end
            lines.append("")
            lines.append("## Wrap-Up")
            lines.append("")
            lines.append(wrap_up)
        
        return '\n'.join(lines)
    
    def _append_related_posts(
        self, 
        markdown: str, 
        related_posts: List[Tuple[str, str, float]]
    ) -> str:
        """Append related posts block and signature to markdown."""
        # Add related posts if available
        if related_posts:
            related_block = ["\n## Related posts\n"]
            
            for title, path, score in related_posts:
                related_block.append(f"- [{title}]({path})")
            
            related_block.append("")  # Add blank line
            markdown = markdown + "\n" + "\n".join(related_block)
        
        # Always add the signature
        signature = [
            "\n---",
            "",
            "[https://upwork.com/freelancers/paulchrisluke](https://upwork.com/freelancers/paulchrisluke)",
            "",
            "_Hi. I'm Chris. I am a morally ambiguous technology marketer. Ridiculously rich people ask me to solve problems they didn't know they have. Book me on_ [Upwork](https://upwork.com/freelancers/paulchrisluke) _like a high-class hooker or find someone who knows how to get ahold of me._"
        ]
        
        return markdown + "\n" + "\n".join(signature)
    
    def _append_no_related_posts(self, markdown: str) -> str:
        """Append a message when no related posts are found and add signature."""
        markdown = markdown + "\n\n## Related posts\n\nNo related posts found for this blog post."
        
        # Always add the signature
        signature = [
            "\n---",
            "",
            "[https://upwork.com/freelancers/paulchrisluke](https://upwork.com/freelancers/paulchrisluke)",
            "",
            "_Hi. I'm Chris. I am a morally ambiguous technology marketer. Ridiculously rich people ask me to solve problems they didn't know they have. Book me on_ [Upwork](https://upwork.com/freelancers/paulchrisluke) _like a high-class hooker or find someone who knows how to get ahold of me._"
        ]
        
        return markdown + "\n" + "\n".join(signature)
    
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
        
        # Select the best image for this blog post
        story_packets = digest.get("story_packets", [])
        best_image = self._select_best_image(story_packets)
        
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
            "image": best_image
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
            "og:image": best_image,
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
        
        # Force long descriptions to be inline to prevent weird wrapping
        if "og" in frontmatter_data and "og:description" in frontmatter_data["og"]:
            desc = frontmatter_data["og"]["og:description"]
            # Only add quotes if not already quoted
            if not (desc.startswith('"') and desc.endswith('"')):
                frontmatter_data["og"]["og:description"] = f'"{desc}"'
        if "description" in frontmatter_data:
            desc = frontmatter_data["description"]
            # Only add quotes if not already quoted
            if not (desc.startswith('"') and desc.endswith('"')):
                frontmatter_data["description"] = f'"{desc}"'
        
        # Convert to YAML
        yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
        
        return f"---\n{yaml_content}---\n"
    
    def _select_best_image(self, story_packets: List[Any]) -> str:
        """
        Select the best image for the blog post frontmatter.
        
        Priority order:
        1. First story packet with rendered video (by story type priority)
        2. Default blog image as fallback
        
        Args:
            story_packets: List of story packet dictionaries or StoryPacket objects
            
        Returns:
            URL string for the best image
        """
        if not story_packets:
            return self.blog_default_image
        
        # Priority order for story types (lower number = higher priority)
        type_priority = {
            "feat": 1,      # Features
            "fix": 2,       # Bug fixes
            "perf": 3,      # Performance
            "security": 4,  # Security
            "infra": 5,     # Infrastructure
            "docs": 6,      # Documentation
            "other": 7      # Other
        }
        
        # Find the highest priority story with rendered video
        best_story = None
        best_priority = float('inf')
        
        for packet in story_packets:
            # Handle both Dict and StoryPacket formats
            if hasattr(packet, 'video'):  # StoryPacket object
                video_status = packet.video.status if packet.video else None
                story_type = packet.story_type.value if packet.story_type else "other"
            else:  # Dict format
                video_status = packet.get("video", {}).get("status")
                story_type = packet.get("story_type", "other")
            
            if video_status == "rendered":
                priority = type_priority.get(story_type, 999)
                
                if priority < best_priority:
                    best_priority = priority
                    best_story = packet
        
        if best_story:
            # Use the video PNG intro slide as thumbnail
            if hasattr(best_story, 'video'):  # StoryPacket object
                video_path = best_story.video.path
            else:  # Dict format
                video_path = best_story["video"]["path"]
            
            # Convert video path to the correct Worker URL format
            # From: /stories/2025/08/27/story_20250827_pr34.mp4
            # To: https://quill-blog-api.paulchrisluke.workers.dev/assets/stories/2025/08/27/story_20250827_pr34_01_intro.png
            if video_path.startswith('/stories/'):
                # Extract date and filename
                parts = video_path.split('/')
                if len(parts) >= 5:
                    year = parts[2]  # 2025
                    month = parts[3]  # 08
                    day = parts[4]    # 27
                    filename = parts[5]  # story_20250827_pr34.mp4
                    
                    # Convert filename to intro PNG
                    base_name = filename.replace('.mp4', '')
                    intro_png = f"{base_name}_01_intro.png"
                    
                    # Generate Worker URL for the intro PNG
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
            
            # Fallback: try to convert existing path format
            intro_png_path = video_path.replace(".mp4", "_01_intro.png")
            if intro_png_path.startswith('/stories/'):
                return f"https://{self.worker_domain}{intro_png_path.replace('.mp4', '_01_intro.png')}"
        
        return self.blog_default_image
    
    def _get_video_thumbnail_url(self, video_path: str, story_id: str) -> str:
        """
        Generate thumbnail URL for a video based on its path.
        
        Args:
            video_path: Path to the video file
            story_id: Story identifier for fallback
            
        Returns:
            URL string for the thumbnail, or empty string if not available
        """
        try:
            # Handle different video path formats
            if video_path.startswith('out/videos/'):
                # Convert out/videos/YYYY-MM-DD/filename.mp4 to thumbnail
                parts = video_path.split('/')
                if len(parts) >= 4:
                    date_part = parts[2]  # YYYY-MM-DD
                    filename = parts[3]   # story_YYYYMMDD_prXX.mp4
                    
                    # Convert to YYYY/MM/DD format
                    date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                    year = str(date_obj.year)
                    month = f"{date_obj.month:02d}"
                    day = f"{date_obj.day:02d}"
                    
                    # Generate intro PNG thumbnail path
                    base_name = filename.replace('.mp4', '')
                    intro_png = f"{base_name}_01_intro.png"
                    
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
            
            elif video_path.startswith('stories/') or video_path.startswith('/stories/'):
                # Handle stories/YYYY/MM/DD/filename.mp4 format
                clean_path = video_path.lstrip('/')
                parts = clean_path.split('/')
                
                if len(parts) >= 4:
                    year = parts[1]   # YYYY
                    month = parts[2]  # MM
                    day = parts[3]    # DD
                    filename = parts[4]  # story_YYYYMMDD_prXX.mp4
                    
                    # Generate intro PNG thumbnail path
                    base_name = filename.replace('.mp4', '')
                    intro_png = f"{base_name}_01_intro.png"
                    
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
            
            elif video_path.startswith('https://'):
                from urllib.parse import urlsplit
                path = urlsplit(video_path).path
                if '/stories/' in path:
                    stories_index = path.find('/stories/')
                    if stories_index != -1:
                        stories_path = path[stories_index:]
                        # Convert video path to thumbnail path
                        thumbnail_path = stories_path.replace('.mp4', '_01_intro.png')
                        # Get Worker domain from environment
                        return f"https://{self.worker_domain}/assets{thumbnail_path}"
            
            # Fallback: try to generate from story_id if available
            if story_id and video_path:
                # Extract date from video path if possible
                if '/stories/' in video_path:
                    # Try to extract date from path
                    import re
                    date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', video_path)
                    if date_match:
                        year, month, day = date_match.groups()
                        
                        return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{story_id}_01_intro.png"
            
            return ""
            
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail URL for {video_path}: {e}")
            return ""
    
    def _enhance_story_packets_with_thumbnails(self, story_packets: List[Any], _target_date: str) -> List[Any]:
        """
        Enhance story packets with thumbnail URLs for API responses.
        
        Args:
            story_packets: List of StoryPacket objects
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            List of enhanced StoryPacket objects with thumbnail URLs
        """
        enhanced_packets = []
        
        for packet in story_packets:
            # Create a copy to avoid modifying the original
            enhanced_packet = packet.model_copy() if hasattr(packet, 'model_copy') else packet.copy()
            
            # Add thumbnail information to video info if video exists and is rendered
            if (hasattr(enhanced_packet, 'video') and 
                enhanced_packet.video and 
                enhanced_packet.video.path and 
                enhanced_packet.video.status == 'rendered'):
                
                # Generate thumbnail URL
                thumbnail_url = self._get_video_thumbnail_url(enhanced_packet.video.path, enhanced_packet.id)
                
                # Add thumbnail URL to video info
                if hasattr(enhanced_packet.video, 'thumbnail_url'):
                    enhanced_packet.video.thumbnail_url = thumbnail_url
                else:
                    # If VideoInfo model doesn't have thumbnail_url field, add it as a custom attribute
                    if not hasattr(enhanced_packet.video, '_custom_attrs'):
                        enhanced_packet.video._custom_attrs = {}
                    enhanced_packet.video._custom_attrs['thumbnail_url'] = thumbnail_url
            
            enhanced_packets.append(enhanced_packet)
        
        return enhanced_packets
    
    def _enhance_existing_digest_with_thumbnails(self, digest: Dict[str, Any], _target_date: str) -> List[Dict[str, Any]]:
        """
        Enhance existing digest story packets with thumbnail URLs.
        
        Args:
            digest: Existing digest dictionary
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            List of enhanced story packet dictionaries with thumbnail URLs
        """
        enhanced_packets = []
        
        for packet in digest.get("story_packets", []):
            # Create a copy to avoid modifying the original
            enhanced_packet = packet.copy()
            
            # Add thumbnail information to video info if video exists and is rendered
            if (enhanced_packet.get('video') and 
                enhanced_packet['video'].get('path') and 
                enhanced_packet['video'].get('status') == 'rendered'):
                
                # Generate thumbnail URL
                thumbnail_url = self._get_video_thumbnail_url(enhanced_packet['video']['path'], enhanced_packet.get('id', ''))
                
                # Add thumbnail URL to video info
                if thumbnail_url:
                    enhanced_packet['video']['thumbnail_url'] = thumbnail_url
            
            enhanced_packets.append(enhanced_packet)
        
        return enhanced_packets
    

    
    def _generate_content(self, digest: Dict[str, Any]) -> str:
        """Generate the main content of the blog post."""
        target_date = digest["date"]
        clips = digest["twitch_clips"]
        events = digest["github_events"]
        story_packets = digest.get("story_packets", [])
        
        content_parts = []
        
        # Add header
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        content_parts.append(f"# Daily Devlog — {date_obj.strftime('%B %d, %Y')}")
        content_parts.append("")
        
        # Add lead if available (v2 digest)
        if digest.get("version") == "2" and digest.get("frontmatter", {}).get("lead"):
            content_parts.append(digest["frontmatter"]["lead"])
            content_parts.append("")
        
        # Add summary
        content_parts.append(
            f"Today's development activities include {len(clips)} Twitch "
            f"{'clip' if len(clips)==1 else 'clips'} and {len(events)} GitHub "
            f"{'event' if len(events)==1 else 'events'}."
        )
        content_parts.append("")
        
        # Add story packets section (v2 digest)
        if story_packets:
            content_parts.append("## Stories")
            content_parts.append("")
            
            # Group by story type
            stories_by_type = {}
            for packet in story_packets:
                story_type = packet.get("story_type", "other")
                if story_type not in stories_by_type:
                    stories_by_type[story_type] = []
                stories_by_type[story_type].append(packet)
            
            # Story type display names
            type_names = {
                "feat": "New Features",
                "fix": "Bug Fixes", 
                "perf": "Performance",
                "security": "Security",
                "infra": "Infrastructure",
                "docs": "Documentation",
                "other": "Other"
            }
            
            for story_type, packets in stories_by_type.items():
                if story_type in type_names:
                    content_parts.append(f"### {type_names[story_type]}")
                    content_parts.append("")
                    
                    for packet in packets:
                        content_parts.append(f"#### {packet.get('title_human', packet.get('title_raw', 'Untitled'))}")
                        content_parts.append("")
                        
                        if packet.get('why'):
                            content_parts.append(f"**Why:** {packet['why']}")
                            content_parts.append("")
                        
                        if packet.get('highlights'):
                            content_parts.append("**Highlights:**")
                            for highlight in packet['highlights']:
                                content_parts.append(f"- {highlight}")
                            content_parts.append("")
                        
                        # Add video if available and rendered
                        if (packet.get('video', {}).get('path') and 
                            packet.get('video', {}).get('status') != 'pending'):
                            video_path = packet['video']['path']
                            
                            # Convert relative video paths to public URLs
                            if video_path.startswith('out/videos/'):
                                # Convert to public stories URL with consistent format
                                date_part = video_path.split('/')[2]  # Get date from out/videos/YYYY-MM-DD/
                                filename = video_path.split('/')[-1]  # Get filename
                                # Convert to YYYY/MM/DD format
                                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                                public_path = f"stories/{date_obj.strftime('%Y/%m/%d')}/{filename}"
                                video_path = public_path
                            
                            # Convert to Cloudflare R2 URL for API consumption
                            if video_path.startswith('stories/') or video_path.startswith('/stories/'):
                                # Remove leading slash if present
                                clean_path = video_path.lstrip('/')
                                cloudflare_url = self._get_cloudflare_url(clean_path)
                                video_path = cloudflare_url
                            
                            # Add video embed for website preview (only for secure paths)
                            if video_path.startswith(('https://', '/stories/')):
                                # Escape video path for HTML attribute to prevent XSS
                                escaped_video_path = html.escape(video_path, quote=True)
                                
                                # Generate thumbnail URL for the video
                                thumbnail_url = self._get_video_thumbnail_url(video_path, packet.get('id', ''))
                                
                                if thumbnail_url:
                                    content_parts.append(f'<video controls poster="{thumbnail_url}" src="{escaped_video_path}"></video>')
                                else:
                                    content_parts.append(f'<video controls src="{escaped_video_path}"></video>')
                                content_parts.append("")
                            else:
                                # For non-secure paths, just show the link
                                content_parts.append(f"**Video:** [Watch Story]({video_path})")
                                content_parts.append("")
                        
                        # Add PR link
                        if packet.get('links', {}).get('pr_url'):
                            content_parts.append(f"**PR:** [{packet['links']['pr_url']}]({packet['links']['pr_url']})")
                            content_parts.append("")
                        
                        content_parts.append("---")
                        content_parts.append("")
        
        # Add Twitch clips section (if not covered by stories)
        if clips and not story_packets:
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
        
        # Add GitHub events section (if not covered by stories)
        if events and not story_packets:
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
    
    def _generate_story_packets(
        self, 
        events_data: List[Dict[str, Any]], 
        clips_data: List[Dict[str, Any]],
        target_date: str
    ) -> List[StoryPacket]:
        """Generate story packets from merged PRs."""
        story_packets = []
        
        # Find merged PRs
        merged_prs = [
            event for event in events_data 
            if (event.get("type") == "PullRequestEvent" and 
                isinstance(event.get("details"), dict) and
                event["details"].get("action") == "closed" and 
                event["details"].get("merged") is True)
        ]
        
        # Deduplicate clips by ID (keep the one with transcript if available)
        unique_clips = {}
        for clip in clips_data:
            clip_id = clip["id"]
            if clip_id not in unique_clips:
                unique_clips[clip_id] = clip
            elif clip.get("transcript") and not unique_clips[clip_id].get("transcript"):
                # Prefer clips with transcripts
                unique_clips[clip_id] = clip
        
        deduplicated_clips = list(unique_clips.values())
        
        # Group PRs by similar titles to handle deduplication
        pr_groups = {}
        for pr_event in merged_prs:
            title = pr_event.get("title", "").lower()
            # Group by base title (remove PR number, etc.)
            base_title = title.replace("feature/", "").replace("fix/", "").replace("security/", "").strip()
            if base_title not in pr_groups:
                pr_groups[base_title] = []
            pr_groups[base_title].append(pr_event)
        
        # Generate story packets with deduplication
        for pr_events in pr_groups.values():
            if len(pr_events) == 1:
                # Single PR, create normal story packet
                pr_event = pr_events[0]
                pairing = pair_with_clip(pr_event, deduplicated_clips)
                packet = make_story_packet(pr_event, pairing, deduplicated_clips)
                
                # Check for existing video file
                video_path = self._find_video_for_story(packet, target_date)
                if video_path:
                    packet.video.path = video_path
                    packet.video.status = VideoStatus.RENDERED
                
                story_packets.append(packet)
            else:
                # Multiple PRs with similar titles - merge into one story
                # Use the first PR as the base, merge highlights from others
                base_pr = pr_events[0]
                pairing = pair_with_clip(base_pr, deduplicated_clips)
                packet = make_story_packet(base_pr, pairing, deduplicated_clips)
                
                # Merge highlights from other PRs
                all_highlights = packet.highlights.copy()
                for other_pr in pr_events[1:]:
                    extractor_result = _extract_why_and_highlights(other_pr)
                    if not extractor_result:
                        continue
                    
                    other_why, other_highlights = extractor_result
                    if other_highlights:
                        all_highlights.extend(other_highlights)
                
                # Deduplicate and limit highlights
                unique_highlights = []
                for highlight in all_highlights:
                    if highlight not in unique_highlights and len(highlight) > 5:
                        unique_highlights.append(highlight)
                
                packet.highlights = unique_highlights[:4]  # Max 4 highlights
                
                # Check for existing video file
                video_path = self._find_video_for_story(packet, target_date)
                if video_path:
                    packet.video.path = video_path
                    packet.video.status = VideoStatus.RENDERED
                
                story_packets.append(packet)
        
        return story_packets
    
    def _find_video_for_story(self, packet: StoryPacket, target_date: str) -> Optional[str]:
        """Find existing video file for a story packet."""
        # Check for video file in the expected location
        video_dir = Path("out/videos") / target_date
        if not video_dir.exists():
            return None
        
        # Look for video file matching the story ID
        story_id = packet.id
        video_file = video_dir / f"{story_id}.mp4"
        
        if video_file.exists():
            return str(video_file)
        
        # Fallback: look for video file by PR number
        pr_number = packet.pr_number
        video_file = video_dir / f"story_{target_date.replace('-', '')}_pr{pr_number}.mp4"
        
        if video_file.exists():
            return str(video_file)
        
        return None
    
    def _generate_frontmatter_v2(
        self, 
        target_date: str, 
        clips_data: List[Dict[str, Any]], 
        events_data: List[Dict[str, Any]], 
        story_packets: List[StoryPacket]
    ) -> FrontmatterInfo:
        """Generate v2 frontmatter with story packet information."""
        # Parse date
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Generate title
        title = f"Daily Devlog — {date_obj.strftime('%b %d, %Y')}"
        
        # Extract story types for tags
        story_types = [packet.story_type.value for packet in story_packets]
        unique_types = list(set(story_types))
        
        # Generate lead based on story packets
        lead = self._generate_lead(story_packets)
        
        # Select the best image for this blog post
        best_image = self._select_best_image(story_packets)
        
        # Build Open Graph metadata
        og_metadata = {
            "og:title": title,
            "og:description": (
                f"Daily development log with {len(story_packets)} "
                f"{'story' if len(story_packets)==1 else 'stories'} from "
                f"{len(clips_data)} Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.blog_base_url}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Build schema.org metadata
        schema_metadata = {
            "article": {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": title,
                "datePublished": target_date,
                "author": {
                    "@type": "Person",
                    "name": self.blog_author
                },
                "keywords": unique_types,
                "url": f"{self.blog_base_url}/blog/{target_date}",
                "image": best_image
            }
        }
        
        return FrontmatterInfo(
            title=title,
            date=target_date,
            author=self.blog_author,
            og=og_metadata,
            schema=schema_metadata,
            tags=unique_types,
            lead=lead
        )
    
    def _generate_lead(self, story_packets: List[StoryPacket]) -> Optional[str]:
        """Generate a lead paragraph from story packets."""
        if not story_packets:
            return None
        
        # Count story types
        type_counts = {}
        for packet in story_packets:
            story_type = packet.story_type.value
            type_counts[story_type] = type_counts.get(story_type, 0) + 1
        
        # Generate lead based on most common types
        if len(story_packets) == 1:
            packet = story_packets[0]
            return f"Today's development work focused on {packet.title_human.lower()}."
        
        # Multiple stories
        total_stories = len(story_packets)
        if type_counts.get("feat", 0) > 0 and type_counts.get("security", 0) > 0:
            return f"Shipped {type_counts['feat']} new feature{'s' if type_counts['feat'] > 1 else ''} and enhanced security today."
        elif type_counts.get("feat", 0) > 0:
            return f"Shipped {type_counts['feat']} new feature{'s' if type_counts['feat'] > 1 else ''} today."
        elif type_counts.get("fix", 0) > 0:
            return f"Fixed {type_counts['fix']} issue{'s' if type_counts['fix'] > 1 else ''} and improved the codebase."
        elif type_counts.get("security", 0) > 0:
            return f"Enhanced security with {type_counts['security']} improvement{'s' if type_counts['security'] > 1 else ''}."
        else:
            return f"Completed {total_stories} development task{'s' if total_stories > 1 else ''} today."
    
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
    

    
    def _generate_frontmatter_v3(
        self, 
        target_date: str, 
        clips_data: List[Dict[str, Any]], 
        events_data: List[Dict[str, Any]], 
        story_packets: List[StoryPacket]
    ) -> FrontmatterInfo:
        """
        Generate v3 frontmatter that matches the exact requirements specification.
        
        This generates the exact frontmatter structure needed for working blog posts
        with proper assets and links.
        """
        # Parse date
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Generate title
        title = f"Daily Devlog — {date_obj.strftime('%B %d, %Y')}"
        
        # Extract story types for tags
        story_types = [packet.story_type.value for packet in story_packets]
        unique_types = list(set(story_types))
        
        # Generate lead based on story packets
        lead = self._generate_lead(story_packets)
        
        # Select the best image for this blog post
        best_image = self._select_best_image(story_packets)
        
        # Build Open Graph metadata with correct asset paths
        og_metadata = {
            "og:title": title,
            "og:description": (
                f"Daily development log with {len(story_packets)} "
                f"{'story' if len(story_packets)==1 else 'stories'} from "
                f"{len(clips_data)} Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.blog_base_url}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Build schema.org metadata with correct asset paths
        schema_metadata = {
            "article": {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": title,
                "datePublished": target_date,
                "author": {
                    "@type": "Person",
                    "name": self.blog_author
                },
                "keywords": unique_types,
                "url": f"{self.blog_base_url}/blog/{target_date}",
                "image": best_image
            }
        }
        
        return FrontmatterInfo(
            title=title,
            date=target_date,
            author=self.blog_author,
            og=og_metadata,
            schema=schema_metadata,
            tags=unique_types,
            lead=lead
        )
    
    def get_blog_api_data(self, target_date: str) -> Dict[str, Any]:
        """
        Get complete blog data for API consumption with Cloudflare URLs.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary containing complete blog data for API
        """
        try:
            # Build the digest
            digest = self.build_digest(target_date)
            
            # Update story packets with Cloudflare URLs
            updated_story_packets = []
            for story in digest.get("story_packets", []):
                updated_story = story.copy()
                
                # Update video path to Cloudflare URL - handle all local asset patterns
                if story.get("video", {}).get("path"):
                    video_path = story["video"]["path"]
                    # Convert any local path (stories/, out/videos/, relative paths without http)
                    if not video_path.startswith('http'):
                        clean_path = video_path.lstrip('/')
                        cloudflare_url = self._get_cloudflare_url(clean_path)
                        updated_story["video"]["path"] = cloudflare_url
                
                updated_story_packets.append(updated_story)
            
            # Create updated digest with Cloudflare URLs for markdown generation
            updated_digest = digest.copy()
            updated_digest["story_packets"] = updated_story_packets
            
            # Regenerate markdown with updated digest (so video URLs are Cloudflare URLs)
            markdown = self.generate_markdown(updated_digest)
            
            # Get assets
            assets = self.get_blog_assets(target_date)
            
            # Build the complete final blog structure
            final_blog_data = {
                "date": target_date,
                "version": "2",
                "twitch_clips": digest.get("twitch_clips", []),
                "github_events": digest.get("github_events", []),
                "metadata": digest.get("metadata", {}),
                "frontmatter": updated_digest.get("frontmatter", {}),  # Use updated digest frontmatter
                "story_packets": updated_story_packets,
                "markdown": markdown,
                "assets": assets,
                "api_metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),  # UTC timestamp
                    "version": "1.0",
                    "api_endpoint": f"/api/blog/{target_date}"
                }
            }
            
            return final_blog_data
            
        except Exception as e:
            logger.exception(f"Failed to get blog API data for {target_date}")  # Log full traceback
            raise
    
    def get_blog_markdown(self, target_date: str) -> str:
        """
        Get raw markdown content for a date.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Raw markdown content as string
        """
        # Check if markdown exists in drafts
        draft_path = Path("drafts") / f"{target_date}.md"
        if draft_path.exists():
            with open(draft_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        # If no draft exists, generate it
        try:
            digest = self.build_digest(target_date)
            markdown = self.generate_markdown(digest)
            return markdown
        except Exception as e:
            logger.exception(f"Failed to generate markdown for {target_date}")
            raise
    
    def get_blog_assets(self, target_date: str) -> BlogAssets:
        """
        Get all assets for a blog post with Cloudflare R2 URLs.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            BlogAssets object with stories, images, and videos
        """
        assets = {
            "stories": [],
            "images": [],
            "videos": []
        }
        
        try:
            # Get story assets from story_packets
            digest = self.build_digest(target_date)
            for story in digest.get("story_packets", []):
                story_id = story.get("id")
                if story_id:
                    story_assets = self._get_story_assets(target_date, story_id)
                    if story_assets:
                        assets["stories"].append(story_id)
                        # Add images and videos from story assets
                        assets["images"].extend(story_assets.get("images", []))
                        if story_assets.get("video"):
                            assets["videos"].append(story_assets["video"])
                        assets["images"].extend(story_assets.get("highlights", []))
            
            # Convert to Cloudflare R2 URLs
            cloudflare_assets = {
                "stories": assets["stories"],
                "images": [self._get_cloudflare_url(path) for path in assets["images"]],
                "videos": [self._get_cloudflare_url(path) for path in assets["videos"]]
            }
            
            return BlogAssets(**cloudflare_assets)
            
        except Exception as e:
            logger.exception(f"Failed to get blog assets for {target_date}")
            raise
    
    def _get_story_assets(self, target_date: str, story_id: str) -> StoryAssets:
        """
        Get assets for a specific story.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            story_id: Story identifier
            
        Returns:
            StoryAssets object with video, images, and highlights
        """
        story_assets = {
            "images": [],
            "video": None,
            "highlights": []
        }
        
        try:
            # Check for story assets in public directory
            # Assets are stored directly in the date directory, not in story subdirectories
            date_path = Path("public/stories") / target_date.replace("-", "/")
            if date_path.exists():
                for asset_file in date_path.iterdir():
                    if asset_file.is_file() and asset_file.name.startswith(story_id):
                        rel_path = str(asset_file.relative_to(Path("public")))
                        if asset_file.name.endswith('.mp4'):
                            story_assets["video"] = rel_path
                        elif asset_file.name.endswith('.png'):
                            if 'hl_' in asset_file.name:
                                story_assets["highlights"].append(rel_path)
                            else:
                                story_assets["images"].append(rel_path)
            
            return StoryAssets(**story_assets)
            
        except Exception as e:
            logger.exception("Failed to get story assets for %s", story_id)
            return StoryAssets(video=None, images=[], highlights=[])
    
    def _get_cloudflare_url(self, asset_path: str) -> str:
        """
        Convert local asset path to Worker API URL.
        
        Args:
            asset_path: Local asset path (e.g., "stories/2025/08/29/story_123.mp4")
            
        Returns:
            Full Worker API URL for the asset
        """
        try:
            # Convert the asset path to the Worker's asset format
            # Local path: stories/2025/08/29/story_123.mp4
            # Worker path: /assets/stories/2025/08/29/story_123.mp4
            worker_path = f"/assets/{asset_path}"
            
            return f"https://{self.worker_domain}{worker_path}"
                
        except Exception as e:
            logger.exception("Failed to generate Worker URL for %s", asset_path)
            return f"/{asset_path}"
