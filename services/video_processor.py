"""
Video processing service for thumbnail generation and lightweight video optimization.
Generates JPG/PNG thumbnails and ensures single resolution storage.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import json

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handle video thumbnail generation and lightweight processing."""
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self.thumbnail_format = "jpg"  # Can be changed to "png" if needed
        self.thumbnail_quality = "85"  # JPG quality (1-100)
        self.target_resolution = "720p"  # Single resolution for storage efficiency
    
    def generate_thumbnail(
        self, 
        video_path: Path, 
        output_path: Path,
        timestamp: str = "00:00:05",
        width: int = 480,
        height: int = 270
    ) -> bool:
        """
        Generate a thumbnail from video at specified timestamp.
        
        Args:
            video_path: Path to input video file
            output_path: Path for output thumbnail
            timestamp: Timestamp to extract frame from (HH:MM:SS)
            width: Thumbnail width
            height: Thumbnail height
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Build ffmpeg command for thumbnail generation
            cmd = [
                self.ffmpeg_path,
                "-i", str(video_path),
                "-ss", timestamp,
                "-vframes", "1",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-q:v", "2",  # High quality for thumbnails
                "-y",  # Overwrite output file
                str(output_path)
            ]
            
            logger.info(f"Generating thumbnail: {video_path.name} -> {output_path.name}")
            
            # Run ffmpeg command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"✓ Thumbnail generated: {output_path}")
                return True
            else:
                logger.error(f"✗ Thumbnail generation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"✗ Thumbnail generation timed out for {video_path}")
            return False
        except Exception as e:
            logger.error(f"✗ Thumbnail generation error for {video_path}: {e}")
            return False
    
    def optimize_video_resolution(
        self, 
        input_path: Path, 
        output_path: Path,
        target_height: int = 720
    ) -> bool:
        """
        Optimize video to single target resolution for storage efficiency.
        
        Args:
            input_path: Path to input video file
            output_path: Path for output optimized video
            target_height: Target height (720p = 720, 1080p = 1080)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Calculate target width maintaining aspect ratio
            # Assuming 16:9 aspect ratio for most content
            target_width = int(target_height * 16 / 9)
            
            # Build ffmpeg command for video optimization
            cmd = [
                self.ffmpeg_path,
                "-i", str(input_path),
                "-vf", f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",  # Good quality, reasonable file size
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",  # Optimize for web streaming
                "-y",  # Overwrite output file
                str(output_path)
            ]
            
            logger.info(f"Optimizing video resolution: {input_path.name} -> {output_path.name}")
            
            # Run ffmpeg command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout for video processing
            )
            
            if result.returncode == 0:
                logger.info(f"✓ Video optimized: {output_path}")
                return True
            else:
                logger.error(f"✗ Video optimization failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"✗ Video optimization timed out for {input_path}")
            return False
        except Exception as e:
            logger.error(f"✗ Video optimization error for {input_path}: {e}")
            return False
    
    def get_video_info(self, video_path: Path) -> Optional[Dict[str, Any]]:
        """
        Get video metadata using ffprobe.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with video info or None if failed
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                info = json.loads(result.stdout)
                
                # Extract relevant information
                video_info = {
                    "duration": info.get("format", {}).get("duration"),
                    "size": info.get("format", {}).get("size"),
                    "bitrate": info.get("format", {}).get("bit_rate"),
                    "width": None,
                    "height": None,
                    "fps": None
                }
                
                # Get video stream info
                for stream in info.get("streams", []):
                    if stream.get("codec_type") == "video":
                        video_info["width"] = stream.get("width")
                        video_info["height"] = stream.get("height")
                        video_info["fps"] = stream.get("r_frame_rate")
                        break
                
                return video_info
            else:
                logger.error(f"Failed to get video info: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting video info for {video_path}: {e}")
            return None
    
    def generate_story_thumbnails(self, story_packet: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
        """
        Generate thumbnails for a story packet (intro, why, outro, highlight).
        
        Args:
            story_packet: Story packet data
            output_dir: Output directory for thumbnails
            
        Returns:
            Dictionary mapping thumbnail types to file paths
        """
        thumbnails = {}
        video_path = story_packet.get("video", {}).get("path")
        
        if not video_path:
            logger.warning(f"No video path found for story {story_packet.get('id', 'unknown')}")
            return thumbnails
        
        # Convert URL to local path if needed
        if video_path.startswith("http"):
            # Extract filename from URL
            video_filename = Path(video_path).name
            video_path = Path("out/videos") / video_filename
        else:
            video_path = Path(video_path)
        
        if not video_path.exists():
            logger.warning(f"Video file not found: {video_path}")
            return thumbnails
        
        story_id = story_packet.get("id", "unknown")
        
        # Generate different thumbnail types
        thumbnail_configs = {
            "intro": {"timestamp": "00:00:03", "suffix": "01_intro"},
            "why": {"timestamp": "00:00:08", "suffix": "02_why"},
            "outro": {"timestamp": "00:00:12", "suffix": "99_outro"},
            "highlight": {"timestamp": "00:00:06", "suffix": "hl_01"}
        }
        
        for thumb_type, config in thumbnail_configs.items():
            output_filename = f"story_{story_id}_{config['suffix']}.{self.thumbnail_format}"
            output_path = output_dir / output_filename
            
            if self.generate_thumbnail(
                video_path, 
                output_path, 
                timestamp=config["timestamp"]
            ):
                thumbnails[thumb_type] = str(output_path)
                logger.info(f"Generated {thumb_type} thumbnail: {output_filename}")
            else:
                logger.warning(f"Failed to generate {thumb_type} thumbnail for {story_id}")
        
        return thumbnails
