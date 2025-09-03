"""
R2 publisher service for static site and blog JSON publishing.
Handles idempotent uploads with MD5/ETag comparison, feed generation, and cache management.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, List, Any
import boto3
from botocore.exceptions import ClientError

from services.auth import AuthService
from services.feeds import FeedGenerator
from services.related import RelatedPostsService
from services.video_processor import VideoProcessor
from services.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class R2Publisher:
    """Handles publishing static site files and blog JSON to R2 with idempotency."""
    
    def __init__(self):
        self.auth_service = AuthService()
        self.r2_credentials = self.auth_service.get_r2_credentials()
        
        if not self.r2_credentials:
            raise ValueError(
                "R2 credentials not found. Please set R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_S3_ENDPOINT, and R2_BUCKET environment variables"
            )
        
        # Initialize S3 client for R2
        secret_key = self.r2_credentials.secret_access_key
        if hasattr(secret_key, 'get_secret_value'):
            aws_secret_access_key = secret_key.get_secret_value()
        else:
            aws_secret_access_key = str(secret_key) if secret_key is not None else ""
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.r2_credentials.access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=self.r2_credentials.endpoint,
            region_name=self.r2_credentials.region
        )
        
        self.bucket = self.r2_credentials.bucket
        
        # Initialize Milestone 7 services
        self.frontend_domain = os.getenv("FRONTEND_DOMAIN", "https://paulchrisluke.com")
        self.api_domain = os.getenv("API_DOMAIN", "https://api.paulchrisluke.com")
        
        self.feed_generator = FeedGenerator(self.frontend_domain, self.api_domain)
        self.related_service = RelatedPostsService()
        self.video_processor = VideoProcessor()
        self.cache_manager = CacheManager()
    
    def _hash_md5(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _should_skip(self, r2_key: str, local_md5: str) -> bool:
        """Check if file should be skipped (identical content already exists)."""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=r2_key)
            etag = response.get('ETag', '').strip('"')  # Remove quotes from ETag
            return etag == local_md5
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code in ('404', 'NotFound', 'NoSuchKey'):
                return False  # File doesn't exist, should upload
            logger.warning(f"Error checking R2 object {r2_key}: {e}", exc_info=True)
            return False  # On error, proceed with upload
    
    def _headers_for(self, file_path: Path) -> Dict[str, str]:
        """Get appropriate headers for file type."""
        suffix = file_path.suffix.lower()
        
        if suffix == '.html':
            return {
                'ContentType': 'text/html; charset=utf-8',
                'CacheControl': 'public, max-age=3600, s-maxage=86400'
            }
        elif suffix == '.json':
            return {
                'ContentType': 'application/json',
                'CacheControl': 'public, max-age=300, s-maxage=1800'
            }
        elif suffix in ['.jpg', '.jpeg', '.png']:
            return {
                'ContentType': f'image/{suffix[1:]}',
                'CacheControl': 'public, max-age=86400, s-maxage=86400'
            }
        elif suffix == '.xml':
            return {
                'ContentType': 'application/xml',
                'CacheControl': 'public, max-age=3600, s-maxage=86400'
            }
        else:
            return {
                'ContentType': 'application/octet-stream',
                'CacheControl': 'public, max-age=300, s-maxage=1800'
            }
    
    def publish_site(self, local_dir: Path) -> Dict[str, bool]:
        """Upload index.html idempotently."""
        results = {}
        
        if not local_dir.exists():
            logger.error(f"Site directory does not exist: {local_dir}")
            return results
        
        site_files = ['index.html']
        
        for filename in site_files:
            file_path = local_dir / filename
            if not file_path.exists():
                logger.warning(f"Site file not found: {file_path}")
                results[filename] = False
                continue
            
            try:
                local_md5 = self._hash_md5(file_path)
                r2_key = filename
                
                if self._should_skip(r2_key, local_md5):
                    logger.info(f"↻ Skipped {filename} (identical content)")
                    results[filename] = True
                    continue
                
                # Upload file
                with open(file_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket,
                        Key=r2_key,
                        Body=f,
                        **self._headers_for(file_path)
                    )
                
                logger.info(f"✓ Uploaded {filename}")
                results[filename] = True
                
            except Exception as e:
                logger.error(f"✗ Failed to upload {filename}: {e}")
                results[filename] = False
        
        return results
    
    def publish_blogs(self, blogs_dir: Path) -> Dict[str, bool]:
        """Upload API-v3 digest JSON files idempotently with enhanced features."""
        results = {}
        
        if not blogs_dir.exists():
            logger.error(f"Blogs directory does not exist: {blogs_dir}")
            return results
        
        # Find all API-v3 digest files
        api_v3_files = list(blogs_dir.rglob("API-v3-*_digest.json"))
        
        if not api_v3_files:
            logger.info("No API-v3 digest files found")
            return results
        
        # Load all blog data for feed generation and related posts
        all_blogs_data = []
        
        for file_path in api_v3_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    blog_data = json.load(f)
                all_blogs_data.append(blog_data)
            except Exception as e:
                logger.warning(f"Failed to load blog data from {file_path}: {e}")
        
        # Generate feeds and blogs index
        self._generate_and_publish_feeds(all_blogs_data)
        
        # Process each blog file
        for file_path in api_v3_files:
            try:
                # Calculate R2 key: blogs/YYYY-MM-DD/API-v3-YYYY-MM-DD_digest.json
                relative_path = file_path.relative_to(blogs_dir)
                r2_key = f"blogs/{relative_path}"
                
                # Load blog data for enhancement
                with open(file_path, 'r', encoding='utf-8') as f:
                    blog_data = json.load(f)
                
                # Enhance with related posts
                blog_data = self._enhance_with_related_posts(blog_data, all_blogs_data)
                
                # Generate thumbnails if video exists
                blog_data = self._enhance_with_thumbnails(blog_data, file_path.parent)
                
                # Write enhanced data back to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(blog_data, f, indent=2, ensure_ascii=False)
                
                local_md5 = self._hash_md5(file_path)
                
                if self._should_skip(r2_key, local_md5):
                    logger.info(f"↻ Skipped {r2_key} (identical content)")
                    results[str(relative_path)] = True
                    continue
                
                # Upload enhanced file
                with open(file_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket,
                        Key=r2_key,
                        Body=f,
                        **self._headers_for(file_path)
                    )
                
                logger.info(f"✓ Uploaded {r2_key}")
                results[str(relative_path)] = True
                
                # Purge cache for this blog post
                blog_date = blog_data.get('date')
                if blog_date:
                    self.cache_manager.purge_blog_cache(blog_date, self.api_domain, self.frontend_domain)
                
            except Exception as e:
                logger.error(f"✗ Failed to upload {file_path}: {e}")
                results[str(relative_path)] = False
        
        return results
    
    def _generate_and_publish_feeds(self, blogs_data: List[Dict[str, Any]]) -> None:
        """Generate and publish RSS, sitemap, and blogs index."""
        try:
            # Generate feeds
            rss_content = self.feed_generator.generate_rss_feed(blogs_data)
            sitemap_content = self.feed_generator.generate_sitemap(blogs_data)
            blogs_index = self.feed_generator.generate_blogs_index(blogs_data)
            
            # Create temporary files for upload
            feeds_dir = Path("out/feeds")
            feeds_dir.mkdir(parents=True, exist_ok=True)
            
            # Write RSS feed
            rss_file = feeds_dir / "rss.xml"
            with open(rss_file, 'w', encoding='utf-8') as f:
                f.write(rss_content)
            
            # Write sitemap
            sitemap_file = feeds_dir / "sitemap.xml"
            with open(sitemap_file, 'w', encoding='utf-8') as f:
                f.write(sitemap_content)
            
            # Write blogs index
            blogs_index_file = feeds_dir / "blogs-index.json"
            with open(blogs_index_file, 'w', encoding='utf-8') as f:
                json.dump(blogs_index, f, indent=2, ensure_ascii=False)
            
            # Upload feeds to R2
            feed_files = [
                (rss_file, "rss.xml"),
                (sitemap_file, "sitemap.xml"),
                (blogs_index_file, "blogs/index.json")
            ]
            
            for file_path, r2_key in feed_files:
                try:
                    local_md5 = self._hash_md5(file_path)
                    
                    if self._should_skip(r2_key, local_md5):
                        logger.info(f"↻ Skipped {r2_key} (identical content)")
                        continue
                    
                    with open(file_path, 'rb') as f:
                        self.s3_client.put_object(
                            Bucket=self.bucket,
                            Key=r2_key,
                            Body=f,
                            **self._headers_for(file_path)
                        )
                    
                    logger.info(f"✓ Uploaded {r2_key}")
                    
                except Exception as e:
                    logger.error(f"✗ Failed to upload {r2_key}: {e}")
            
            # Clean up temporary files
            for file_path, _ in feed_files:
                if file_path.exists():
                    file_path.unlink()
            
            if feeds_dir.exists():
                feeds_dir.rmdir()
                
        except Exception as e:
            logger.error(f"Failed to generate and publish feeds: {e}")
    
    def _enhance_with_related_posts(self, blog_data: Dict[str, Any], all_blogs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Enhance blog data with related posts using lightweight scoring."""
        try:
            frontmatter = blog_data.get('frontmatter', {})
            current_tags = frontmatter.get('tags', [])
            current_title = frontmatter.get('title', '')
            current_date = blog_data.get('date', '')
            
            if not all([current_tags, current_title, current_date]):
                logger.debug(f"Skipping related posts for {current_date} - missing required data")
                return blog_data
            
            # Find related posts
            related_posts = self.related_service.find_related_posts(
                current_date=current_date,
                current_tags=current_tags,
                current_title=current_title,
                max_posts=3
            )
            
            if related_posts:
                # Convert to the format expected by the frontend
                related_posts_data = []
                for title, path, score in related_posts:
                    related_posts_data.append({
                        "title": title,
                        "url": f"{self.frontend_domain}{path}",
                        "score": round(score, 3)
                    })
                
                blog_data['related_posts'] = related_posts_data
                logger.info(f"Added {len(related_posts_data)} related posts to {current_date}")
            
        except Exception as e:
            logger.warning(f"Failed to enhance with related posts: {e}")
        
        return blog_data
    
    def _enhance_with_thumbnails(self, blog_data: Dict[str, Any], blog_dir: Path) -> Dict[str, Any]:
        """Enhance blog data with video thumbnails."""
        try:
            story_packets = blog_data.get('story_packets', [])
            
            for packet in story_packets:
                video_info = packet.get('video', {})
                if video_info.get('status') == 'rendered':
                    # Generate thumbnails
                    thumbnails = self.video_processor.generate_story_thumbnails(
                        packet, 
                        blog_dir
                    )
                    
                    if thumbnails:
                        # Add thumbnail paths to video info
                        video_info['thumbnails'] = thumbnails
                        logger.info(f"Generated thumbnails for {packet.get('id', 'unknown')}")
            
        except Exception as e:
            logger.warning(f"Failed to enhance with thumbnails: {e}")
        
        return blog_data
