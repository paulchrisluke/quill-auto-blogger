"""
Cache management service for Cloudflare cache purging and cache headers.
Handles cache invalidation after content updates.
"""

import logging
import os
import httpx
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CacheManager:
    """Manage Cloudflare cache purging and cache headers."""
    
    def __init__(self, account_id: str = None, api_token: str = None, zone_id: str = None):
        self.account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = api_token or os.getenv("CLOUDFLARE_API_TOKEN")
        self.zone_id = zone_id or os.getenv("CLOUDFLARE_ZONE_ID")
        
        if not all([self.account_id, self.api_token]):
            logger.warning("Cloudflare credentials not found. Cache purging will be disabled.")
    
    def purge_cache_by_urls(self, urls: List[str]) -> bool:
        """
        Purge specific URLs from Cloudflare cache.
        
        Args:
            urls: List of URLs to purge
            
        Returns:
            True if successful, False otherwise
        """
        if not all([self.account_id, self.api_token]):
            logger.warning("Cannot purge cache: Cloudflare credentials missing")
            return False
        
        if not urls:
            logger.info("No URLs to purge")
            return True
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "files": urls
            }
            
            api_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/purge_cache"
            
            logger.info(f"Purging {len(urls)} URLs from Cloudflare cache")
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(api_url, headers=headers, json=data)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        logger.info(f"✓ Successfully purged {len(urls)} URLs from cache")
                        return True
                    else:
                        logger.error(f"✗ Cache purge failed: {result.get('errors', [])}")
                        return False
                else:
                    logger.error(f"✗ Cache purge HTTP error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"✗ Cache purge error: {e}")
            return False
    
    def purge_cache_by_tags(self, tags: List[str]) -> bool:
        """
        Purge cache by tags (more efficient for bulk operations).
        
        Args:
            tags: List of cache tags to purge
            
        Returns:
            True if successful, False otherwise
        """
        if not all([self.account_id, self.api_token]):
            logger.warning("Cannot purge cache: Cloudflare credentials missing")
            return False
        
        if not tags:
            logger.info("No tags to purge")
            return True
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "tags": tags
            }
            
            api_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/purge_cache"
            
            logger.info(f"Purging cache by tags: {tags}")
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(api_url, headers=headers, json=data)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        logger.info(f"✓ Successfully purged cache by tags: {tags}")
                        return True
                    else:
                        logger.error(f"✗ Cache purge by tags failed: {result.get('errors', [])}")
                        return False
                else:
                    logger.error(f"✗ Cache purge by tags HTTP error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"✗ Cache purge by tags error: {e}")
            return False
    
    def purge_entire_cache(self) -> bool:
        """
        Purge entire Cloudflare cache (use with caution).
        
        Returns:
            True if successful, False otherwise
        """
        if not all([self.account_id, self.api_token]):
            logger.warning("Cannot purge cache: Cloudflare credentials missing")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "purge_everything": True
            }
            
            api_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/purge_cache"
            
            logger.warning("Purging entire Cloudflare cache - this may impact performance")
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(api_url, headers=headers, json=data)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        logger.info("✓ Successfully purged entire cache")
                        return True
                    else:
                        logger.error(f"✗ Entire cache purge failed: {result.get('errors', [])}")
                        return False
                else:
                    logger.error(f"✗ Entire cache purge HTTP error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"✗ Entire cache purge error: {e}")
            return False
    
    def get_cache_headers(self, content_type: str = "html") -> Dict[str, str]:
        """
        Get appropriate cache headers for different content types.
        
        Args:
            content_type: Type of content ("html", "json", "image", "video")
            
        Returns:
            Dictionary of cache headers
        """
        if content_type == "html":
            return {
                "Cache-Control": "public, max-age=3600, s-maxage=86400",
                "CDN-Cache-Control": "public, max-age=86400"
            }
        elif content_type == "json":
            return {
                "Cache-Control": "public, max-age=300, s-maxage=1800",
                "CDN-Cache-Control": "public, max-age=1800"
            }
        elif content_type == "image":
            return {
                "Cache-Control": "public, max-age=86400, s-maxage=86400",
                "CDN-Cache-Control": "public, max-age=86400"
            }
        elif content_type == "video":
            return {
                "Cache-Control": "public, max-age=86400, s-maxage=86400",
                "CDN-Cache-Control": "public, max-age=86400"
            }
        else:
            return {
                "Cache-Control": "public, max-age=300, s-maxage=1800",
                "CDN-Cache-Control": "public, max-age=1800"
            }
    
    def purge_blog_cache(self, blog_date: str, api_domain: str, frontend_domain: str) -> bool:
        """
        Purge cache for a specific blog post and related content.
        
        Args:
            blog_date: Blog post date (YYYY-MM-DD)
            api_domain: API domain for cache purging
            frontend_domain: Frontend domain for cache purging
            
        Returns:
            True if successful, False otherwise
        """
        urls_to_purge = [
            f"{api_domain}/blogs/{blog_date}/API-v3-{blog_date}_digest.json",
            f"{api_domain}/blogs/index.json",
            f"{api_domain}/rss.xml",
            f"{api_domain}/sitemap.xml",
            f"{frontend_domain}/blog/{blog_date}",
            f"{frontend_domain}/",
            f"{frontend_domain}/blog"
        ]
        
        # Also purge by tags for more efficient cache invalidation
        tags_to_purge = [
            f"blog-{blog_date}",
            "blogs-index",
            "feeds"
        ]
        
        # Purge by URLs
        url_success = self.purge_cache_by_urls(urls_to_purge)
        
        # Purge by tags
        tag_success = self.purge_cache_by_tags(tags_to_purge)
        
        return url_success and tag_success
