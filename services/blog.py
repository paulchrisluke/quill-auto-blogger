"""
Blog digest builder service for generating daily blog posts with frontmatter.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import hashlib
import re
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING, TypedDict
from html import unescape
import yaml
from dotenv import load_dotenv

from models import TwitchClip, GitHubEvent

class DateEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle date and datetime objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)
from story_schema import (
    StoryPacket, FrontmatterInfo, 
    make_story_packet, pair_with_clip,
    _extract_why_and_highlights, VideoStatus
)
from services.publisher import StoryAssets
from .content_generator import ContentGenerator

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
        self.blog_default_image = "https://media.paulchrisluke.com/assets/pcl-labs-logo.svg"
        self.worker_domain = os.getenv("WORKER_DOMAIN", "https://quill-blog-api-prod.paulchrisluke.workers.dev")
        self.media_domain = os.getenv("MEDIA_DOMAIN", "https://media.paulchrisluke.com")
        
        # Blog signature configuration
        self.signature_enabled = os.getenv("BLOG_SIGNATURE_ENABLED", "false").lower() == "true"
        self.signature_text = os.getenv("BLOG_SIGNATURE_TEXT", "")
        
        # Initialize extracted services
        from .digest_utils import DigestUtils
        from .digest_io import DigestIO
        from .frontmatter_generator import FrontmatterGenerator
        from .related import RelatedPostsService
        
        self.utils = DigestUtils(self.media_domain, self.blog_default_image)
        self.io = DigestIO(self.data_dir, self.blogs_dir)
        self.frontmatter_gen = FrontmatterGenerator(self.blog_author, self.blog_base_url, self.media_domain)
        self.related_service = RelatedPostsService()
    
    def update_paths(self, data_dir: Path, blogs_dir: Path):
        """Update data and blogs directories and recreate DigestIO instance."""
        self.data_dir = data_dir
        self.blogs_dir = blogs_dir
        self.blogs_dir.mkdir(parents=True, exist_ok=True)
        
        # Recreate DigestIO instance with new paths
        from .digest_io import DigestIO
        self.io = DigestIO(self.data_dir, self.blogs_dir)
    
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
        
        # First try to load existing FINAL digest (has AI-enhanced content)
        final_digest_path = self.blogs_dir / target_date / f"FINAL-{target_date}_digest.json"
        if final_digest_path.exists():
            try:
                with open(final_digest_path, 'r', encoding='utf-8') as f:
                    digest = json.load(f)
                logger.info(f"Loaded existing FINAL digest for {target_date}")
                
                # Check if digest has enhanced schema.org
                if "frontmatter" in digest and digest.get("frontmatter", {}).get("schema", {}).get("blogPosting"):
                    logger.info(f"Loaded existing FINAL digest with enhanced schema for {target_date}")
                    
                    # Enhance existing digest with thumbnail URLs
                    if digest.get("story_packets"):
                        enhanced_packets = self.utils.enhance_existing_digest_with_thumbnails(digest, target_date)
                        digest["story_packets"] = enhanced_packets
                    
                    return digest
                else:
                    logger.info(f"Existing FINAL digest for {target_date} missing enhanced schema, rebuilding...")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load FINAL digest for {target_date}: {e}")
        
        # Then try to load existing pre-cleaned digest
        pre_cleaned_path = self.blogs_dir / target_date / f"PRE-CLEANED-{target_date}_digest.json"
        if pre_cleaned_path.exists():
            try:
                with open(pre_cleaned_path, 'r', encoding='utf-8') as f:
                    digest = json.load(f)
                logger.info(f"Loaded existing pre-cleaned digest for {target_date}")
                
                # Check if digest has enhanced schema.org
                if "frontmatter" in digest and digest.get("frontmatter", {}).get("schema", {}).get("blogPosting"):
                    logger.info(f"Found existing digest with enhanced schema for {target_date}")
                    
                    # Enhance existing digest with thumbnail URLs
                    if digest.get("story_packets"):
                        enhanced_packets = self.utils.enhance_existing_digest_with_thumbnails(digest, target_date)
                        digest["story_packets"] = enhanced_packets
                    
                    return digest
                else:
                    logger.info(f"Existing digest for {target_date} missing enhanced schema, rebuilding...")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load pre-cleaned digest for {target_date}: {e}")
        
        # Fall back to building from raw data
        date_path = self.data_dir / target_date
        
        if not date_path.exists():
            raise FileNotFoundError(f"No data found for date: {target_date}")
        
        # Load all data for the date
        twitch_clips = self.io.load_twitch_clips(date_path)
        github_events = self.io.load_github_events(date_path)
        
        if not twitch_clips and not github_events:
            raise FileNotFoundError(f"No data files found in {date_path} for {target_date}")
        
        # Convert to dict format for processing
        clips_data = [clip.model_dump(mode="json") for clip in twitch_clips]
        events_data = [event.model_dump(mode="json") for event in github_events]
        
        # Generate story packets from merged PRs
        story_packets = self._generate_story_packets(events_data, clips_data, target_date)
        
        # Generate clean frontmatter with enhanced schema.org
        frontmatter = self.frontmatter_gen.generate(
            target_date, clips_data, events_data, story_packets
        )
        
        # Enhance story packets with thumbnail URLs before serialization
        enhanced_story_packets = self.utils.enhance_story_packets_with_thumbnail_urls(story_packets, target_date)
        
        # Build clean digest structure with enhanced schema.org
        digest = {
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
                if not (desc.startswith('"') and desc.endswith('"')):
                    frontmatter_data["og"]["og:description"] = f'"{desc}"'
            if "description" in frontmatter_data:
                desc = frontmatter_data["description"]
                if not (desc.startswith('"') and desc.endswith('"')):
                    frontmatter_data["description"] = f'"{desc}"'
            
            yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
            frontmatter = f"---\n{yaml_content}---\n"
        else:
            # Fall back to clean frontmatter generation
            frontmatter = self._generate_clean_frontmatter(digest)
        
        # Generate content using ContentGenerator
        content_gen = ContentGenerator(digest, self.utils)
        content = content_gen.generate(ai_enabled, force_ai, related_enabled)
        
        # Post-process markdown if AI is enabled
        if ai_enabled and digest.get("version") == "2":
            # Regenerate frontmatter after AI modifications using updated frontmatter
            frontmatter_data = content_gen.frontmatter.copy()
            if "og" in frontmatter_data and "og:description" in frontmatter_data["og"]:
                desc = frontmatter_data["og"]["og:description"]
                if not (desc.startswith('"') and desc.endswith('"')):
                    frontmatter_data["og"]["og:description"] = f'"{desc}"'
            if "description" in frontmatter_data:
                desc = frontmatter_data["description"]
                if not (desc.startswith('"') and desc.endswith('"')):
                    frontmatter_data["description"] = f'"{desc}"'
            
            yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
            frontmatter = f"---\n{yaml_content}---\n"
        
        return f"{frontmatter}\n\n{content}"
    
    def save_digest(self, digest: Dict[str, Any], *, cache_manager: Optional[CacheManager] = None) -> Path:
        """Save digest as JSON file for AI ingestion."""
        return self.io.save_digest(digest, digest["date"])
    
    def save_markdown(self, date: str, markdown: str) -> Path:
        """Save markdown content to drafts directory."""
        return self.io.save_markdown(date, markdown)
    
    def create_final_digest(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Create FINAL version of digest with AI enhancements for API consumption."""
        return self.io.create_final_digest(target_date)
    

    

    
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
            "date_parsed": target_date
        }
    
    def _generate_clean_frontmatter(self, digest: Dict[str, Any]) -> str:
        """Generate clean frontmatter with schema.org metadata."""
        frontmatter_info = self.frontmatter_gen.generate(
            digest["date"], 
            digest["twitch_clips"], 
            digest["github_events"],
            digest.get("story_packets", [])
        )
        # Convert FrontmatterInfo to YAML string
        frontmatter_data = frontmatter_info.model_dump(mode="json", by_alias=True)
        yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
        return f"---\n{yaml_content}---\n"
    
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
                
                # Check for existing video file or render if needed
                video_path = self._find_video_for_story(packet, target_date)
                if video_path:
                    packet.video.path = video_path
                    packet.video.status = VideoStatus.RENDERED
                else:
                    # Render video if it doesn't exist
                    try:
                        video_path = self._render_video_for_packet(packet, target_date)
                        if video_path:
                            packet.video.path = video_path
                            packet.video.status = VideoStatus.RENDERED
                    except Exception as e:
                        logger.exception("Failed to render video for %s", packet.id)
                        packet.video.status = VideoStatus.FAILED
                        packet.video.error = str(e)
                
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
                
                # Check for existing video file or render if needed
                video_path = self._find_video_for_story(packet, target_date)
                if video_path:
                    packet.video.path = video_path
                    packet.video.status = VideoStatus.RENDERED
                else:
                    # Render video if it doesn't exist
                    try:
                        video_path = self._render_video_for_packet(packet, target_date)
                        if video_path:
                            packet.video.path = video_path
                            packet.video.status = VideoStatus.RENDERED
                    except Exception as e:
                        logger.exception("Failed to render video for %s", packet.id)
                        packet.video.status = VideoStatus.FAILED
                        packet.video.error = str(e)
                
                story_packets.append(packet)
        
        return story_packets
    
    def _render_video_for_packet(self, packet: StoryPacket, target_date: str) -> Optional[str]:
        """Render video for a story packet if it doesn't exist."""
        try:
            from tools.renderer_html import render_for_packet
            
            # Create output directory for videos
            out_dir = Path("out/videos") / target_date
            out_dir.mkdir(parents=True, exist_ok=True)
            
            # Convert packet to dict format for renderer
            packet_dict = packet.model_dump(mode="json")
            
            # Render the video
            video_path = render_for_packet(packet_dict, out_dir)
            
            # Get video duration
            from tools.renderer_html import get_video_duration
            duration = get_video_duration(Path(video_path))
            
            # Update packet with video info
            packet.video.duration_s = duration if duration > 0 else None
            packet.video.canvas = "1920x1080"  # Default canvas size
            
            logger.info(f"Rendered video for {packet.id}: {video_path}")
            return video_path
            
        except Exception as e:
            logger.error(f"Failed to render video for {packet.id}: {e}")
            raise
    
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
    
    def get_blog_api_data(self, target_date: str) -> Dict[str, Any]:
        """Get complete blog data for API consumption following the correct order of operations."""
        try:
            # Step 1: Ensure FINAL digest exists (AI-enhanced)
            final_path = self.io.get_digest_path(target_date, kind="FINAL")
            
            if not final_path.exists():
                logger.info(f"FINAL digest not found, building it from PRE-CLEANED: {final_path}")
                
                # Build raw digest first
                pre_path = self.io.build_digest(target_date, kind="PRE-CLEANED")
                data = self.io.load_digest(pre_path)
                
                # Enhance with AI (blog + stories)
                data = self.io.enhance_with_ai(data)
                
                # Normalize assets (videos/thumbnails → CDN)
                content_gen = ContentGenerator(data, self.utils)
                data = content_gen.normalize_assets(data)
                
                # Save FINAL digest
                self.io.save_digest(data, target_date, kind="FINAL")
                logger.info(f"Created FINAL digest with AI enhancements: {final_path}")
            else:
                logger.info(f"Loading existing FINAL digest: {final_path}")
                data = self.io.load_digest(final_path)
            
            # Step 2: Generate content with AI enhancements
            content_gen = ContentGenerator(data, self.utils)
            consolidated_content = content_gen.generate(ai_enabled=True, related_enabled=True)
            
            # Step 3: Apply final SEO polish (slug + canonical + meta coherence)
            final_blog_data = self._apply_final_seo_polish(data, target_date, consolidated_content)
            
            # Step 4: Build API-v3 payload
            api_data = self._build_api_v3(final_blog_data, target_date, consolidated_content, content_gen.frontmatter)
            
            # Step 5: Save and upload
            self._save_v3_api_response(target_date, api_data)
            self._upload_to_r2(target_date, api_data)
            
            return api_data
            
        except Exception as e:
            logger.exception("Failed to get blog API data for %s", target_date)
            raise

    def _apply_final_seo_polish(self, data: Dict[str, Any], target_date: str, content: str) -> Dict[str, Any]:
        """
        Apply final SEO polish to blog data after all other processing is complete.
        This runs LAST and ensures canonical coherence, word count, and metadata consistency.
        """
        # Create a copy to avoid modifying the original
        polished_data = data.copy()
        frontmatter = polished_data.get("frontmatter", {})
        
        # 1. Generate slug from title and build canonical URL
        title = frontmatter.get("title", "")
        if title:
            slug = self._generate_slug(title)
            canonical = f"https://paulchrisluke.com/blog/{target_date.replace('-', '/')}/{slug}/"
            
            # Mirror canonical to all required fields
            polished_data["url"] = canonical
            polished_data.setdefault("seo_meta", {})["canonical"] = canonical
            
            # Mirror to frontmatter fields
            if frontmatter.get("og"):
                frontmatter["og"]["og:url"] = canonical
            if frontmatter.get("schema"):
                frontmatter["schema"]["url"] = canonical
        
        # 2. Calculate word count and reading time
        word_count = self._word_count(content)
        reading_time = self._read_time_minutes(word_count)
        
        polished_data["wordCount"] = word_count
        polished_data["timeRequired"] = f"PT{reading_time}M"
        
        # Update schema with word count
        if frontmatter.get("schema"):
            frontmatter["schema"]["wordCount"] = word_count
        
        # 3. Ensure all images are absolute URLs
        self._ensure_absolute_images(polished_data)
        
        # 4. Clean up any remaining AI placeholders
        self._clean_ai_placeholders(polished_data, content)
        
        return polished_data

    def _build_api_v3(self, data: Dict[str, Any], target_date: str, content: str, content_gen_frontmatter: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build the final API-v3 payload structure."""
        # Use ContentGenerator's frontmatter if provided, otherwise fall back to data frontmatter
        frontmatter = content_gen_frontmatter if content_gen_frontmatter else data.get("frontmatter", {})
        
        # Clean frontmatter for API consumption
        cleaned_frontmatter = self.frontmatter_gen.clean_frontmatter_for_api(frontmatter)
        
        # Add thumbnails to story packets
        story_packets = self.utils.attach_blog_thumbnail_manifest(
            data.get("story_packets", []), target_date
        )
        
        # Add video objects to schema
        enhanced_schema = self.frontmatter_gen.add_video_objects_to_schema(
            cleaned_frontmatter.get("schema", {}), 
            story_packets
        )
        cleaned_frontmatter["schema"] = enhanced_schema
            
        # Build the API-v3 structure
        api_data = {
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "date": target_date,
            "frontmatter": cleaned_frontmatter,
                "content": {
                "body": content
            },
            "story_packets": story_packets,
            "metadata": data.get("metadata", {}),
            "related_posts": data.get("related_posts", []),
            "api_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "api_endpoint": f"/api/blog/{target_date}"
            }
        }
            
        # Copy SEO and timing data from polished data
        if "seo_meta" in data:
            api_data["seo_meta"] = data["seo_meta"]
        if "wordCount" in data:
            api_data["wordCount"] = data["wordCount"]
        if "timeRequired" in data:
            api_data["timeRequired"] = data["timeRequired"]
        
        # Merge schema.org data at root level
        if cleaned_frontmatter.get('schema'):
            blog_posting_schema = cleaned_frontmatter['schema']
            api_data.update({
                "headline": blog_posting_schema.get('headline'),
                "description": blog_posting_schema.get('description'),
                "author": blog_posting_schema.get('author'),
                "datePublished": blog_posting_schema.get('datePublished'),
                "dateModified": blog_posting_schema.get('dateModified'),
                "url": blog_posting_schema.get('url'),
                "mainEntityOfPage": blog_posting_schema.get('mainEntityOfPage'),
                "publisher": blog_posting_schema.get('publisher'),
                "image": blog_posting_schema.get('image'),
                "keywords": blog_posting_schema.get('keywords'),
                "wordCount": blog_posting_schema.get('wordCount'),
                "video": blog_posting_schema.get('video')
            })
            
        return api_data

    def _upload_to_r2(self, target_date: str, api_data: Dict[str, Any]) -> None:
        """Upload API v3 to R2 for Worker consumption."""
        try:
            from services.publisher_r2 import R2Publisher
            r2_publisher = R2Publisher()
            
            # Save to temporary file for R2Publisher to process
            temp_api_file = self.blogs_dir / target_date / f"API-v3-{target_date}_digest.json"
            with open(temp_api_file, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, indent=2, ensure_ascii=False)
            
            # Use R2Publisher's publish_blogs method for idempotent upload
            results = r2_publisher.publish_blogs(self.blogs_dir)
            if str(temp_api_file.relative_to(self.blogs_dir)) in results and results[str(temp_api_file.relative_to(self.blogs_dir))]:
                logger.info(f"Successfully uploaded API v3 to R2 for {target_date}")
            else:
                logger.warning(f"Failed to upload API v3 to R2 for {target_date}")
        except Exception as e:
            logger.warning(f"Failed to upload API v3 to R2 for {target_date}: {e}")
            # Don't fail the main operation for this
            
    def _generate_slug(self, title: str) -> str:
        """Generate a URL-safe slug from a title."""
        import re
        import unicodedata
        
        # Convert to lowercase and normalize unicode
        slug = unicodedata.normalize('NFKD', title.lower())
        
        # Remove emojis and special characters, keep only alphanumeric and spaces
        slug = re.sub(r'[^\w\s-]', '', slug)
        
        # Replace spaces and multiple hyphens with single hyphen
        slug = re.sub(r'[-\s]+', '-', slug)
        
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        
        # Limit length
        if len(slug) > 60:
            slug = slug[:60].rstrip('-')
        
        return slug or "untitled"

    def _word_count(self, content: str) -> int:
        """Count words in content."""
        import re
        from html import unescape
        
        # Strip markdown and HTML
        plain = re.sub(r'`{1,3}.*?`{1,3}', '', content, flags=re.S)
        plain = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', plain)
        plain = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', plain)
        plain = re.sub(r'<[^>]+>', '', plain)
        plain = re.sub(r'^\s*#{1,6}\s*', '', plain, flags=re.M)
        plain = re.sub(r'\s+', ' ', plain).strip()
        plain = unescape(plain)
        
        return len(plain.split()) if plain else 0

    def _read_time_minutes(self, words: int, wpm: int = 225) -> int:
        """Calculate reading time in minutes."""
        return max(1, round(words / wpm))

    def _ensure_absolute_images(self, data: Dict[str, Any]) -> None:
        """Ensure all image URLs are absolute."""
        frontmatter = data.get("frontmatter", {})
        
        # Normalize og:image
        if frontmatter.get("og", {}).get("og:image"):
            og_image = frontmatter["og"]["og:image"]
            if not og_image.startswith('http'):
                clean_path = og_image.lstrip('/')
                frontmatter["og"]["og:image"] = self.utils.get_cloudflare_url(clean_path)
        
        # Normalize schema image
        if frontmatter.get("schema"):
            schema = frontmatter["schema"]
            if "blogPosting" in schema and schema["blogPosting"].get("image"):
                image = schema["blogPosting"]["image"]
                if not image.startswith('http'):
                    clean_path = image.lstrip('/')
                    schema["blogPosting"]["image"] = self.utils.get_cloudflare_url(clean_path)
            elif schema.get("image"):
                image = schema["image"]
                if not image.startswith('http'):
                    clean_path = image.lstrip('/')
                    schema["image"] = self.utils.get_cloudflare_url(clean_path)

    def _clean_ai_placeholders(self, data: Dict[str, Any], content: str) -> None:
        """Remove any remaining AI placeholders from data and content."""
        def clean_text(text):
            if not isinstance(text, str):
                return text
            text = text.replace("[AI_GENERATE_SEO_DESCRIPTION]", "")
            text = text.replace("[AI_GENERATE_LEAD]", "")
            text = text.replace("[AI_GENERATE", "")
            return text.strip()
        
        # Clean frontmatter
        frontmatter = data.get("frontmatter", {})
        if frontmatter.get("description"):
            frontmatter["description"] = clean_text(frontmatter["description"])
        if frontmatter.get("og", {}).get("og:description"):
            frontmatter["og"]["og:description"] = clean_text(frontmatter["og"]["og:description"])
    
    def _generate_related_posts(self, target_date: str, blog_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate related posts for the current blog."""
        try:
            # Extract current post data
            frontmatter = blog_data.get("frontmatter", {})
            current_tags = frontmatter.get("tags", [])
            current_title = frontmatter.get("title", "")
            
            # Find related posts
            related_posts = self.related_service.find_related_posts(
                current_date=target_date,
                current_tags=current_tags,
                current_title=current_title,
                max_posts=3
            )
            
            return related_posts
            
        except Exception as e:
            logger.error(f"Error generating related posts for {target_date}: {e}")
            return []
    
    def _save_v3_api_response(self, target_date: str, api_data: Dict[str, Any]) -> None:
        """
        Save v3 API response to JSON file for R2 serving and local development.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            api_data: The v3 API response data to save
        """
        try:
            # Ensure blogs directory exists for this date
            date_dir = self.blogs_dir / target_date
            date_dir.mkdir(parents=True, exist_ok=True)
            
            # Save v3 API response to main blogs directory
            api_file_path = date_dir / f"API-v3-{target_date}_digest.json"
            with open(api_file_path, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, indent=2, ensure_ascii=False, cls=DateEncoder)
            
            logger.info(f"Saved v3 API response to {api_file_path}")
            
            # Also save a copy to cloudflare-worker/blogs directory for local development
            try:
                cloudflare_worker_dir = Path("cloudflare-worker/blogs") / target_date
                cloudflare_worker_dir.mkdir(parents=True, exist_ok=True)
                
                cloudflare_worker_file_path = cloudflare_worker_dir / f"API-v3-{target_date}_digest.json"
                with open(cloudflare_worker_file_path, 'w', encoding='utf-8') as f:
                    json.dump(api_data, f, indent=2, ensure_ascii=False, cls=DateEncoder)
                
                logger.info(f"Saved v3 API response to cloudflare-worker directory: {cloudflare_worker_file_path}")
                
            except Exception as e:
                logger.warning(f"Failed to save v3 API response to cloudflare-worker directory: {e}")
                # Don't fail the main operation for this
                
        except Exception as e:
            logger.exception("Failed to save v3 API response for %s", target_date)
            # Don't raise - this is not critical for API functionality
    
    def get_blog_markdown(self, target_date: str) -> str:
        """Get raw markdown content for a date."""
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
        """Get all assets for a blog post with Cloudflare R2 URLs."""
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
                "images": [self.utils.get_cloudflare_url(path) for path in assets["images"]],
                "videos": [self.utils.get_cloudflare_url(path) for path in assets["videos"]]
            }
            
            return BlogAssets(**cloudflare_assets)
            
        except Exception as e:
            logger.exception(f"Failed to get blog assets for {target_date}")
            raise
    
    def _get_story_assets(self, target_date: str, story_id: str) -> StoryAssets:
        """Get assets for a specific story."""
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


