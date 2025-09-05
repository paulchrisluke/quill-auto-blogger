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
        self.media_domain = os.getenv("MEDIA_DOMAIN", "https://media.paulchrisluke.com").rstrip("/")
        self.blog_default_image = os.getenv("BLOG_DEFAULT_IMAGE", f"{self.media_domain}/assets/pcl-labs-logo.svg")
        self.worker_domain = os.getenv("WORKER_DOMAIN", "https://quill-blog-api-prod.paulchrisluke.workers.dev")
        
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
    
    def build_normalized_digest(self, target_date: str) -> Dict[str, Any]:
        """
        Build a normalized digest for a specific date with story packets.
        First tries to load existing normalized digest, falls back to building from raw data.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary containing normalized digest data, metadata, and story packets
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
                
                # Check if digest has enhanced schema.org (support both legacy and unified formats)
                frontmatter = digest.get("frontmatter", {})
                schema = frontmatter.get("schema", {})
                has_enhanced_schema = (
                    schema.get("@type") == "BlogPosting" or  # Unified format
                    schema.get("blogPosting")  # Legacy format
                )
                if "frontmatter" in digest and has_enhanced_schema:
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
                
                # Check if digest has enhanced schema.org (support both legacy and unified formats)
                frontmatter = digest.get("frontmatter", {})
                schema = frontmatter.get("schema", {})
                has_enhanced_schema = (
                    schema.get("@type") == "BlogPosting" or  # Unified format
                    schema.get("blogPosting")  # Legacy format
                )
                if "frontmatter" in digest and has_enhanced_schema:
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
            "meta": {"kind": "NormalizedDigest", "version": 1, "generated_at": datetime.now().isoformat()},
            "date": target_date,
            "twitch_clips": clips_data,
            "github_events": events_data,
            "metadata": self._generate_metadata(target_date, twitch_clips, github_events),
            "frontmatter": frontmatter.model_dump(mode="json", by_alias=True),
            "story_packets": [packet.model_dump(mode="json") for packet in enhanced_story_packets]
        }
        
        return digest

    def ingest_sources(self, target_date: str) -> Dict[str, Any]:
        """
        Ingest raw events from Twitch and GitHub sources.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Raw events dictionary
        """
        # Load raw data from data directory
        date_path = self.data_dir / target_date
        if not date_path.exists():
            raise FileNotFoundError(f"No data found for {target_date}")
        
        twitch_clips = self.io.load_twitch_clips(date_path)
        github_events = self.io.load_github_events(date_path)
        
        raw_events = {
            "meta": {"kind": "RawEvents", "version": 1, "generated_at": datetime.now().isoformat()},
            "twitch": [clip.model_dump(mode="json") for clip in twitch_clips],
            "github": [event.model_dump(mode="json") for event in github_events]
        }
        
        # Save raw events
        self.io.save_raw_events(raw_events, target_date)
        return raw_events

    def enhance_digest_with_ai(self, normalized_digest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance normalized digest with AI content.
        
        Args:
            normalized_digest: Normalized digest dictionary
            
        Returns:
            Enriched digest dictionary
        """
        return self.io.enhanceDigestWithAI(normalized_digest)

    def save_publish_package(self, package: Dict[str, Any], target_date: str) -> Path:
        """
        Save publish package to file system.
        
        Args:
            package: Publish package dictionary
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Path to saved publish package
        """
        return self.io.save_publish_package(package, target_date)
    
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
        return self.build_normalized_digest(latest_date)
    
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
            out_dir = Path(self.blogs_dir) / target_date
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
        video_dir = Path(self.blogs_dir) / target_date
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
    
    def _ensure_videos_rendered(self, enriched_digest: Dict[str, Any], target_date: str) -> None:
        """Ensure all story packets have rendered videos."""
        story_packets = enriched_digest.get("story_packets", [])
        
        for packet_data in story_packets:
            video_data = packet_data.get("video", {})
            
            # Check if video needs to be rendered
            if (video_data.get("status") == "rendered" and 
                video_data.get("path") and 
                not self._video_file_exists(video_data["path"], target_date)):
                
                logger.info(f"Video file missing for {packet_data.get('id', 'unknown')}, rendering...")
                self._render_video_for_packet_data(packet_data, target_date)
    
    def _video_file_exists(self, video_path: str, target_date: str) -> bool:
        """Check if video file actually exists on disk."""
        try:
            # Convert path to actual file path
            if video_path.startswith("blogs/"):
                # blogs/2025-08-27/story_123.mp4 -> blogs/2025-08-27/story_123.mp4
                file_path = Path(video_path)
            elif video_path.startswith("out/videos/"):
                # out/videos/2025-08-27/story_123.mp4 -> out/videos/2025-08-27/story_123.mp4
                file_path = Path(video_path)
            else:
                # Assume it's a relative path
                file_path = Path(video_path)
            
            return file_path.exists()
        except Exception:
            return False
    
    def _render_video_for_packet_data(self, packet_data: Dict[str, Any], target_date: str) -> None:
        """Render video for a story packet data dict."""
        try:
            from tools.renderer_html import render_for_packet
            
            # Create output directory for videos
            out_dir = Path(self.blogs_dir) / target_date
            out_dir.mkdir(parents=True, exist_ok=True)
            
            # Render the video
            video_path = render_for_packet(packet_data, out_dir)
            
            # Get video duration
            from tools.renderer_html import get_video_duration
            duration = get_video_duration(Path(video_path))
            
            # Update packet with video info
            if "video" not in packet_data:
                packet_data["video"] = {}
            
            packet_data["video"]["status"] = "rendered"
            packet_data["video"]["path"] = video_path
            packet_data["video"]["duration_s"] = duration if duration > 0 else None
            packet_data["video"]["canvas"] = "1920x1080"
            
            logger.info(f"Rendered video for {packet_data.get('id', 'unknown')}: {video_path}")
            
        except Exception as e:
            logger.error(f"Failed to render video for {packet_data.get('id', 'unknown')}: {e}")
            # Mark as failed
            if "video" not in packet_data:
                packet_data["video"] = {}
            packet_data["video"]["status"] = "failed"
            packet_data["video"]["error"] = str(e)
    
    def assemble_publish_package(self, target_date: str) -> Dict[str, Any]:
        """Assemble publish package from enriched digest using the new API v3 serializer."""
        try:
            # Step 1: Load enriched digest
            try:
                enriched_digest = self.io.load_enriched_digest(target_date)
                logger.info(f"Loaded existing enriched digest for {target_date}")
            except FileNotFoundError:
                logger.info(f"Enriched digest not found, building from normalized digest")
                # Load normalized digest and enhance it
                normalized_digest = self.io.load_normalized_digest(target_date)
                enriched_digest = self.io.enhanceDigestWithAI(normalized_digest)
                # Save enriched digest
                self.io.save_enriched_digest(enriched_digest, target_date)
            
            # Step 2: Generate content with AI enhancements
            content_gen = ContentGenerator(enriched_digest, self.utils)
            consolidated_content = content_gen.generate(ai_enabled=True, related_enabled=True)
            
            # Step 3: Render videos for story packets if they don't exist
            self._ensure_videos_rendered(enriched_digest, target_date)
            
            # Step 4: Normalize assets (convert local paths to Cloudflare URLs)
            enriched_digest = content_gen.normalize_assets(enriched_digest)
            
            # Step 4.5: Add the generated content to the digest
            enriched_digest["content"] = {"body": consolidated_content}
            
            # Step 4: Use the new API v3 serializer to build publish package
            from .serializers.api_v3 import build as build_api_v3
            publish_package = build_api_v3(
                enriched_digest, 
                self.blog_author, 
                self.blog_base_url, 
                self.media_domain
            )
            
            # Step 4.5: Validate the final package
            _validate_api_data(publish_package)
            
            # Step 5: Save and upload
            self.io.save_publish_package(publish_package, target_date)
            self._upload_to_r2(target_date, publish_package)
            
            return publish_package
            
        except Exception as e:
            logger.exception("Failed to assemble publish package for %s", target_date)
            raise





    def _upload_to_r2(self, target_date: str, publish_package: Dict[str, Any]) -> None:
        """Upload API v3 publish package to R2 for Worker consumption."""
        try:
            from services.publisher_r2 import R2Publisher
            r2_publisher = R2Publisher()
            
            # Save to temporary file for R2Publisher to process
            temp_api_file = self.blogs_dir / target_date / f"{target_date}_page.publish.json"
            with open(temp_api_file, 'w', encoding='utf-8') as f:
                json.dump(publish_package, f, indent=2, ensure_ascii=False, cls=DateEncoder)
            
            # Use R2Publisher's publish_blogs method for idempotent upload
            results = r2_publisher.publish_blogs(self.blogs_dir)
            if str(temp_api_file.relative_to(self.blogs_dir)) in results and results[str(temp_api_file.relative_to(self.blogs_dir))]:
                logger.info(f"Successfully uploaded API v3 publish package to R2 for {target_date}")
            else:
                logger.warning(f"Failed to upload API v3 publish package to R2 for {target_date}")
        except Exception as e:
            logger.warning(f"Failed to upload API v3 publish package to R2 for {target_date}: {e}")
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
            from services.utils import get_schema_property, set_schema_property, migrate_legacy_schema_to_unified
            
            schema = frontmatter["schema"]
            # Migrate to unified format if needed
            schema = migrate_legacy_schema_to_unified(schema)
            frontmatter["schema"] = schema
            
            # Get and normalize image
            image = get_schema_property(schema, "image")
            if image and not image.startswith('http'):
                clean_path = image.lstrip('/')
                normalized_image = self.utils.get_cloudflare_url(clean_path)
                set_schema_property(schema, "image", normalized_image)

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
    
    def savePublishPackage(self, target_date: str, api_data: Dict[str, Any]) -> None:
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
            api_file_path = date_dir / f"{target_date}_digest.enriched.json"
            with open(api_file_path, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, indent=2, ensure_ascii=False, cls=DateEncoder)
            
            logger.info(f"Saved v3 API response to {api_file_path}")
            
            # Also save a copy to cloudflare-worker/blogs directory for local development
            try:
                cloudflare_worker_dir = Path("cloudflare-worker/blogs") / target_date
                cloudflare_worker_dir.mkdir(parents=True, exist_ok=True)
                
                cloudflare_worker_file_path = cloudflare_worker_dir / f"{target_date}_page.publish.json"
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
            digest = self.build_normalized_digest(target_date)
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
            digest = self.build_normalized_digest(target_date)
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




