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
        
        # Save PRE-CLEANED digest (videos are already rendered during story packet generation)
        digest_path = builder.save_digest(digest)
        logger.info(f"Saved PRE-CLEANED digest: {digest_path}")
        
        # Count rendered videos
        rendered_count = sum(1 for packet in digest.get('story_packets', []) 
                           if packet.get('video', {}).get('status') == 'rendered')
        result["videos_rendered"] = rendered_count
        logger.info(f"Videos rendered during story packet generation: {rendered_count}")
        
        # Create FINAL digest with AI enhancements
        final_digest = builder.create_final_digest(target_date)
        if not final_digest:
            logger.error(f"Failed to create FINAL digest for {target_date}")
            result["error"] = "Failed to create FINAL digest"
            return result
        
        logger.info(f"Created FINAL digest with AI enhancements")
        
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