def _safe_strip_md(text: str) -> str:
    """Very light markdown strip for description/lead safety."""
    if not isinstance(text, str):
        return ""
    t = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.S)        # inline/blocks
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", t)                  # images
    t = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", t)              # links -> text
    t = re.sub(r"<[^>]+>", "", t)                               # HTML tags (e.g., <video>)
    t = re.sub(r"^\s*#{1,6}\s*", "", t, flags=re.M)             # headings
    t = re.sub(r"\s+", " ", t).strip()
    return unescape(t)


def _word_count(md: str) -> int:
    """Count words in markdown content."""
    plain = _safe_strip_md(md)
    return len(plain.split()) if plain else 0


def _read_time_minutes(words: int, wpm: int = 225) -> int:
    """Calculate reading time in minutes."""
    return max(1, round(words / wpm))


def _iso_minutes(minutes: int) -> str:
    """Convert minutes to ISO 8601 duration format."""
    return f"PT{int(minutes)}M"


def _hash_for_etag(obj) -> str:
    """Generate hash for ETag from object."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _first_nonempty(*vals):
    """Return first non-empty string value."""
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _ensure_abs(url: Optional[str]) -> Optional[str]:
    """Ensure URL is absolute; return None if relative."""
    if not url or url.startswith("http://") or url.startswith("https://"):
        return url
    return None


def _trim(s: str, max_len: int) -> str:
    """Trim string to max length with ellipsis."""
    if not s:
        return s
    s = s.strip()
    return s if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def _dedupe_seq(seq):
    """Deduplicate sequence while preserving order."""
    seen = set()
    out = []
    for x in seq or []:
        if not isinstance(x, str): 
            continue
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out


def _ensure_video_objects(final_blog_data: dict) -> None:
    """Guarantee schema.org VideoObject list with thumbnailUrl for each story video."""
    videos = []
    for sp in final_blog_data.get("story_packets", []):
        v = (sp.get("video") or {})
        path = v.get("path") or ""
        if not path or not path.startswith("http"):
            continue
        name = sp.get("title_human") or sp.get("title_raw") or "Video"
        thumb = None
        thumbs = (v.get("thumbnails") or {})
        # prefer intro/highlight if present
        for key in ("intro", "highlight", "why", "outro"):
            if key in thumbs and thumbs[key]:
                thumb = thumbs[key]
                break
        # normalize thumb to absolute (media domain should already produce absolute if via utils)
        if thumb and not thumb.startswith("http"):
            thumb = None
        videos.append({
            "@type": "VideoObject",
            "name": name,
            "description": _trim(_first_nonempty(sp.get("why"), sp.get("ai_comprehensive_intro"), ""), 300),
            "contentUrl": path,
            "thumbnailUrl": thumb,
            "uploadDate": sp.get("merged_at"),
            "duration": "PT90S" if (sp.get("explainer") or {}).get("target_seconds") == 90 else None
        })
    # attach to both root and (if present) frontmatter.schema
    if videos:
        final_blog_data["video"] = videos
        fm_schema = (((final_blog_data.get("frontmatter") or {}).get("schema")) or {})
        if fm_schema:
            fm_schema["video"] = videos
            final_blog_data["frontmatter"]["schema"] = fm_schema


def _apply_final_seo_polish(final_blog_data: dict) -> dict:
    """Apply final SEO polish to blog data after all other processing is complete."""
    data = final_blog_data.copy()

    # 1) Content body & placeholder hygiene
    body = (((data.get("content") or {}).get("body")) or data.get("articleBody") or "")
    # remove any leaked placeholders or duplicate intros
    body = body.replace("[AI_GENERATE_LEAD]", "")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    data.setdefault("content", {})["body"] = body
    data["articleBody"] = body  # keep parity at root for consumers that expect it
    
    # Clean up AI_GENERATE placeholders in other fields
    def _clean_placeholders(text):
        if not isinstance(text, str):
            return text
        # Remove common AI generation placeholders
        text = text.replace("[AI_GENERATE_SEO_DESCRIPTION]", "")
        text = text.replace("[AI_GENERATE_LEAD]", "")
        text = text.replace("[AI_GENERATE", "")  # Catch any incomplete placeholders
        return text.strip()
    
    # Clean up description fields and ensure consistency
    # Get the best description from og:description if available
    og_description = data.get("frontmatter", {}).get("og", {}).get("og:description", "")
    
    # Use og:description if it exists and is not a placeholder
    if og_description and "[AI_GENERATE" not in og_description:
        best_description = og_description
    else:
        # Clean up existing descriptions
        best_description = _clean_placeholders(data.get("description", ""))
    
    # Set description consistently across all fields
    if best_description:
        data["description"] = best_description
        data.setdefault("frontmatter", {})["description"] = best_description
        data.setdefault("frontmatter", {}).setdefault("og", {})["og:description"] = best_description
        data.setdefault("seo_meta", {})["description"] = best_description
    else:
        # Clean up any remaining placeholders
        if data.get("description"):
            data["description"] = _clean_placeholders(data["description"])
        if data.get("frontmatter", {}).get("description"):
            data["frontmatter"]["description"] = _clean_placeholders(data["frontmatter"]["description"])
        if data.get("frontmatter", {}).get("og", {}).get("og:description"):
            data["frontmatter"]["og"]["og:description"] = _clean_placeholders(data["frontmatter"]["og"]["og:description"])
        if data.get("seo_meta", {}).get("description"):
            data["seo_meta"]["description"] = _clean_placeholders(data["seo_meta"]["description"])
    

    # 2) wordCount + read time
    wc = _word_count(body)
    minutes = _read_time_minutes(wc)
    data["wordCount"] = wc
    data["timeRequired"] = _iso_minutes(minutes)

    # 3) Canonical/URL sanity - ensure coherence across all fields
    canonical = _first_nonempty(
        (data.get("seo_meta") or {}).get("canonical"),
        (data.get("frontmatter") or {}).get("og", {}).get("og:url"),
        data.get("url"),
    )
    if canonical:
        # Mirror canonical to all required fields for consistency
        data["url"] = canonical
        data.setdefault("seo_meta", {})["canonical"] = canonical
        
        # Mirror to frontmatter fields
        if data.get("frontmatter"):
            # Mirror to og:url
            if data["frontmatter"].get("og"):
                data["frontmatter"]["og"]["og:url"] = canonical
            # Mirror to schema.url
            if data["frontmatter"].get("schema"):
                data["frontmatter"]["schema"]["url"] = canonical

    # 4) Title/description consolidation
    title = _first_nonempty(
        (data.get("seo_meta") or {}).get("title"),
        (data.get("frontmatter") or {}).get("title"),
        data.get("headline"),
    )
    desc = _first_nonempty(
        (data.get("seo_meta") or {}).get("description"),
        (data.get("frontmatter") or {}).get("description"),
        data.get("description"),
    )
    # trim to sensible lengths for SERP/snippets
    if title:
        title = _trim(title, 70)
        data["headline"] = title
        data.setdefault("seo_meta", {})["title"] = title
        if data.get("frontmatter"):
            data["frontmatter"]["title"] = title
            if data["frontmatter"].get("og"):
                data["frontmatter"]["og"]["og:title"] = title
    if desc:
        desc = _trim(_safe_strip_md(desc), 160)
        data["description"] = desc
        data.setdefault("seo_meta", {})["description"] = desc
        if data.get("frontmatter"):
            data["frontmatter"]["description"] = desc
            if data["frontmatter"].get("og"):
                data["frontmatter"]["og"]["og:description"] = desc

    # 5) Image normalization (prefer OG image; ensure absolute)
    og_img = _first_nonempty(
        (data.get("seo_meta") or {}).get("og:image"),
        (data.get("frontmatter") or {}).get("og", {}).get("og:image"),
        (data.get("frontmatter") or {}).get("schema", {}).get("image"),
        data.get("image"),
    )
    if _ensure_abs(og_img):
        data["image"] = og_img
        data.setdefault("seo_meta", {})["og:image"] = og_img
        if data.get("frontmatter"):
            data["frontmatter"].setdefault("og", {})["og:image"] = og_img
            if data["frontmatter"].get("schema"):
                data["frontmatter"]["schema"]["image"] = og_img

    # 6) Keywords/tags dedupe
    kw = _dedupe_seq(
        (data.get("keywords") or []) +
        ((data.get("frontmatter") or {}).get("schema", {}).get("keywords") or []) +
        ((data.get("frontmatter") or {}).get("tags") or [])
    )
    if kw:
        data["keywords"] = kw[:20]
        if data.get("frontmatter"):
            data["frontmatter"]["tags"] = kw[:20]
            if data["frontmatter"].get("schema"):
                data["frontmatter"]["schema"]["keywords"] = kw[:20]

    # 7) Language + mainEntityOfPage/publisher/author IDs if easy to infer
    data.setdefault("seo_schema", {})
    data["seo_schema"]["inLanguage"] = data.get("seo_schema", {}).get("inLanguage") or "en-US"

    # 8) Video objects from story packets (with thumbnails)
    _ensure_video_objects(data)

    # 9) Stable ETag & cache hints
    etag = _hash_for_etag({"url": data.get("url"), "wc": wc, "updated": data.get("dateModified"), "body": body[:2048]})
    data["seo_headers"] = {
        "X-Robots-Tag": "index, follow",
        "Cache-Control": "public, max-age=3600",
        "ETag": f"\"{data.get('date','')}-{etag[:16]}\""
    }

    return data