def _validate_api_data(data: dict) -> None:
    """Validate API v3 data to ensure all required fields are present and no deprecated fields exist."""
    # Check for deprecated fields that should not exist
    deprecated_fields = ["frontmatter", "seo_meta", "articleBody", "headline", "description", "image", "video"]
    for field in deprecated_fields:
        if field in data:
            logger.warning(f"Deprecated field '{field}' found in API v3 data")
    
    # Validate required fields exist
    required_fields = ["url", "datePublished", "dateModified", "wordCount", "timeRequired", 
                      "content", "media", "stories", "related", "schema", "headers"]
    for field in required_fields:
        if field not in data:
            logger.warning(f"Required field '{field}' missing from API v3 data")
    
    # Validate content structure
    content = data.get("content", {})
    if not isinstance(content, dict):
        logger.warning("Content field should be a dictionary")
    else:
        required_content_fields = ["title", "summary", "body", "tags"]
        for field in required_content_fields:
            if field not in content:
                logger.warning(f"Required content field '{field}' missing")
    
    # Validate media structure
    media = data.get("media", {})
    if not isinstance(media, dict):
        logger.warning("Media field should be a dictionary")
    else:
        if "hero" not in media or "videos" not in media:
            logger.warning("Media field missing 'hero' or 'videos'")
        elif not isinstance(media.get("videos"), list):
            logger.warning("Media.videos should be a list")
    
    # Validate stories structure and video references
    stories = data.get("stories", [])
    video_ids = {video.get("id") for video in media.get("videos", [])}
    for story in stories:
        if not isinstance(story, dict):
            logger.warning("Story should be a dictionary")
            continue
        
        video_id = story.get("videoId")
        if video_id and video_id not in video_ids:
            logger.warning(f"Story videoId '{video_id}' not found in media.videos")
    
    # Validate schema structure
    schema = data.get("schema", {})
    if not isinstance(schema, dict):
        logger.warning("Schema field should be a dictionary")
    elif schema.get("@type") != "BlogPosting":
        logger.warning("Schema @type should be 'BlogPosting'")
    
    # Validate timeRequired is in ISO8601 format
    time_required = data.get("timeRequired")
    if time_required and not time_required.startswith("PT"):
        logger.warning(f"timeRequired not in ISO8601 format: {time_required}")
    
    # Check for AI placeholders
    body = content.get("body", "")
    if "[AI_" in str(body):
        logger.warning("AI placeholders found in body content")
    
    # Validate headers structure
    headers = data.get("headers", {})
    if not isinstance(headers, dict):
        logger.warning("Headers field should be a dictionary")
    else:
        required_headers = ["X-Robots-Tag", "Cache-Control", "ETag"]
        for header in required_headers:
            if header not in headers:
                logger.warning(f"Required header '{header}' missing")

