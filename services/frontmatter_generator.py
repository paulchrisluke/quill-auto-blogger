"""
Frontmatter generation for blog posts.
"""

import re
import unicodedata
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from story_schema import FrontmatterInfo
from .digest_utils import DigestUtils

logger = logging.getLogger(__name__)


class FrontmatterGenerator:
    """Generate clean frontmatter for blog posts."""

    def __init__(self, author: str, base_url: str, media_domain: str, frontend_domain: Optional[str] = None):
        self.author = author
        self.base_url = base_url.rstrip("/")
        self.media = media_domain
        self.frontend = frontend_domain.rstrip("/") if frontend_domain else self.base_url

    def slugify(self, title: str) -> str:
        """Generate a clean slug from title following the specified rules."""
        s = unicodedata.normalize("NFKD", title)
        s = s.encode("ascii", "ignore").decode("ascii")
        s = s.lower()
        s = re.sub(r"[^a-z0-9\s-]", "", s)
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        
        # Split into words and prioritize important keywords
        words = s.split("-")
        
        # If we have more than 8 words, try to preserve important SEO keywords
        if len(words) > 8:
            # Keywords that are important for SEO
            important_keywords = ['ai', 'automation', 'schema', 'content', 'blog', 'gen', 'powered', 'api', 'seo']
            
            # Keep first few words (usually brand/context)
            result_words = words[:3]  # e.g., ['pcl', 'labs', 'devlog']
            
            # Add important keywords from the rest
            remaining_words = words[3:]
            for word in remaining_words:
                if word in important_keywords and word not in result_words:
                    result_words.append(word)
            
            # Add remaining words (no character limit)
            for word in remaining_words:
                if word not in result_words:
                    result_words.append(word)
            
            s = "-".join(result_words)
        else:
            # Use all words if 8 or fewer
            s = "-".join(words)
        
        return s or "post"

    def generate_canonical_url(self, title: str, date_str: str, existing_slugs: Optional[List[str]] = None) -> str:
        """Generate canonical URL with collision handling."""
        base_slug = self.slugify(title)
        yyyy, mm, dd = date_str.split("-")
        
        # Handle collisions if existing slugs are provided
        if existing_slugs:
            slug = base_slug
            counter = 2
            while slug in existing_slugs:
                # Truncate base slug to make room for suffix
                max_base_length = 60 - len(f"-{counter}")
                truncated_base = base_slug[:max_base_length].rstrip("-")
                slug = f"{truncated_base}-{counter}"
                counter += 1
        else:
            slug = base_slug
            
        return f"{self.frontend}/blog/{yyyy}/{mm}/{dd}/{slug}/"

    def generate(
        self,
        date_str: str,
        clips: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        stories: List[Any],
    ) -> FrontmatterInfo:
        """Generate frontmatter with schema + OG metadata."""
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        headline = f"PCL Labs Devlog — {date_obj.strftime('%b %d, %Y')}"

        # Generate canonical URL with slug (will be updated after AI enhancement if needed)
        canonical = self.generate_canonical_url(headline, date_str)

        # Best image from stories
        utils = DigestUtils(self.media, f"{self.media}/assets/pcl-labs-logo.svg")
        try:
            best_image = utils.select_best_image(stories)
            if not best_image:
                best_image = utils.get_random_stock_image()
        except Exception as e:
            logger.warning(f"Failed to select best image from stories: {e}")
            best_image = utils.get_random_stock_image()

        # Placeholders for AI
        seo_description = "[AI_GENERATE_SEO_DESCRIPTION]"

        # Unified tags
        tags = self._generate_keywords(stories, clips, events)

        # Schema - use BlogPosting for consistency with seo_schema
        schema = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": headline,
            "datePublished": date_str,
            "author": {
                "@type": "Person", 
                "@id": f"{self.frontend}#author",
                "name": self.author,
                "url": self.frontend
            },
            "publisher": {
                "@type": "Organization",
                "@id": f"{self.frontend}#organization", 
                "name": "PCL Labs",
                "url": self.frontend,
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{self.media}/assets/pcl-labs-logo.png",
                    "width": 200,
                    "height": 200
                }
            },
            "keywords": tags,
            "url": canonical,
            "image": best_image,
            "inLanguage": "en-US",
        }

        # Open Graph - use centralized description
        og = {
            "og:title": headline,
            "og:description": seo_description,  # Use same description as schema
            "og:type": "article",
            "og:url": canonical,
            "og:image": best_image,
            "og:site_name": "Paul Chris Luke - PCL Labs",
        }

        return FrontmatterInfo(
            title=headline,
            date=date_str,
            author=self.author,
            canonical=canonical,
            description=seo_description,
            tags=tags,
            image=best_image,
            schema=schema,
            og=og,
        )

    def _generate_keywords(
        self, stories: List[Any], clips: List[Dict[str, Any]], events: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate up to 10 unified keywords."""
        base = ["ai blog automation", "schema seo", "twitch transcription", "github automation", "devlog"]
        extras = []

        for s in stories:
            st = getattr(s, "story_type", None)
            if not st:
                continue
            v = st.value if hasattr(st, "value") else str(st)
            if v == "feat":
                extras.extend(["features", "caching", "security"])
            elif v == "security":
                extras.extend(["security", "auth", "rate limiting"])
            elif v == "automation":
                extras.extend(["automation", "pipelines"])

        if clips:
            extras.append("twitch clips")
        if events:
            extras.append("github events")

        return list(dict.fromkeys(base + extras))[:10]

    def clean_frontmatter_for_api(self, frontmatter: Dict[str, Any]) -> Dict[str, Any]:
        """Clean frontmatter for API consumption by removing content fields."""
        if not frontmatter:
            return {}
        
        # Create a copy and remove content-related fields
        cleaned = frontmatter.copy()
        
        # Remove fields that are not needed for API consumption
        content_fields_to_remove = ['body', 'content', 'markdown', 'html']
        for field in content_fields_to_remove:
            cleaned.pop(field, None)
        
        return cleaned

    def add_video_objects_to_schema(self, schema: Dict[str, Any], story_packets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add video objects to existing schema."""
        video_objects = []
        
        for packet in story_packets:
            video_data = packet.get("video", {})
            if video_data.get("status") == "rendered" and video_data.get("path"):
                # Get thumbnail URL from existing thumbnails
                thumbnails = video_data.get("thumbnails", {})
                thumbnail_url = ""
                
                # Try to get intro thumbnail first, then fallback to others
                if thumbnails.get("intro"):
                    intro_path = thumbnails["intro"]
                    if not intro_path.startswith("http"):
                        # Use DigestUtils to build absolute thumbnail URL
                        from .digest_utils import DigestUtils
                        utils = DigestUtils(self.media, f"{self.media}/assets/pcl-labs-logo.svg")
                        thumbnail_url = utils.get_cloudflare_url(intro_path)
                    else:
                        thumbnail_url = intro_path
                else:
                    # No intro thumbnail found, try other thumbnails
                    for thumb_type in ["why", "outro", "highlight"]:
                        if thumbnails.get(thumb_type):
                            thumb_path = thumbnails[thumb_type]
                            if not thumb_path.startswith("http"):
                                # Use DigestUtils to build absolute thumbnail URL
                                from .digest_utils import DigestUtils
                                utils = DigestUtils(self.media, f"{self.media}/assets/pcl-labs-logo.svg")
                                thumbnail_url = utils.get_cloudflare_url(thumb_path)
                            else:
                                thumbnail_url = thumb_path
                            break
                
                video_obj = {
                    "@type": "VideoObject",
                    "name": packet.get("title_human", ""),
                    "description": packet.get("why", ""),
                    "contentUrl": video_data["path"],
                    "thumbnailUrl": thumbnail_url,
                    "uploadDate": packet.get("merged_at", ""),
                    "duration": f"PT{video_data.get('duration_s', 90)}S" if video_data.get("duration_s") else "PT90S"
                }
                video_objects.append(video_obj)
        
        # Add video objects to schema if any exist
        if video_objects:
            schema["video"] = video_objects
            
        return schema
