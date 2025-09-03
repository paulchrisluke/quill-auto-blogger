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
    
    def __init__(self, worker_domain: str, blog_default_image: str):
        self.worker_domain = worker_domain
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
            thumbnail_url = self.get_video_thumbnail_url(video_path, best_story.id if hasattr(best_story, 'id') else '')
            return thumbnail_url if thumbnail_url else self.blog_default_image
        
        # Fallback: return default blog image when no suitable video thumbnail is found
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
                    intro_png = f"{filename}_01_intro.png"
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse stories path {video_path}: {e}")
                    return ""
            
            # Handle out/videos paths: out/videos/YYYY-MM-DD/filename
            elif len(parts) >= 4 and parts[0] == 'out' and parts[1] == 'videos':
                try:
                    date_part = parts[2]  # YYYY-MM-DD
                    filename = parts[3]
                    
                    # Parse date and convert to YYYY/MM/DD format
                    date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                    year = str(date_obj.year)
                    month = f"{date_obj.month:02d}"
                    day = f"{date_obj.day:02d}"
                    
                    # Strip file extension before constructing intro PNG filename
                    filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    intro_png = f"{filename}_01_intro.png"
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse out/videos path {video_path}: {e}")
                    return ""
            
            # Fallback: try to generate from story_id if available
            if story_id and clean_path:
                # Extract date from video path if possible
                if 'stories/' in clean_path:
                    import re
                    date_match = re.search(r'stories/(\d{4})/(\d{2})/(\d{2})/', clean_path)
                    if date_match:
                        year, month, day = date_match.groups()
                        return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{story_id}_01_intro.png"
            
            logger.warning(f"Could not determine thumbnail path for: {video_path}")
            return ""
            
        except (IndexError, ValueError) as e:
            logger.warning(f"Failed to generate thumbnail URL for {video_path}: {e}")
            return ""
    
    def get_cloudflare_url(self, asset_path: str) -> str:
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
    
    def enhance_story_packets_with_thumbnails(self, story_packets: List[Any], _target_date: str) -> List[Any]:
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
