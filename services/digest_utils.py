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
                    base_name = filename.rsplit('.', 1)[0]  # Safely strip .mp4 extension
                    intro_png = f"{base_name}_01_intro.png"
                    
                    # Generate Worker URL for the intro PNG
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
            
            # Fallback: try to convert existing path format
            intro_png_path = video_path.replace(".mp4", "_01_intro.png")
            if intro_png_path.startswith('/stories/'):
                return f"https://{self.worker_domain}{intro_png_path.replace('.mp4', '_01_intro.png')}"
        
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
            # Strip extension and split path into parts
            base_name = video_path.rsplit('.', 1)[0]  # Safely strip extension
            parts = base_name.split('/')
            
            # Validate path structure before indexing
            if len(parts) < 5:
                logger.warning(f"Invalid video path structure (insufficient parts): {video_path}")
                return ""
            
            # Handle stories paths: stories/YYYY/MM/DD/filename
            if parts[0] == 'stories':
                try:
                    year = parts[1]
                    month = parts[2]
                    day = parts[3]
                    filename = parts[4]
                    
                    # Validate date components
                    if not (year.isdigit() and month.isdigit() and day.isdigit()):
                        logger.warning(f"Invalid date components in path: {video_path}")
                        return ""
                    
                    # Construct intro PNG filename
                    intro_png = f"{filename}_01_intro.png"
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse stories path {video_path}: {e}")
                    return ""
            
            # Handle out/videos paths: out/videos/YYYY-MM-DD/filename
            elif parts[0] == 'out' and parts[1] == 'videos':
                try:
                    date_part = parts[2]  # YYYY-MM-DD
                    filename = parts[3]
                    
                    # Parse date and convert to YYYY/MM/DD format
                    date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                    year = str(date_obj.year)
                    month = f"{date_obj.month:02d}"
                    day = f"{date_obj.day:02d}"
                    
                    # Construct intro PNG filename
                    intro_png = f"{filename}_01_intro.png"
                    return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{intro_png}"
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse out/videos path {video_path}: {e}")
                    return ""
            
            # Handle absolute paths starting with /stories/
            elif video_path.startswith('/stories/'):
                # Remove leading slash and process as relative path
                clean_path = video_path.lstrip('/')
                return self.get_video_thumbnail_url(clean_path, story_id)
            
            # Handle HTTPS URLs
            elif video_path.startswith('https://'):
                from urllib.parse import urlsplit
                path = urlsplit(video_path).path
                if '/stories/' in path:
                    stories_index = path.find('/stories/')
                    if stories_index != -1:
                        stories_path = path[stories_index:]
                        # Convert video path to thumbnail path
                        thumbnail_path = stories_path.replace('.mp4', '_01_intro.png')
                        return f"https://{self.worker_domain}/assets{thumbnail_path}"
            
            # Fallback: try to generate from story_id if available
            if story_id and video_path:
                # Extract date from video path if possible
                if '/stories/' in video_path:
                    import re
                    date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', video_path)
                    if date_match:
                        year, month, day = date_match.groups()
                        return f"https://{self.worker_domain}/assets/stories/{year}/{month}/{day}/{story_id}_01_intro.png"
            
            logger.warning(f"Could not determine thumbnail path for: {video_path}")
            return ""
            
        except Exception as e:
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
