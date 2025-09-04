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
        
        # Check if publish package already exists
        data_dir = builder.data_dir / target_date
        if data_dir.exists() and (data_dir / 'page.publish.json').exists():
            logger.info(f"Publish package already exists for {target_date}, skipping generation")
            result["error"] = "Publish package already exists"
            return result
        
        # Orchestration: Clean stage-based pipeline
        logger.info(f"Starting clean stage-based pipeline for {target_date}...")
        
        # Step 1: Ingest sources → Raw Events
        logger.info("Step 1: Ingesting sources...")
        raw_events = builder.ingest_sources(target_date)
        
        # Step 2: Build normalized digest
        logger.info("Step 2: Building normalized digest...")
        normalized_digest = builder.build_normalized_digest(target_date)
        
        # Check if we have story packets (merged PRs)
        story_count = len(normalized_digest.get('story_packets', []))
        result["story_count"] = story_count
        
        if story_count == 0:
            logger.info(f"No story packets found for {target_date}, skipping blog generation")
            result["error"] = "No story packets found"
            return result
        
        logger.info(f"Found {story_count} story packets, continuing pipeline...")
        
        # Save normalized digest
        normalized_path = builder.io.save_normalized_digest(normalized_digest, target_date)
        logger.info(f"Saved normalized digest: {normalized_path}")
        
        # Step 3: Enhance with AI → Enriched Digest
        logger.info("Step 3: Enhancing with AI...")
        enriched_digest = builder.io.enhanceDigestWithAI(normalized_digest)
        enriched_path = builder.io.save_enriched_digest(enriched_digest, target_date)
        logger.info(f"Saved enriched digest: {enriched_path}")
        
        # Step 4: Assemble publish package
        logger.info("Step 4: Assembling publish package...")
        publish_package = builder.assemble_publish_package(target_date)
        logger.info(f"Assembled publish package with {len(publish_package.get('story_packets', []))} stories")
        
        # Count rendered videos
        rendered_count = sum(1 for packet in normalized_digest.get('story_packets', []) 
                           if packet.get('video', {}).get('status') == 'rendered')
        result["videos_rendered"] = rendered_count
        logger.info(f"Videos rendered during story packet generation: {rendered_count}")
        
        result["blog_generated"] = True
        
        # Upload to R2 if requested
        if upload_to_r2:
            try:
                publisher = R2Publisher()
                logger.info(f"Uploading blogs to R2...")
                upload_results = publisher.publish_blogs(Path('data'))
                
                # Check if our publish package was uploaded
                blog_key = f'{target_date}/page.publish.json'
                if blog_key in upload_results and upload_results[blog_key]:
                    logger.info(f"Successfully uploaded publish package for {target_date} to R2")
                    result["r2_uploaded"] = True
                else:
                    logger.error(f"Failed to upload publish package for {target_date} to R2")
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


def generate_missing_blogs(days_back: int = 7, upload_to_r2: bool = True) -> Dict[str, Any]:
    """
    Generate blogs for missing dates going back a specified number of days.
    
    Args:
        days_back: Number of days to check backwards for missing blogs.
        upload_to_r2: Whether to upload the generated blogs to R2.
        
    Returns:
        Dictionary with generation results for each date.
    """
    results = {}
    
    for i in range(1, days_back + 1):
        target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        logger.info(f"Checking for missing blog on {target_date}")
        
        result = generate_daily_blog(target_date, upload_to_r2=upload_to_r2)
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
