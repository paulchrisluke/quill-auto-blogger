"""
Automatic blog generation service.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from .blog import BlogDigestBuilder
from .publisher_r2 import R2Publisher

logger = logging.getLogger(__name__)


def generate_daily_blog(target_date: Optional[str] = None, upload_to_r2: bool = True) -> Dict[str, Any]:
    """
    Automatically generate a daily blog post.
    
    Args:
        target_date: Date in YYYY-MM-DD format. If None, uses yesterday's date.
        upload_to_r2: Whether to upload the generated blog to R2.
        
    Returns:
        Dictionary with generation results and metadata.
    """
    # Determine target date
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.info(f"Starting automatic blog generation for {target_date}")
    
    result = {
        "date": target_date,
        "success": False,
        "story_count": 0,
        "videos_rendered": 0,
        "blog_generated": False,
        "r2_uploaded": False,
        "error": None
    }
    
    try:
        # Initialize blog builder
        builder = BlogDigestBuilder()
        
        # Check if data exists for this date
        data_dir = builder.data_dir / target_date
        if not data_dir.exists():
            logger.info(f"No data found for {target_date}, skipping blog generation")
            result["error"] = "No data found"
            return result
        
        # Check if blog already exists
        blog_dir = builder.blogs_dir / target_date
        if blog_dir.exists() and (blog_dir / f'API-v3-{target_date}_digest.json').exists():
            logger.info(f"Blog already exists for {target_date}, skipping generation")
            result["error"] = "Blog already exists"
            return result
        
        # Generate the blog
        logger.info(f"Building digest for {target_date}...")
        digest = builder.build_digest(target_date)
        
        # Check if we have story packets (merged PRs)
        story_count = len(digest.get('story_packets', []))
        result["story_count"] = story_count
        
        if story_count == 0:
            logger.info(f"No story packets found for {target_date}, skipping blog generation")
            result["error"] = "No story packets found"
            return result
        
        logger.info(f"Found {story_count} story packets, generating blog...")
        
        # Save PRE-CLEANED digest
        digest_path = builder.save_digest(digest)
        logger.info(f"Saved PRE-CLEANED digest: {digest_path}")
        
        # Create FINAL digest with AI enhancements
        final_digest = builder.create_final_digest(target_date)
        if not final_digest:
            logger.error(f"Failed to create FINAL digest for {target_date}")
            result["error"] = "Failed to create FINAL digest"
            return result
        
        logger.info(f"Created FINAL digest with AI enhancements")
        
        # Render videos for story packets
        logger.info(f"Rendering videos for {story_count} story packets...")
        videos_rendered = _render_videos_for_digest(final_digest, target_date)
        result["videos_rendered"] = videos_rendered
        logger.info(f"Rendered {videos_rendered} videos")
        
        # Save the updated digest with rendered videos
        if videos_rendered > 0:
            final_digest_path = builder.blogs_dir / target_date / f"FINAL-{target_date}_digest.json"
            with open(final_digest_path, 'w') as f:
                json.dump(final_digest, f, indent=2, default=str)
            logger.info(f"Saved updated FINAL digest with rendered videos: {final_digest_path}")
        
        # Generate API data for R2 serving
        api_data = builder.get_blog_api_data(target_date)
        logger.info(f"Generated API data with {len(api_data.get('story_packets', []))} story packets")
        
        result["blog_generated"] = True
        
        # Upload to R2 if requested
        if upload_to_r2:
            try:
                publisher = R2Publisher()
                logger.info(f"Uploading blogs to R2...")
                upload_results = publisher.publish_blogs(Path('blogs'))
                
                # Check if our blog was uploaded
                blog_key = f'{target_date}/API-v3-{target_date}_digest.json'
                if blog_key in upload_results and upload_results[blog_key]:
                    logger.info(f"Successfully uploaded blog for {target_date} to R2")
                    result["r2_uploaded"] = True
                else:
                    logger.error(f"Failed to upload blog for {target_date} to R2")
                    result["error"] = "R2 upload failed"
                    
            except Exception as e:
                logger.error(f"Error uploading to R2: {e}")
                result["error"] = f"R2 upload error: {e}"
        
        result["success"] = True
        logger.info(f"✅ Successfully generated blog for {target_date}")
        
    except Exception as e:
        logger.error(f"❌ Error generating blog for {target_date}: {e}")
        result["error"] = str(e)
    
    return result


def generate_missing_blogs(days_back: int = 7) -> Dict[str, Any]:
    """
    Generate blogs for missing dates going back a specified number of days.
    
    Args:
        days_back: Number of days to check backwards for missing blogs.
        
    Returns:
        Dictionary with generation results for each date.
    """
    results = {}
    
    for i in range(1, days_back + 1):
        target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        logger.info(f"Checking for missing blog on {target_date}")
        
        result = generate_daily_blog(target_date, upload_to_r2=True)
        results[target_date] = result
        
        if result["success"]:
            logger.info(f"✅ Generated missing blog for {target_date}")
        elif result["error"] == "Blog already exists":
            logger.info(f"⏭️ Blog already exists for {target_date}")
        else:
            logger.warning(f"⚠️ Failed to generate blog for {target_date}: {result['error']}")
    
    return results


def _render_videos_for_digest(digest: Dict[str, Any], target_date: str) -> int:
    """
    Render videos for all story packets in a digest that need rendering.
    
    Args:
        digest: The digest containing story packets
        target_date: The date for the blog post
        
    Returns:
        Number of videos successfully rendered
    """
    story_packets = digest.get("story_packets", [])
    rendered_count = 0
    
    # Create output directory for videos
    out_dir = Path("out/videos") / target_date
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for packet in story_packets:
        story_id = packet.get("id")
        video_info = packet.get("video", {})
        
        # Check if packet needs rendering
        video_status = video_info.get("status")
        needs_rendering = video_status != "rendered"
        
        if not needs_rendering:
            logger.info(f"Skipping {story_id} - video already rendered")
            continue
        
        try:
            logger.info(f"Rendering video for {story_id}...")
            
            # Import renderer
            from tools.renderer_html import render_for_packet
            
            # Render the video
            video_path = render_for_packet(packet, out_dir)
            
            # Update packet with video info
            packet["video"]["status"] = "rendered"
            packet["video"]["path"] = video_path
            packet["video"]["canvas"] = "1920x1080"  # Default canvas size
            
            # Get video duration
            from tools.renderer_html import get_video_duration
            duration = get_video_duration(Path(video_path))
            if duration > 0:
                packet["video"]["duration_s"] = duration
            
            rendered_count += 1
            logger.info(f"✅ Rendered video for {story_id}: {video_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to render video for {story_id}: {e}")
            # Mark as failed
            packet["video"]["status"] = "failed"
            packet["video"]["error"] = str(e)
    
    return rendered_count


if __name__ == "__main__":
    # Allow running as a script
    import sys
    
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = None
    
    result = generate_daily_blog(target_date)
    
    if result["success"]:
        print(f"✅ Successfully generated blog for {result['date']}")
        print(f"   Story packets: {result['story_count']}")
        print(f"   R2 uploaded: {result['r2_uploaded']}")
    else:
        print(f"❌ Failed to generate blog for {result['date']}: {result['error']}")
        sys.exit(1)
