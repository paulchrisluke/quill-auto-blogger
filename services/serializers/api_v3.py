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
        # Use a fixed default stock image for deterministic builds
        import os
        default_stock_images = [
            "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=1200&h=630&fit=crop",  # Code on screen
            "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1200&h=630&fit=crop",  # Developer workspace
            "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=1200&h=630&fit=crop",  # Programming setup
            "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&h=630&fit=crop",  # Data visualization
            "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200&h=630&fit=crop",  # Tech workspace
        ]
        self.default_image = os.getenv("BLOG_DEFAULT_IMAGE", default_stock_images[0])
    
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
            "title": content["title"],
            "summary": content["summary"],
            "content": content["body"],
            "tags": content["tags"],
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
        # Prioritize direct fields over frontmatter for enriched digests
        if normalized_digest.get("title") or normalized_digest.get("description"):
            # Enriched digest format (direct fields) - prioritize these
            title = normalized_digest.get("title", "")
            summary = normalized_digest.get("description", "")
            tags = normalized_digest.get("tags", [])
        elif "frontmatter" in normalized_digest:
            # Legacy format with frontmatter
            frontmatter = normalized_digest.get("frontmatter", {})
            title = frontmatter.get("title", "")
            summary = frontmatter.get("description", "")
            tags = frontmatter.get("tags", [])
        else:
            # Fallback to empty values
            title = ""
            summary = ""
            tags = []
        
        # Get body content - try multiple sources
        body = ""
        if "content" in normalized_digest and isinstance(normalized_digest["content"], str):
            # Content is a string (enriched digest format)
            body = normalized_digest["content"]
        elif "content" in normalized_digest and isinstance(normalized_digest["content"], dict) and "body" in normalized_digest["content"]:
            # Content is a dict with body field
            body = normalized_digest["content"]["body"]
        elif "markdown_body" in normalized_digest:
            body = normalized_digest["markdown_body"]
        elif "articleBody" in normalized_digest:
            body = normalized_digest["articleBody"]

        # If content carries tags, prefer/merge them
        if isinstance(normalized_digest.get("content"), dict) and normalized_digest["content"].get("tags"):
            if not tags:
                tags = normalized_digest["content"]["tags"]
            else:
                tags = list(dict.fromkeys([*tags, *normalized_digest["content"]["tags"]]))
        
        # Clean up any AI placeholders
        body = self._clean_placeholders(body)
        
        # Process markdown content for better formatting and linking
        body = self._process_markdown_content(body, normalized_digest)
        
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
    
    def _process_markdown_content(self, content: str, normalized_digest: Dict[str, Any]) -> str:
        """
        Process AI-generated content to add proper markdown formatting, links, and structure.
        
        Args:
            content: Raw AI-generated content
            normalized_digest: The normalized digest containing resource data
            
        Returns:
            Enhanced markdown content with proper formatting and links
        """
        if not content:
            return content
        
        # 1. Fix escaped newlines
        content = self._fix_escaped_newlines(content)
        
        # 2. Add proper headers based on content structure
        content = self._add_markdown_headers(content)
        
        # 3. Add links to Twitch clips and GitHub PRs
        content = self._add_resource_links(content, normalized_digest)
        
        # 4. Format code mentions as code blocks
        content = self._format_code_mentions(content)
        
        # 5. Add emphasis to technical terms
        content = self._add_emphasis(content)
        
        # 6. Convert lists to proper markdown lists
        content = self._format_lists(content)
        
        # 7. Add blockquotes for meta-commentary
        content = self._add_blockquotes(content)
        
        # 8. Add signature with proper links
        content = self._add_signature(content)
        
        return content
    
    def _fix_escaped_newlines(self, content: str) -> str:
        """Fix escaped newlines in AI-generated content."""
        # Replace escaped newlines with actual newlines
        content = content.replace('\\n', '\n')
        
        # Clean up multiple consecutive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content.strip()
    
    def _add_markdown_headers(self, content: str) -> str:
        """Add proper markdown headers to break up content sections."""
        lines = content.split('\n')
        processed_lines = []
        
        # Common section patterns to detect
        section_patterns = [
            (r'^(As I start my day|The first major milestone|But development doesn\'t happen)', '## What Shipped'),
            (r'^(While the code merged|Twitch captured|In one clip)', '## The Human Side'),
            (r'^(As the day goes on|I start to reflect|I think about)', '## Reflections'),
            (r'^(In the end|As I wrap up|And with that)', '## Wrap-Up'),
            (r'^(Finally|After hours of|I was able to)', '## The Solution'),
            (r'^(As I delved deeper|I realized that|The problem was)', '## The Challenge'),
        ]
        
        for line in lines:
            # Check if this line should start a new section
            header_added = False
            for pattern, header in section_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    processed_lines.append('')
                    processed_lines.append(header)
                    processed_lines.append('')
                    processed_lines.append(line)
                    header_added = True
                    break
            
            if not header_added:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def _add_resource_links(self, content: str, normalized_digest: Dict[str, Any]) -> str:
        """Add links to Twitch clips and GitHub PRs mentioned in content."""
        # Get available resources
        twitch_clips = normalized_digest.get('twitch_clips', [])
        github_events = normalized_digest.get('github_events', [])
        
        # Create lookup dictionaries
        clip_lookup = {}
        for clip in twitch_clips:
            title = clip.get('title', '').lower()
            url = clip.get('url', '')
            if title and url:
                clip_lookup[title] = url
        
        pr_lookup = {}
        for event in github_events:
            if event.get('type') == 'PullRequestEvent' and event.get('url'):
                pr_num = event.get('details', {}).get('number')
                title = event.get('title', '').lower()
                url = event.get('url', '')
                if pr_num and url:
                    pr_lookup[f"pr #{pr_num}"] = url
                    if title:
                        pr_lookup[title] = url
        
        # Add links to Twitch clips
        for clip_title, clip_url in clip_lookup.items():
            # Look for mentions of the clip title
            pattern = rf'\b{re.escape(clip_title)}\b'
            if re.search(pattern, content, re.IGNORECASE):
                content = re.sub(
                    pattern,
                    f'[{clip_title}]({clip_url})',
                    content,
                    flags=re.IGNORECASE
                )
        
        # Add links to PRs
        for pr_ref, pr_url in pr_lookup.items():
            pattern = rf'\b{re.escape(pr_ref)}\b'
            if re.search(pattern, content, re.IGNORECASE):
                content = re.sub(
                    pattern,
                    f'[{pr_ref}]({pr_url})',
                    content,
                    flags=re.IGNORECASE
                )
        
        return content
    
    def _format_code_mentions(self, content: str) -> str:
        """Format technical code mentions as proper code blocks or inline code."""
        # Common technical terms that should be formatted as inline code
        tech_terms = [
            'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_API_TOKEN', 'R2_ACCOUNT_ID', 'R2_API_TOKEN',
            'Bearer token', 'API endpoints', 'R2 storage', 'environment variables',
            'deployment URL', 'test script', 'authentication', 'REST API'
        ]
        
        for term in tech_terms:
            # Format as inline code if not already formatted
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, content, re.IGNORECASE):
                content = re.sub(
                    pattern,
                    f'`{term}`',
                    content,
                    flags=re.IGNORECASE
                )
        
        # Look for configuration changes and format as code blocks
        config_pattern = r'(changing|updating|fixing)\s+(CLOUDFLARE_ACCOUNT_ID|R2_ACCOUNT_ID|CLOUDFLARE_API_TOKEN|R2_API_TOKEN)\s+to\s+(R2_ACCOUNT_ID|CLOUDFLARE_ACCOUNT_ID|R2_API_TOKEN|CLOUDFLARE_API_TOKEN)'
        config_matches = re.finditer(config_pattern, content, re.IGNORECASE)
        
        for match in config_matches:
            original = match.group(0)
            # Extract the key parts
            start_var = match.group(2)
            end_var = match.group(3)
            
            # Create a code block for the configuration change
            code_block = f"""```bash
{start_var} → {end_var}
```"""
            
            content = content.replace(original, f"{original}\n\n{code_block}")
        
        return content
    
    def _add_emphasis(self, content: str) -> str:
        """Add emphasis to technical terms and important concepts."""
        # Terms that should be bold
        bold_terms = [
            'R2 storage configuration', 'audio processor', 'debugging', 'optimization',
            'automation tools', 'live-streaming', 'AI generation', 'pipeline',
            'caching', 'deduplication', 'workflow', 'API', 'authentication'
        ]
        
        for term in bold_terms:
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, content, re.IGNORECASE):
                content = re.sub(
                    pattern,
                    f'**{term}**',
                    content,
                    flags=re.IGNORECASE
                )
        
        # Terms that should be italic
        italic_terms = [
            'Clanker', 'meta-commentary', 'human story', 'community feedback',
            'personal insights', 'irony', 'absurdity', 'automation paradox'
        ]
        
        for term in italic_terms:
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, content, re.IGNORECASE):
                content = re.sub(
                    pattern,
                    f'*{term}*',
                    content,
                    flags=re.IGNORECASE
                )
        
        return content
    
    def _format_lists(self, content: str) -> str:
        """Convert paragraph lists to proper markdown lists."""
        # Look for sentences that start with action words and contain multiple items
        list_patterns = [
            r'(I started by|I began by|The steps included|The process involved).*?([^.]+\.)',
            r'(This involved|This included|The changes were).*?([^.]+\.)',
        ]
        
        for pattern in list_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                original = match.group(0)
                items_text = match.group(2)
                
                # Split on common separators
                items = re.split(r'[,;]\s*(?=\w)', items_text)
                if len(items) > 1:
                    # Create markdown list
                    list_items = []
                    for item in items:
                        item = item.strip().rstrip('.')
                        if item:
                            list_items.append(f"- {item}")
                    
                    if list_items:
                        markdown_list = '\n'.join(list_items)
                        replacement = f"{match.group(1)}:\n\n{markdown_list}"
                        content = content.replace(original, replacement)
        
        return content
    
    def _add_blockquotes(self, content: str) -> str:
        """Add blockquotes for meta-commentary sections."""
        # Look for meta-commentary patterns
        meta_patterns = [
            r'(It\'s a bit like building a machine that builds machines[^.]*\.)',
            r'(The irony is that[^.]*\.)',
            r'(I\'m a developer who\'s building tools that build tools[^.]*\.)',
            r'(building automation tools while live-streaming the process[^.]*\.)',
        ]
        
        for pattern in meta_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                original = match.group(1)
                blockquote = f"> {original}"
                content = content.replace(original, blockquote)
        
        return content
    
    def _add_signature(self, content: str) -> str:
        """Add proper signature with working links."""
        signature = """

---

**Hi. I'm Chris.** I'm a morally ambiguous technology marketer and builder at PCL Labs. I turn raw events into stories with wit, irreverence, and emotional honesty. I help solve complex technical challenges through AI blog automation, schema-driven SEO, and developer workflow optimization.

Book me on [Upwork](https://upwork.com/freelancers/paulchrisluke) or find someone who knows how to get ahold of me.

[Follow me on Twitch](https://twitch.tv/paulchrisluke) for live coding sessions and developer insights.
"""
        
        # Only add signature if it's not already there
        if "Hi. I'm Chris." not in content:
            content += signature
        
        return content


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
