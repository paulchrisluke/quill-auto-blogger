"""
Frontmatter generation for blog posts.
"""

import sys
import yaml
from datetime import datetime
from typing import List, Dict, Any

from story_schema import FrontmatterInfo


class FrontmatterGenerator:
    """Generate frontmatter for blog posts."""
    
    def __init__(self, blog_author: str, blog_base_url: str, worker_domain: str):
        self.blog_author = blog_author
        self.blog_base_url = blog_base_url.rstrip("/")
        self.worker_domain = worker_domain
    
    def generate_frontmatter(
        self, 
        target_date: str, 
        clips_data: List[Dict[str, Any]], 
        events_data: List[Dict[str, Any]], 
        story_packets: List[Any],
        version: str = "v2"
    ) -> FrontmatterInfo:
        """
        Generate frontmatter with specified version.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            clips_data: List of Twitch clip data
            events_data: List of GitHub event data
            story_packets: List of story packets
            version: Frontmatter version ("v1", "v2", "v3")
            
        Returns:
            FrontmatterInfo object
        """
        if version == "v1":
            return self._generate_frontmatter_v1(target_date, clips_data, events_data, story_packets)
        elif version == "v2":
            return self._generate_frontmatter_v2(target_date, clips_data, events_data, story_packets)
        elif version == "v3":
            return self._generate_frontmatter_v3(target_date, clips_data, events_data, story_packets)
        else:
            raise ValueError(f"Unsupported frontmatter version: {version}")
    
    def _generate_frontmatter_v1(self, target_date: str, clips_data: List[Dict[str, Any]], events_data: List[Dict[str, Any]], story_packets: List[Any]) -> str:
        """Generate v1 frontmatter with schema.org metadata."""
        # Parse date
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Generate headline
        headline = f"Daily Devlog — {date_obj.strftime('%b %d, %Y')}"
        
        # Select the best image for this blog post
        from .digest_utils import DigestUtils
        utils = DigestUtils(self.worker_domain, "https://example.com/default.jpg")
        best_image = utils.select_best_image(story_packets)
        
        # Build schema.org Article
        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": headline,
            "datePublished": target_date,
            "author": {
                "@type": "Person",
                "name": self.blog_author
            },
            "keywords": [],  # Will be populated from metadata
            "url": f"{self.blog_base_url}/blog/{target_date}",
            "image": best_image
        }
        
        # Build VideoObject schemas for Twitch clips
        video_objects = []
        for clip in clips_data:
            upload_date = clip.get("created_at")
            if isinstance(upload_date, (datetime, date)):
                upload_date = upload_date.isoformat()
            video_schema = {
                "@type": "VideoObject",
                "name": clip["title"],
                "description": clip.get("transcript", "")[:200] + "..." if clip.get("transcript") else "",
                "url": clip["url"],
                "uploadDate": upload_date,
                "duration": (
                    f"PT{int(round(float(clip.get('duration', 0.0))))}S"
                    if clip.get("duration") is not None else None
                ),
                "thumbnailUrl": f"https://clips-media-assets2.twitch.tv/{clip['id']}/preview-480x272.jpg"
            }
            # Remove None values
            video_schema = {k: v for k, v in video_schema.items() if v is not None}
            video_objects.append(video_schema)
        
        # Build FAQPage schema if there are multiple GitHub events
        faq_schema = None
        if len(events_data) > 1:
            faq_entries = []
            for event in events_data:
                if event.get("title") or event.get("details", {}).get("commit_messages"):
                    question = event.get("title", f"{event.get('type', 'unknown')} in {event.get('repo', '')}")
                    answer = event.get("body", "")
                    if not answer and event.get("details", {}).get("commit_messages"):
                        answer = "\n".join(event.get("details", {}).get("commit_messages", []))
                    
                    if answer:
                        faq_entries.append({
                            "@type": "Question",
                            "name": question,
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": answer
                            }
                        })
            
            if faq_entries:
                faq_schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": faq_entries
                }
        
        # Build Open Graph metadata
        og_metadata = {
            "og:title": headline,
            "og:description": (
                f"Daily development log with {len(clips_data)} "
                f"Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.blog_base_url}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Combine all metadata
        frontmatter_data = {
            "title": headline,
            "date": target_date,
            "author": self.blog_author,
            "schema": {
                "article": article_schema,
                "videos": video_objects
            },
            "og": og_metadata
        }
        
        # Add FAQ schema if available
        if faq_schema:
            frontmatter_data["schema"]["faq"] = faq_schema
        
        # Force long descriptions to be inline to prevent weird wrapping
        if "og" in frontmatter_data and "og:description" in frontmatter_data["og"]:
            desc = frontmatter_data["og"]["og:description"]
            # Only add quotes if not already quoted
            if not (desc.startswith('"') and desc.endswith('"')):
                frontmatter_data["og"]["og:description"] = f'"{desc}"'
        
        # Convert to YAML
        yaml_content = yaml.safe_dump(frontmatter_data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=sys.maxsize)
        
        return f"---\n{yaml_content}---\n"
    
    def _generate_frontmatter_v2(self, target_date: str, clips_data: List[Dict[str, Any]], events_data: List[Dict[str, Any]], story_packets: List[Any]) -> FrontmatterInfo:
        """Generate v2 frontmatter with story packet information."""
        # Parse date
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Generate title
        title = f"Daily Devlog — {date_obj.strftime('%b %d, %Y')}"
        
        # Extract story types for tags
        story_types = [packet.story_type.value for packet in story_packets]
        unique_types = list(set(story_types))
        
        # Generate lead based on story packets
        lead = self._generate_lead(story_packets)
        
        # Select the best image for this blog post
        from .digest_utils import DigestUtils
        utils = DigestUtils(self.worker_domain, "https://example.com/default.jpg")
        best_image = utils.select_best_image(story_packets)
        
        # Build Open Graph metadata
        og_metadata = {
            "og:title": title,
            "og:description": (
                f"Daily development log with {len(story_packets)} "
                f"{'story' if len(story_packets)==1 else 'stories'} from "
                f"{len(clips_data)} Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.blog_base_url}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Build schema.org metadata
        schema_metadata = {
            "article": {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": title,
                "datePublished": target_date,
                "author": {
                    "@type": "Person",
                    "name": self.blog_author
                },
                "keywords": unique_types,
                "url": f"{self.blog_base_url}/blog/{target_date}",
                "image": best_image
            }
        }
        
        return FrontmatterInfo(
            title=title,
            date=target_date,
            author=self.blog_author,
            og=og_metadata,
            schema=schema_metadata,
            tags=unique_types,
            lead=lead
        )
    
    def _generate_frontmatter_v3(self, target_date: str, clips_data: List[Dict[str, Any]], events_data: List[Dict[str, Any]], story_packets: List[Any]) -> FrontmatterInfo:
        """Generate v3 frontmatter that matches the exact requirements specification."""
        # Parse date
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Generate title
        title = f"Daily Devlog — {date_obj.strftime('%B %d, %Y')}"
        
        # Extract story types for tags
        story_types = [packet.story_type.value for packet in story_packets]
        unique_types = list(set(story_types))
        
        # Generate lead based on story packets
        lead = self._generate_lead(story_packets)
        
        # Select the best image for this blog post
        from .digest_utils import DigestUtils
        utils = DigestUtils(self.worker_domain, "https://example.com/default.jpg")
        best_image = utils.select_best_image(story_packets)
        
        # Build Open Graph metadata with correct asset paths
        og_metadata = {
            "og:title": title,
            "og:description": (
                f"Daily development log with {len(story_packets)} "
                f"{'story' if len(story_packets)==1 else 'stories'} from "
                f"{len(clips_data)} Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.blog_base_url}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Build schema.org metadata with correct asset paths
        schema_metadata = {
            "article": {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": title,
                "datePublished": target_date,
                "author": {
                    "@type": "Person",
                    "name": self.blog_author
                },
                "keywords": unique_types,
                "url": f"{self.blog_base_url}/blog/{target_date}",
                "image": best_image
            }
        }
        
        return FrontmatterInfo(
            title=title,
            date=target_date,
            author=self.blog_author,
            og=og_metadata,
            schema=schema_metadata,
            tags=unique_types,
            lead=lead
        )
    
    def _generate_lead(self, story_packets: List[Any]) -> str:
        """Generate a lead paragraph from story packets."""
        if not story_packets:
            return ""
        
        # Count story types
        type_counts = {}
        for packet in story_packets:
            story_type = packet.story_type.value
            type_counts[story_type] = type_counts.get(story_type, 0) + 1
        
        # Generate lead based on most common types
        if len(story_packets) == 1:
            packet = story_packets[0]
            return f"Today's development work focused on {packet.title_human.lower()}."
        
        # Multiple stories
        total_stories = len(story_packets)
        if type_counts.get("feat", 0) > 0 and type_counts.get("security", 0) > 0:
            return f"Shipped {type_counts['feat']} new feature{'s' if type_counts['feat'] > 1 else ''} and enhanced security today."
        elif type_counts.get("feat", 0) > 0:
            return f"Shipped {type_counts['feat']} new feature{'s' if type_counts['feat'] > 1 else ''} today."
        elif type_counts.get("fix", 0) > 0:
            return f"Fixed {type_counts['fix']} issue{'s' if type_counts['fix'] > 1 else ''} and improved the codebase."
        elif type_counts.get("security", 0) > 0:
            return f"Enhanced security with {type_counts['security']} improvement{'s' if type_counts['security'] > 1 else ''}."
        else:
            return f"Completed {total_stories} development task{'s' if total_stories > 1 else ''} today."
    
    def clean_frontmatter_for_api(self, frontmatter: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean frontmatter to remove content fields, keeping only metadata.
        
        Args:
            frontmatter: Original frontmatter dictionary
            
        Returns:
            Cleaned frontmatter with only metadata fields
        """
        # Fields to keep (metadata only)
        metadata_fields = {
            'title', 'date', 'author', 'og', 'schema', 'tags', 'lead', 'description'
        }
        
        # Fields to remove (content that should be in content.body)
        content_fields = {
            'holistic_intro', 'wrap_up'
        }
        
        cleaned = {}
        for key, value in frontmatter.items():
            if key in metadata_fields:
                cleaned[key] = value
            elif key in content_fields:
                # Skip content fields - they'll be integrated into content.body
                continue
            else:
                # Keep other fields that might be metadata
                cleaned[key] = value
        
        return cleaned
