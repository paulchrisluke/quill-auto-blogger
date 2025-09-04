"""
Frontmatter generation for blog posts.
"""

import sys
import yaml
from datetime import datetime, date
from typing import List, Dict, Any, Union

from story_schema import FrontmatterInfo


class FrontmatterGenerator:
    """Generate frontmatter for blog posts."""
    
    def __init__(self, blog_author: str, blog_base_url: str, worker_domain: str, frontend_domain: str = None):
        self.blog_author = blog_author
        self.blog_base_url = blog_base_url.rstrip("/")
        self.worker_domain = worker_domain
        # Use frontend_domain if provided, otherwise fall back to blog_base_url
        self.frontend_domain = frontend_domain.rstrip("/") if frontend_domain else self.blog_base_url
    
    def generate_frontmatter(
        self, 
        target_date: str, 
        clips_data: List[Dict[str, Any]], 
        events_data: List[Dict[str, Any]], 
        story_packets: List[Any],
        version: str = "v2"
    ) -> Union[str, FrontmatterInfo]:
        """
        Generate frontmatter with specified version.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            clips_data: List of Twitch clip data
            events_data: List of GitHub event data
            story_packets: List of story packets
            version: Frontmatter version ("v1", "v2", "v3")
            
        Returns:
            FrontmatterInfo object for v2/v3, YAML string for v1
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
        
        # Build schema.org Article with canonical URL
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
            "url": f"{self.frontend_domain}/blog/{target_date}",
            "image": best_image
        }
        
        # Build VideoObject schemas for Twitch clips
        video_objects = []
        for clip in clips_data:
            upload_date = clip.get("created_at")
            if isinstance(upload_date, (datetime, datetime.date)):
                upload_date = upload_date.isoformat()
            video_schema = {
                "@type": "VideoObject",
                "name": clip["title"],
                "description": clip.get("transcript", "")[:200] + "..." if clip.get("transcript") else "",
                "url": clip["url"],
                "uploadDate": upload_date,
                "duration": (
                    f"PT{int(round(float(clip.get('duration', 0.0))))}S"
                    if clip.get('duration') is not None else None
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
        
        # Build Open Graph metadata with canonical URL
        og_metadata = {
            "og:title": headline,
            "og:description": (
                f"Daily development log with {len(clips_data)} "
                f"Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.frontend_domain}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Combine all metadata
        frontmatter_data = {
            "title": headline,
            "date": target_date,
            "author": self.blog_author,
            "canonical": f"{self.frontend_domain}/blog/{target_date}",
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
        
        # Build Open Graph metadata with canonical URL
        og_metadata = {
            "og:title": title,
            "og:description": (
                f"Daily development log with {len(story_packets)} "
                f"{'story' if len(story_packets)==1 else 'stories'} from "
                f"{len(clips_data)} Twitch {'clip' if len(clips_data)==1 else 'clips'} and "
                f"{len(events_data)} GitHub {'event' if len(events_data)==1 else 'events'}"
            ),
            "og:type": "article",
            "og:url": f"{self.frontend_domain}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Build schema.org metadata with canonical URL
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
                "url": f"{self.frontend_domain}/blog/{target_date}",
                "image": best_image
            }
        }
        
        return FrontmatterInfo(
            title=title,
            date=target_date,
            author=self.blog_author,
            canonical=f"{self.frontend_domain}/blog/{target_date}",
            og=og_metadata,
            schema=schema_metadata,
            tags=unique_types,
            lead=lead
        )
    
    def _generate_frontmatter_v3(self, target_date: str, clips_data: List[Dict[str, Any]], events_data: List[Dict[str, Any]], story_packets: List[Any]) -> FrontmatterInfo:
        """Generate v3 frontmatter with enhanced BlogPosting schema and rich content."""
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
        
        # Generate description from lead and content summary
        description = self._generate_description(lead, story_packets, clips_data, events_data)
        
        # Build Open Graph metadata with canonical URL
        og_metadata = {
            "og:title": title,
            "og:description": description,
            "og:type": "article",
            "og:url": f"{self.frontend_domain}/blog/{target_date}",
            "og:image": best_image,
            "og:site_name": "Daily Devlog"
        }
        
        # Build enhanced BlogPosting schema with rich content
        blog_posting_schema = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "description": description,
            "author": {
                "@type": "Person",
                "name": self.blog_author,
                "url": f"{self.frontend_domain}/about"
            },
            "datePublished": target_date,
            "dateModified": target_date,  # Same as published for now
            "url": f"{self.frontend_domain}/blog/{target_date}",
            "mainEntityOfPage": f"{self.frontend_domain}/blog/{target_date}",
            "publisher": {
                "@type": "Organization",
                "name": "PCL Labs",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{self.frontend_domain}/pcl-labs-logo.svg"
                }
            },
            "image": best_image,
            "keywords": unique_types,
            "wordCount": self._estimate_word_count(story_packets, clips_data, events_data)
        }
        
        # Add rich content schemas
        rich_content = self._generate_rich_content_schemas(story_packets, clips_data)
        if rich_content:
            blog_posting_schema.update(rich_content)
        
        # Build schema.org metadata
        schema_metadata = {
            "blogPosting": blog_posting_schema
        }
        
        return FrontmatterInfo(
            title=title,
            date=target_date,
            author=self.blog_author,
            canonical=f"{self.frontend_domain}/blog/{target_date}",
            og=og_metadata,
            schema=schema_metadata,
            tags=unique_types,
            lead=lead,
            description=description
        )
    
    def _generate_lead(self, story_packets: List[Any]) -> str:
        """Generate a lead paragraph from story packets."""
        if not story_packets:
            return ""
        
        # Count story types
        type_counts = {}
        for packet in story_packets:
            story_type_obj = getattr(packet, "story_type", None)
            if story_type_obj and hasattr(story_type_obj, "value"):
                story_type = story_type_obj.value
            else:
                story_type = "unknown"
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
    
    def _generate_description(self, lead: str, story_packets: List[Any], clips_data: List[Dict[str, Any]], events_data: List[Dict[str, Any]]) -> str:
        """Generate a comprehensive description for the blog post."""
        if lead:
            return lead
        
        # Fallback description based on content
        story_count = len(story_packets)
        clip_count = len(clips_data)
        event_count = len(events_data)
        
        if story_count > 0:
            return f"Daily development log with {story_count} {'story' if story_count == 1 else 'stories'} from {clip_count} Twitch {'clip' if clip_count == 1 else 'clips'} and {event_count} GitHub {'event' if event_count == 1 else 'events'}."
        else:
            return f"Daily development log with {clip_count} Twitch {'clip' if clip_count == 1 else 'clips'} and {event_count} GitHub {'event' if event_count == 1 else 'events'}."
    
    def _estimate_word_count(self, story_packets: List[Any], clips_data: List[Dict[str, Any]], events_data: List[Dict[str, Any]]) -> int:
        """Estimate word count for the blog post."""
        word_count = 0
        
        # Base content (intro, wrap-up, etc.)
        word_count += 200
        
        # Story packets
        for packet in story_packets:
            if hasattr(packet, 'ai_comprehensive_intro') and packet.ai_comprehensive_intro:
                word_count += len(packet.ai_comprehensive_intro.split())
            if hasattr(packet, 'why') and packet.why:
                word_count += len(packet.why.split())
            if hasattr(packet, 'highlights') and packet.highlights:
                for highlight in packet.highlights:
                    word_count += len(highlight.split())
        
        # Twitch clips
        for clip in clips_data:
            if clip.get('transcript'):
                word_count += len(clip['transcript'].split())
        
        # GitHub events
        for event in events_data:
            if event.get('body'):
                word_count += len(event['body'].split())
            if event.get('details', {}).get('commit_messages'):
                for message in event['details']['commit_messages']:
                    word_count += len(message.split())
        
        return max(word_count, 100)  # Minimum 100 words
    
    def _generate_rich_content_schemas(self, story_packets: List[Any], clips_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate rich content schemas for videos and images."""
        rich_content = {}
        
        # Generate VideoObject schemas for story packets with videos
        video_objects = []
        for packet in story_packets:
            if hasattr(packet, 'video') and packet.video and hasattr(packet.video, 'status') and packet.video.status == 'rendered':
                video_schema = {
                    "@type": "VideoObject",
                    "name": getattr(packet, 'title_human', 'Story Video'),
                    "description": getattr(packet, 'why', '')[:200] + "..." if getattr(packet, 'why', '') else "",
                    "url": getattr(packet.video, 'path', None),
                    "uploadDate": getattr(packet, 'merged_at', ''),
                    "thumbnailUrl": getattr(packet.video.thumbnails, 'intro', None) if hasattr(packet.video, 'thumbnails') else None
                }
                # Remove None values
                video_schema = {k: v for k, v in video_schema.items() if v is not None}
                if video_schema:
                    video_objects.append(video_schema)
        
        # Generate VideoObject schemas for Twitch clips
        for clip in clips_data:
            upload_date = clip.get("created_at")
            if isinstance(upload_date, (datetime, datetime.date)):
                upload_date = upload_date.isoformat()
            
            video_schema = {
                "@type": "VideoObject",
                "name": clip.get("title", "Twitch Clip"),
                "description": clip.get("transcript", "")[:200] + "..." if clip.get("transcript") else "",
                "url": clip.get("url"),
                "uploadDate": upload_date,
                "duration": (
                    f"PT{int(round(float(clip.get('duration', 0.0))))}S"
                    if clip.get('duration') is not None else None
                ),
                "thumbnailUrl": f"https://clips-media-assets2.twitch.tv/{clip['id']}/preview-480x272.jpg" if clip.get('id') else None
            }
            # Remove None values
            video_schema = {k: v for k, v in video_schema.items() if v is not None}
            if video_schema:
                video_objects.append(video_schema)
        
        if video_objects:
            rich_content["video"] = video_objects
        
        # Generate ImageObject schemas for story thumbnails
        image_objects = []
        for packet in story_packets:
            if hasattr(packet, 'video') and packet.video and hasattr(packet.video, 'thumbnails'):
                thumbnails = packet.video.thumbnails
                # Convert Pydantic model to dict for iteration
                if hasattr(thumbnails, 'model_dump'):
                    thumbnails_dict = thumbnails.model_dump()
                else:
                    thumbnails_dict = thumbnails.__dict__
                
                for thumbnail_type, thumbnail_path in thumbnails_dict.items():
                    if thumbnail_path:
                        image_schema = {
                            "@type": "ImageObject",
                            "name": f"{getattr(packet, 'title_human', 'Story')} - {thumbnail_type.title()}",
                            "url": f"{self.worker_domain}/assets/{thumbnail_path}",
                            "description": f"{thumbnail_type.title()} thumbnail for {getattr(packet, 'title_human', 'story')}"
                        }
                        image_objects.append(image_schema)
        
        if image_objects:
            rich_content["image"] = image_objects
        
        return rich_content
