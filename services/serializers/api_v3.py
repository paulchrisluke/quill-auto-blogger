"""
API v3 Serializer for PCL Labs Blog Pipeline

This module provides a single source of truth for serializing normalized digests
into the final publish package JSON structure. It eliminates all duplication
and provides a clean, stable API for Nuxt consumption.
"""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from html import unescape


class ApiV3Serializer:
    """Serializes normalized digests into the final API v3 publish package format."""
    
    def __init__(self, blog_author: str, blog_base_url: str, media_domain: str):
        self.blog_author = blog_author
        self.blog_base_url = blog_base_url.rstrip("/")
        self.media_domain = media_domain
        self.default_image = "https://source.unsplash.com/1200x630/?technology,programming,developer"
    
    def build(self, normalized_digest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build the final API v3 publish package from a normalized digest.
        
        Args:
            normalized_digest: The enriched/normalized digest with AI + CDN normalization
            
        Returns:
            Final publish package dictionary with target JSON shape
        """
        # Extract data from normalized digest
        frontmatter = normalized_digest.get("frontmatter", {})
        story_packets = normalized_digest.get("story_packets", [])
        related_posts = normalized_digest.get("related_posts", [])
        target_date = normalized_digest.get("date", "")
        
        # Generate content first to get the title
        content = self._extract_content(normalized_digest)
        
        # Generate canonical URL using the extracted title
        canonical_url = self._generate_canonical_url(
            content.get("title", ""), 
            target_date
        )
        
        # Calculate word count and time required
        word_count = self._word_count(content["body"])
        time_required = f"PT{max(1, word_count // 200)}M"
        
        # Build media objects
        media = self._build_media(story_packets)
        
        # Build stories with video references
        stories = self._build_stories(story_packets, media["videos"])
        
        # Build related posts
        related = self._build_related(related_posts)
        
        # Build schema from canonical fields
        schema = self._build_schema(
            content, media, canonical_url, target_date, word_count
        )
        
        # Build headers with stable ETag
        headers = self._build_headers(canonical_url, word_count, content["body"])
        
        # Assemble final package - only include the target JSON shape fields
        # Filter out any unwanted keys from the normalized digest
        package = {
            "_meta": {
                "kind": "PublishPackage",
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "url": canonical_url,
            "datePublished": target_date,
            "dateModified": datetime.now(timezone.utc).isoformat(),
            "wordCount": word_count,
            "timeRequired": time_required,
            "content": content,
            "media": media,
            "stories": stories,
            "related": related,
            "schema": schema,
            "headers": headers
        }
        
        return package
    
    def _generate_canonical_url(self, title: str, date_str: str) -> str:
        """Generate canonical URL with consistent slug generation."""
        if not date_str:
            return f"{self.blog_base_url}/blog/"
        
        slug = self._generate_slug(title)
        yyyy, mm, dd = date_str.split("-")
        return f"{self.blog_base_url}/blog/{yyyy}/{mm}/{dd}/{slug}/"
    
    def _generate_slug(self, title: str) -> str:
        """Generate a URL-safe slug from a title."""
        if not title:
            return "untitled"
        
        # Convert to lowercase and normalize unicode
        slug = unicodedata.normalize('NFKD', title.lower())
        
        # Remove emojis and special characters, keep only alphanumeric and spaces
        slug = re.sub(r'[^\w\s-]', '', slug)
        
        # Replace spaces and multiple hyphens with single hyphen
        slug = re.sub(r'[-\s]+', '-', slug)
        
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        
        # Limit length to 60 characters
        if len(slug) > 60:
            slug = slug[:60].rstrip('-')
        
        return slug or "untitled"
    
    def _extract_content(self, normalized_digest: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content fields from normalized digest."""
        # Handle both legacy frontmatter format and enriched digest format
        if "frontmatter" in normalized_digest:
            # Legacy format with frontmatter
            frontmatter = normalized_digest.get("frontmatter", {})
            title = frontmatter.get("title", "")
            summary = frontmatter.get("description", "")
            tags = frontmatter.get("tags", [])
        else:
            # Enriched digest format (direct fields)
            title = normalized_digest.get("title", "")
            summary = normalized_digest.get("description", "")
            tags = normalized_digest.get("tags", [])
        
        # Get body content - try multiple sources
        body = ""
        if "content" in normalized_digest and "body" in normalized_digest["content"]:
            body = normalized_digest["content"]["body"]
        elif "markdown_body" in normalized_digest:
            body = normalized_digest["markdown_body"]
        elif "content" in normalized_digest and isinstance(normalized_digest["content"], str):
            body = normalized_digest["content"]
        elif "articleBody" in normalized_digest:
            body = normalized_digest["articleBody"]
        
        # Clean up any AI placeholders
        body = self._clean_placeholders(body)
        
        return {
            "title": self._clean_placeholders(title),
            "summary": self._clean_placeholders(summary),
            "body": body,
            "tags": tags
        }
    
    def _build_media(self, story_packets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build media objects from story packets."""
        videos = []
        hero_image = self.default_image
        
        for packet in story_packets:
            video_data = packet.get("video", {})
            if video_data.get("status") == "rendered" and video_data.get("path"):
                # Construct thumbnail URL from video path
                video_path = video_data.get("path", "")
                thumbnail_url = ""
                if video_path:
                    # Replace .mp4 with _01_intro.png for thumbnail
                    thumbnail_url = video_path.replace(".mp4", "_01_intro.png")
                
                video_obj = {
                    "id": packet.get("id", ""),
                    "name": packet.get("title_human", ""),
                    "url": video_path,
                    "thumb": thumbnail_url,
                    "duration": "PT90S",  # Default duration
                    "uploadDate": packet.get("merged_at", "")
                }
                videos.append(video_obj)
                
                # Use first video thumbnail as hero image
                if not hero_image or hero_image == self.default_image:
                    hero_image = video_obj["thumb"] or self.default_image
        
        return {
            "hero": {"image": hero_image},
            "videos": videos
        }
    
    def _build_stories(self, story_packets: List[Dict[str, Any]], videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build stories array with video references."""
        stories = []
        video_ids = {video["id"] for video in videos}
        
        for packet in story_packets:
            story = {
                "id": packet.get("id", ""),
                "title": packet.get("title_human", ""),
                "why": packet.get("why", ""),
                "highlights": packet.get("highlights", []),
                "videoId": packet.get("id") if packet.get("id") in video_ids else None,
                "mergedAt": packet.get("merged_at", "")
            }
            stories.append(story)
        
        return stories
    
    def _build_related(self, related_posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build related posts array."""
        related = []
        for post in related_posts:
            related.append({
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "image": post.get("image"),
                "score": post.get("score", 0.0)
            })
        return related
    
    def _build_schema(self, content: Dict[str, Any], media: Dict[str, Any], 
                     canonical_url: str, target_date: str, word_count: int) -> Dict[str, Any]:
        """Build JSON-LD BlogPosting schema from canonical fields."""
        # Build video objects from media.videos
        video_objects = []
        for video in media["videos"]:
            video_obj = {
                "@type": "VideoObject",
                "name": video["name"],
                "contentUrl": video["url"],
                "thumbnailUrl": video["thumb"],
                "uploadDate": video["uploadDate"],
                "duration": video["duration"]
            }
            video_objects.append(video_obj)
        
        schema = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": content["title"],
            "description": content["summary"],
            "image": media["hero"]["image"],
            "url": canonical_url,
            "datePublished": target_date,
            "dateModified": datetime.now(timezone.utc).isoformat(),
            "wordCount": word_count,
            "keywords": content["tags"],
            "video": video_objects,
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": canonical_url
            },
            "author": {
                "@type": "Person",
                "@id": f"{self.blog_base_url}#author",
                "name": self.blog_author,
                "url": self.blog_base_url
            },
            "publisher": {
                "@type": "Organization",
                "@id": f"{self.blog_base_url}#organization",
                "name": "PCL Labs",
                "url": self.blog_base_url,
                "logo": {
                    "@type": "ImageObject",
                    "url": self.default_image,
                    "width": 200,
                    "height": 200
                }
            },
            "inLanguage": "en-US"
        }
        
        return schema
    
    def _build_headers(self, canonical_url: str, word_count: int, body: str) -> Dict[str, str]:
        """Build HTTP headers with stable ETag."""
        # Generate stable ETag from url + wordCount + body slice (no time-dependent fields)
        etag_data = {
            "url": canonical_url,
            "wc": word_count,
            "body": body[:2048]
        }
        # Use deterministic JSON serialization
        etag_json = json.dumps(etag_data, sort_keys=True, separators=(',', ':'))
        etag_hash = hashlib.sha256(etag_json.encode('utf-8')).hexdigest()[:16]
        
        return {
            "X-Robots-Tag": "index, follow",
            "Cache-Control": "public, max-age=3600",
            "ETag": f'"{etag_hash}"'
        }
    
    def _word_count(self, content: str) -> int:
        """Count words in content, stripping markdown and HTML."""
        if not content:
            return 0
        
        # Strip markdown and HTML
        plain = re.sub(r'`{1,3}.*?`{1,3}', '', content, flags=re.S)
        plain = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', plain)
        plain = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', plain)
        plain = re.sub(r'<[^>]+>', '', plain)
        plain = re.sub(r'^\s*#{1,6}\s*', '', plain, flags=re.M)
        plain = re.sub(r'\s+', ' ', plain).strip()
        plain = unescape(plain)
        
        return len(plain.split()) if plain else 0
    
    def _clean_placeholders(self, text: str) -> str:
        """Remove AI generation placeholders from text."""
        if not isinstance(text, str):
            return text
        
        text = text.replace("[AI_GENERATE_SEO_DESCRIPTION]", "")
        text = text.replace("[AI_GENERATE_LEAD]", "")
        text = text.replace("[AI_GENERATE", "")
        return text.strip()


def build(normalized_digest: Dict[str, Any], blog_author: str, 
          blog_base_url: str, media_domain: str) -> Dict[str, Any]:
    """
    Convenience function to build API v3 publish package.
    
    Args:
        normalized_digest: The enriched/normalized digest
        blog_author: Blog author name
        blog_base_url: Base URL for the blog
        media_domain: Media domain for assets
        
    Returns:
        Final publish package dictionary
    """
    serializer = ApiV3Serializer(blog_author, blog_base_url, media_domain)
    return serializer.build(normalized_digest)
