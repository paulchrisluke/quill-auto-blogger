"""
Frontmatter generation for blog posts.
"""

from datetime import datetime
from typing import List, Dict, Any
from story_schema import FrontmatterInfo
from .digest_utils import DigestUtils


class FrontmatterGenerator:
    """Generate clean frontmatter for blog posts."""

    def __init__(self, author: str, base_url: str, media_domain: str, frontend_domain: str = None):
        self.author = author
        self.base_url = base_url.rstrip("/")
        self.media = media_domain
        self.frontend = frontend_domain.rstrip("/") if frontend_domain else self.base_url

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

        # Best image from stories
        utils = DigestUtils(self.media, f"{self.media}/default.jpg")
        best_image = utils.select_best_image(stories)

        # Placeholders for AI
        seo_description = "[AI_GENERATE_SEO_DESCRIPTION]"
        lead = "[AI_GENERATE_LEAD]"

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
                "@id": "https://paulchrisluke.com#author",
                "name": self.author,
                "url": "https://paulchrisluke.com"
            },
            "publisher": {
                "@type": "Organization",
                "@id": "https://paulchrisluke.com#organization", 
                "name": "PCL Labs",
                "url": "https://paulchrisluke.com",
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://media.paulchrisluke.com/assets/pcl-labs-logo.png",
                    "width": 200,
                    "height": 200
                }
            },
            "keywords": tags,
            "url": f"{self.frontend}/blog/{date_str}",
            "image": best_image,
            "inLanguage": "en-US",
        }

        # Open Graph - use centralized description
        og = {
            "og:title": headline,
            "og:description": seo_description,  # Use same description as schema
            "og:type": "article",
            "og:url": f"{self.frontend}/blog/{date_str}",
            "og:image": best_image,
            "og:site_name": "Paul Chris Luke - PCL Labs",
        }

        return FrontmatterInfo(
            title=headline,
            date=date_str,
            author=self.author,
            canonical=f"{self.frontend}/blog/{date_str}",
            description=seo_description,
            tags=tags,
            lead=lead,
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
                        # Convert from blogs/2025-08-27/story_... to stories/2025/08/27/story_...
                        if intro_path.startswith("blogs/"):
                            date_part = intro_path.split("/")[1]  # 2025-08-27
                            year, month, day = date_part.split("-")
                            filename = intro_path.split('/', 2)[2]  # story_story_20250827_pr34_01_intro.jpg
                            new_path = f"stories/{year}/{month}/{day}/{filename}"
                            thumbnail_url = f"{self.media}/{new_path}"
                        else:
                            thumbnail_url = f"{self.media}/{intro_path}"
                    else:
                        thumbnail_url = intro_path
                else:
                    # No intro thumbnail found, try other thumbnails
                    for thumb_type in ["why", "outro", "highlight"]:
                        if thumbnails.get(thumb_type):
                            thumb_path = thumbnails[thumb_type]
                            if not thumb_path.startswith("http"):
                                if thumb_path.startswith("blogs/"):
                                    date_part = thumb_path.split("/")[1]
                                    year, month, day = date_part.split("-")
                                    filename = thumb_path.split('/', 2)[2]
                                    new_path = f"stories/{year}/{month}/{day}/{filename}"
                                    thumbnail_url = f"{self.media}/{new_path}"
                                else:
                                    thumbnail_url = f"{self.media}/{thumb_path}"
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
