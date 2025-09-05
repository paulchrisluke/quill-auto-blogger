"""
Utility methods for digest building operations.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Any, Optional, Dict

logger = logging.getLogger(__name__)


class DigestUtils:
    """Utility methods for digest building operations."""
    
    def __init__(self, media_domain: str, blog_default_image: str):
        self.media_domain = media_domain
        self.blog_default_image = blog_default_image
    
    def select_best_image(self, story_packets: List[Any]) -> str:
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
            logger.warning("No story packets provided for image selection, using default blog image")
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
            
            # Delegate to the existing helper method for consistent thumbnail URL generation
            try:
                thumbnail_url = self.get_video_thumbnail_url(video_path, best_story.id if hasattr(best_story, 'id') else '')
                return thumbnail_url
            except ValueError as e:
                logger.error(f"Failed to generate thumbnail URL for video: {video_path}: {e}")
                raise
        
        # No suitable video thumbnail found
        logger.warning("No suitable video thumbnail found in any story packets, using default blog image")
        return self.blog_default_image
    
    def get_video_thumbnail_url(self, video_path: str, story_id: str) -> str:
        """
        Generate thumbnail URL for a video based on its path.
        
        Args:
            video_path: Path to the video file
            story_id: Story identifier for fallback
            
        Returns:
            URL string for the thumbnail, or empty string if not available
        """
        try:
            # Normalize incoming video_path: strip URL scheme and leading slashes
            clean_path = video_path
            if video_path.startswith('https://'):
                from urllib.parse import urlsplit
                clean_path = urlsplit(video_path).path
            clean_path = clean_path.lstrip('/')
            
            # Split the cleaned path into parts
            parts = clean_path.split('/')
            
            # Handle stories paths: stories/YYYY/MM/DD/filename
            if parts[0] == 'stories' and len(parts) >= 5:
                try:
                    year = parts[1]
                    month = parts[2]
                    day = parts[3]
                    filename = parts[4]
                    
                    # Validate date components
                    if not (year.isdigit() and month.isdigit() and day.isdigit()):
                        logger.warning(f"Invalid date components in stories path: {video_path}")
                        return ""
                    
                    # Strip file extension before constructing intro PNG filename
                    filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    intro_jpg = f"{filename}_01_intro.png"
                    return f"{self.media_domain}/stories/{year}/{month}/{day}/{intro_jpg}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse stories path {video_path}: {e}")
                    return ""
            
            # Handle assets/out/videos paths: assets/out/videos/YYYY-MM-DD/filename
            elif len(parts) >= 5 and parts[0] == 'assets' and parts[1] == 'out' and parts[2] == 'videos':
                try:
                    date_part = parts[3]  # YYYY-MM-DD
                    filename = parts[4]
                    
                    # Parse date and convert to YYYY/MM/DD format
                    date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                    year = str(date_obj.year)
                    month = f"{date_obj.month:02d}"
                    day = f"{date_obj.day:02d}"
                    
                    # Strip file extension before constructing intro JPG filename
                    filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    # Use filename as-is for media domain (single "story" format)
                    intro_jpg = f"{filename}_01_intro.png"
                    return f"{self.media_domain}/stories/{year}/{month}/{day}/{intro_jpg}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse assets/out/videos path {video_path}: {e}")
                    return ""
            
            # Handle blogs paths: blogs/YYYY-MM-DD/filename (new format)
            elif len(parts) >= 3 and parts[0] == 'blogs':
                try:
                    date_part = parts[1]  # YYYY-MM-DD
                    filename = parts[2]
                    
                    # Parse date and convert to YYYY/MM/DD format
                    date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                    year = str(date_obj.year)
                    month = f"{date_obj.month:02d}"
                    day = f"{date_obj.day:02d}"
                    
                    # Strip file extension before constructing intro JPG filename
                    filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    # Use filename as-is for media domain (single "story" format)
                    intro_jpg = f"{filename}_01_intro.png"
                    return f"{self.media_domain}/stories/{year}/{month}/{day}/{intro_jpg}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse blogs path {video_path}: {e}")
                    return ""
            
            # Fallback: try to generate from story_id if available
            if story_id and clean_path:
                # Extract date from video path if possible
                if 'stories/' in clean_path:
                    import re
                    date_match = re.search(r'stories/(\d{4})/(\d{2})/(\d{2})/', clean_path)
                    if date_match:
                        year, month, day = date_match.groups()
                        # Use the story_id directly as it should match the actual filename
                        return f"{self.media_domain}/stories/{year}/{month}/{day}/{story_id}_01_intro.png"
            
            logger.error(f"Could not determine thumbnail path for: {video_path}")
            raise ValueError(f"Failed to generate thumbnail path for video: {video_path}")
            
        except (IndexError, ValueError) as e:
            logger.error(f"Failed to generate thumbnail URL for {video_path}: {e}")
            raise ValueError(f"Failed to generate thumbnail URL for video {video_path}: {e}")
    
    def get_cloudflare_url(self, asset_path: str) -> str:
        """
        Convert local asset path to Worker API URL.
        
        Args:
            asset_path: Local asset path (e.g., "stories/2025/08/29/story_123.mp4")
            
        Returns:
            Full Worker API URL for the asset
        """
        try:
            # Handle different asset types with correct paths
            if asset_path.startswith("blogs/"):
                # Convert blogs/YYYY-MM-DD/filename to stories/YYYY/MM/DD/filename for videos
                # e.g., blogs/2025-08-27/story_123.mp4 -> stories/2025/08/27/story_123.mp4
                try:
                    path_parts = asset_path.split('/')
                    if len(path_parts) >= 3:
                        date_part = path_parts[1]  # Get YYYY-MM-DD from blogs/YYYY-MM-DD/
                        filename = path_parts[2]   # Get filename
                        year, month, day = date_part.split('-')
                        worker_path = f"/stories/{year}/{month}/{day}/{filename}"
                    else:
                        worker_path = f"/{asset_path}"
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to convert blogs path {asset_path}: {e}")
                    worker_path = f"/{asset_path}"
            elif asset_path.startswith("assets/"):
                # Other assets in assets/ path
                worker_path = f"/{asset_path}"
            elif asset_path.startswith("stories/"):
                # Story images are stored in stories/ path
                worker_path = f"/{asset_path}"
            else:
                # Default: add /assets/ prefix for other paths
                worker_path = f"/assets/{asset_path}"
            
            # Use media_domain for all assets (videos and images)
            return f"{self.media_domain}{worker_path}"
                
        except Exception as e:
            logger.exception("Failed to generate Worker URL for %s", asset_path)
            return f"/{asset_path}"
    
    def enhance_story_packets_with_thumbnail_urls(self, story_packets: List[Any], _target_date: str) -> List[Any]:
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
                thumbnail_url = self.get_video_thumbnail_url(enhanced_packet.video.path, enhanced_packet.id)
                
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
    
    def enhance_existing_digest_with_thumbnails(self, digest: Dict[str, Any], _target_date: str) -> List[Dict[str, Any]]:
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
                thumbnail_url = self.get_video_thumbnail_url(enhanced_packet['video']['path'], enhanced_packet.get('id', ''))
                
                # Add thumbnail URL to video info
                if thumbnail_url:
                    enhanced_packet['video']['thumbnail_url'] = thumbnail_url
            
            enhanced_packets.append(enhanced_packet)
        
        return enhanced_packets

    def attach_blog_thumbnail_manifest(self, story_packets: List[Any], target_date: str) -> List[Any]:
        """
        Attach blog thumbnail manifest to story packets for video objects.
        
        Args:
            story_packets: List of story packet objects
            target_date: Date string in YYYY-MM-DD format
            
        Returns:
            List of enhanced story packets with thumbnail manifest
            
        Note:
            Thumbnail paths are generated for Worker assets served at /assets/blogs/.
            All thumbnails use .png extension for consistency.
        """
        enhanced_packets = []
        
        for packet in story_packets:
            # Convert to dict if it's a Pydantic model
            if hasattr(packet, 'model_dump'):
                enhanced_packet = packet.model_dump(mode="json")
            else:
                enhanced_packet = packet.copy()
            
            # Add thumbnails to video object if it exists and is rendered
            video_data = enhanced_packet.get("video", {})
            if video_data.get("status") == "rendered":
                # Generate thumbnail paths based on story ID
                story_id = enhanced_packet.get("id", "")
                if story_id:
                    # Use raw story_id as base (do not modify "story_" prefix)
                    # e.g., story_20250827_pr34 -> /stories/2025/08/27/story_20250827_pr34_01_intro.png
                    
                    thumbnails = {
                        "intro": self.get_cloudflare_url(f"blogs/{target_date}/{story_id}_01_intro.png"),
                        "why": self.get_cloudflare_url(f"blogs/{target_date}/{story_id}_02_why.png"), 
                        "outro": self.get_cloudflare_url(f"blogs/{target_date}/{story_id}_99_outro.png"),
                        "highlight": self.get_cloudflare_url(f"blogs/{target_date}/{story_id}_hl_01.png")
                    }
                    
                    enhanced_packet["video"]["thumbnails"] = thumbnails
            
            enhanced_packets.append(enhanced_packet)
        
        return enhanced_packets
