"""
Content generation for blog posts.
"""

import html
import re
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class ContentGenerator:
    """Generate and post-process blog content."""
    
    def __init__(self, digest: Dict[str, Any], utils):
        self.digest = digest
        self.utils = utils
        self.target_date = digest["date"]
        self.frontmatter = digest.get("frontmatter", {})
        self.story_packets = digest.get("story_packets", [])
        self.clips = digest.get("twitch_clips", [])
        self.events = digest.get("github_events", [])
    
    def generate(self, ai_enabled: bool = True, force_ai: bool = False, related_enabled: bool = True) -> str:
        """
        Generate bare scaffold blog content with placeholders for AI enhancement.
        
        Args:
            ai_enabled: Whether to enable AI-assisted content generation
            force_ai: Whether to ignore cache and force AI regeneration
            related_enabled: Whether to include related posts block
            
        Returns:
            Complete blog content as a single string
        """
        content_parts = []
        
        # 1. Holistic intro placeholder (will be filled by AI)
        content_parts.append("[AI_HOLISTIC_INTRO]")
        content_parts.append("")
        
        # 2. Lead paragraph (if available)
        if self.frontmatter.get("lead"):
            content_parts.append(self.frontmatter["lead"])
            content_parts.append("")
        
        # 3. Stories section with minimal structure
        if self.story_packets:
            content_parts.append("## Stories")
            content_parts.append("")
            
            # Group by story type
            stories_by_type = {}
            for packet in self.story_packets:
                story_type = packet.get("story_type", "other")
                if story_type not in stories_by_type:
                    stories_by_type[story_type] = []
                stories_by_type[story_type].append(packet)
            
            # Story type display names
            type_names = {
                "feat": "New Features",
                "fix": "Bug Fixes", 
                "perf": "Performance",
                "security": "Security",
                "infra": "Infrastructure",
                "docs": "Documentation",
                "other": "Other"
            }
            
            for story_type, packets in stories_by_type.items():
                if story_type in type_names:
                    content_parts.append(f"### {type_names[story_type]}")
                    content_parts.append("")
                    
                    for packet in packets:
                        content_parts.append(f"#### {packet.get('title_human', packet.get('title_raw', 'Untitled'))}")
                        content_parts.append("")
                        
                        # Add AI comprehensive intro if available
                        if packet.get('ai_comprehensive_intro'):
                            content_parts.append(packet['ai_comprehensive_intro'])
                            content_parts.append("")
                        
                        # Add highlights as simple list
                        if packet.get('highlights'):
                            for highlight in packet['highlights']:
                                content_parts.append(f"- {highlight}")
                            content_parts.append("")
                        
                        # Add video placeholder
                        if (packet.get('video', {}).get('path') and 
                            packet.get('video', {}).get('status') == 'rendered'):
                            video_path = packet['video']['path']
                            content_parts.append(f"[video: {video_path}]")
                            content_parts.append("")
                        
                        # Add PR placeholder
                        if packet.get('links', {}).get('pr_url'):
                            pr_url = packet['links']['pr_url']
                            content_parts.append(f"[pr: {pr_url}]")
                            content_parts.append("")
                        
                        content_parts.append("---")
                        content_parts.append("")
        
        # 4. Twitch clips section (if not covered by stories)
        if self.clips and not self.story_packets:
            content_parts.append("## Twitch Clips")
            content_parts.append("")
            
            for clip in self.clips:
                content_parts.append(f"### {clip.get('title', 'Untitled Clip')}")
                content_parts.append(f"[clip: {clip.get('url', '')}]")
                content_parts.append("")
        
        # 5. GitHub events section (if not covered by stories)
        if self.events and not self.story_packets:
            content_parts.append("## GitHub Activity")
            content_parts.append("")
            
            for event in self.events:
                content_parts.append(f"### {event.get('type', 'unknown')} in {event.get('repo', '')}")
                content_parts.append(f"[event: {event.get('url', '')}]")
                content_parts.append("")
        
        # 6. Wrap-up placeholder (will be filled by AI if not in frontmatter)
        wrap_up_existing = (self.frontmatter.get("wrap_up") or "").strip()
        if wrap_up_existing:
            content_parts.append("")
            content_parts.append("## Wrap-Up")
            content_parts.append("")
            content_parts.append(wrap_up_existing)
            content_parts.append("")
        else:
            content_parts.append("[AI_WRAP_UP]")
            content_parts.append("")
        
        # 7. Related posts are handled in structured data, not markdown
        
        # 8. Add signature
        content_parts.extend(self._get_signature())
        
        # Generate the base markdown
        markdown = "\n".join(content_parts)
        
        # Post-process with AI enhancements
        return self.post_process_markdown(markdown, ai_enabled, force_ai)
    
    
    def _get_signature(self) -> List[str]:
        """Get the blog signature."""
        return [
            "\n---",
            "",
            "[https://upwork.com/freelancers/paulchrisluke](https://upwork.com/freelancers/paulchrisluke)",
            "",
            "_Hi. I'm Chris. I'm a morally ambiguous technology marketer and builder at PCL Labs. I turn raw events into stories with wit, irreverence, and emotional honesty. I help solve complex technical challenges through AI blog automation, schema-driven SEO, and developer workflow optimization. Book me on_ [Upwork](https://upwork.com/freelancers/paulchrisluke) _or find someone who knows how to get ahold of me._"
        ]
    
    def post_process_markdown(self, markdown: str, ai_enabled: bool, force_ai: bool) -> str:
        """
        Post-process markdown with AI inserts and enhancements.
        
        Args:
            markdown: Raw markdown content with placeholders
            ai_enabled: Whether AI is enabled
            force_ai: Whether to force AI regeneration
            
        Returns:
            Enhanced markdown content
        """
        if not ai_enabled:
            # Still need to replace placeholders even without AI
            return self._replace_placeholders(markdown)
        
        try:
            from .ai_inserts import AIInsertsService
            
            # Initialize AI service
            ai_service = AIInsertsService()
            
            # Prepare inputs for AI
            story_titles = [packet.get("title_human", "") for packet in self.story_packets]
            inputs = {
                "title": self.frontmatter.get("title", ""),
                "tags_csv": ",".join(self.frontmatter.get("tags", [])),
                "lead": self.frontmatter.get("lead", ""),
                "story_titles_csv": ",".join(story_titles)
            }
            
            # 1. SEO Description
            seo_description = ai_service.make_seo_description(self.target_date, inputs, force_ai)
            
            # Update frontmatter og:description
            if "og" not in self.frontmatter:
                self.frontmatter["og"] = {}
            self.frontmatter["og"]["og:description"] = seo_description
            
            # Set frontmatter description
            if "description" not in self.frontmatter:
                self.frontmatter["description"] = seo_description
            
            # Update frontmatter images with smart selection
            best_image = self.utils.select_best_image(self.story_packets)
            if "og" in self.frontmatter:
                self.frontmatter["og"]["og:image"] = best_image
            # Update schema image (support both article and blogPosting schemas)
            if "schema" in self.frontmatter:
                if "article" in self.frontmatter["schema"]:
                    self.frontmatter["schema"]["article"]["image"] = best_image
                elif "blogPosting" in self.frontmatter["schema"]:
                    self.frontmatter["schema"]["blogPosting"]["image"] = best_image
            
            # 2. Title punch-up (optional)
            current_title = self.frontmatter.get("title", "")
            improved_title = ai_service.punch_up_title(self.target_date, current_title, force_ai)
            
            if improved_title:
                # Update frontmatter and H1
                self.frontmatter["title"] = improved_title
                # Also update og:title and headline in frontmatter
                if "og" in self.frontmatter:
                    self.frontmatter["og"]["og:title"] = improved_title
                # Update schema headline (support both article and blogPosting schemas)
                if "schema" in self.frontmatter:
                    if "article" in self.frontmatter["schema"]:
                        self.frontmatter["schema"]["article"]["headline"] = improved_title
                    elif "blogPosting" in self.frontmatter["schema"]:
                        self.frontmatter["schema"]["blogPosting"]["headline"] = improved_title
                markdown = self._update_title_in_markdown(markdown, improved_title)
            
            # 3. Generate holistic intro and wrap-up
            holistic_intro = ai_service.make_holistic_intro(self.target_date, inputs, force_ai)
            if holistic_intro:
                markdown = markdown.replace("[AI_HOLISTIC_INTRO]", holistic_intro)
            
            # Only generate wrap-up if one doesn't already exist in frontmatter (trimmed)
            if not self.frontmatter.get("wrap_up", "").strip():
                wrap_up = ai_service.make_wrap_up(self.target_date, inputs, force_ai)
                if wrap_up:
                    markdown = markdown.replace("[AI_WRAP_UP]", f"## Wrap-Up\n\n{wrap_up}")
            
            # 4. Generate AI-suggested tags
            suggested_tags = ai_service.suggest_tags(self.target_date, inputs, force_ai)
            if suggested_tags:
                # Merge with existing tags, avoiding duplicates
                existing_tags = set(self.frontmatter.get("tags", []))
                existing_tags.update(suggested_tags)
                self.frontmatter["tags"] = list(existing_tags)
                
                # Also update schema keywords
                if "schema" in self.frontmatter and "article" in self.frontmatter["schema"]:
                    self.frontmatter["schema"]["article"]["keywords"] = list(existing_tags)
            
            # 5. Replace all placeholders with AI-generated content
            markdown = self._replace_placeholders_with_ai(markdown, ai_service, force_ai)
            
            return markdown
            
        except Exception as e:
            logger.warning(f"Post-processing failed: {e}")
            # Still try to replace placeholders even on error
            return self._replace_placeholders(markdown)
    
    def _update_title_in_markdown(self, markdown: str, new_title: str) -> str:
        """Update both frontmatter and H1 title."""
        # Update H1
        h1_pattern = r"^(# ).+$"
        replacement = r"\1" + new_title
        markdown = re.sub(h1_pattern, replacement, markdown, flags=re.MULTILINE)
        
        # Update og:title (exact format: 2 spaces + og:title:)
        og_title_pattern = r"^  og:title:\s*.+$"
        replacement = f"  og:title: {new_title}"
        markdown = re.sub(og_title_pattern, replacement, markdown, flags=re.MULTILINE)
        
        # Update schema.article.headline (exact format: 4 spaces + headline:)
        headline_pattern = r"^    headline:\s*.+$"
        replacement = f"    headline: {new_title}"
        markdown = re.sub(headline_pattern, replacement, markdown, flags=re.MULTILINE)
        
        return markdown
    
    def _replace_placeholders(self, markdown: str) -> str:
        """Replace placeholders with basic content when AI is disabled."""
        # Replace video placeholders with simple links
        def replace_video_safe(match):
            video_path = match.group(1)
            if self._is_safe_url(video_path):
                return f'**Video:** [Watch Story]({video_path})'
            else:
                return f'**Video:** Watch Story'
        markdown = re.sub(r'\[video: ([^\]]+)\]', replace_video_safe, markdown)
        
        # Replace PR placeholders with simple links
        def replace_pr_safe(match):
            pr_url = match.group(1)
            if self._is_safe_url(pr_url):
                return f'**PR:** [{pr_url}]({pr_url})'
            else:
                return f'**PR:** {pr_url}'
        markdown = re.sub(r'\[pr: ([^\]]+)\]', replace_pr_safe, markdown)
        
        # Replace clip placeholders with simple links
        def replace_clip_safe(match):
            clip_url = match.group(1)
            if self._is_safe_url(clip_url):
                return f'**Clip:** [Watch]({clip_url})'
            else:
                return f'**Clip:** Watch'
        markdown = re.sub(r'\[clip: ([^\]]+)\]', replace_clip_safe, markdown)
        
        # Replace event placeholders with simple links
        def replace_event_safe(match):
            event_url = match.group(1)
            if self._is_safe_url(event_url):
                return f'**Event:** [View]({event_url})'
            else:
                return f'**Event:** View'
        markdown = re.sub(r'\[event: ([^\]]+)\]', replace_event_safe, markdown)
        
        # Remove AI placeholders
        markdown = markdown.replace("[AI_HOLISTIC_INTRO]", "")
        markdown = markdown.replace("[AI_WRAP_UP]", "")
        
        return markdown
    
    def _replace_placeholders_with_ai(self, markdown: str, ai_service, force_ai: bool = False) -> str:
        """Replace placeholders with AI-generated content."""
        # Replace video placeholders with AI-generated video descriptions
        def replace_video(match):
            video_path = match.group(1)
            # Generate AI description for the video
            video_description = self._generate_video_description(video_path, ai_service, force_ai)
            return video_description
        
        markdown = re.sub(r'\[video: ([^\]]+)\]', replace_video, markdown)
        
        # Replace PR placeholders with AI-generated PR descriptions
        def replace_pr(match):
            pr_url = match.group(1)
            # Generate AI description for the PR
            pr_description = self._generate_pr_description(pr_url, ai_service, force_ai)
            return pr_description
        
        markdown = re.sub(r'\[pr: ([^\]]+)\]', replace_pr, markdown)
        
        # Replace clip placeholders with AI-generated clip descriptions
        def replace_clip(match):
            clip_url = match.group(1)
            # Generate AI description for the clip
            clip_description = self._generate_clip_description(clip_url, ai_service, force_ai)
            return clip_description
        
        markdown = re.sub(r'\[clip: ([^\]]+)\]', replace_clip, markdown)
        
        # Replace event placeholders with AI-generated event descriptions
        def replace_event(match):
            event_url = match.group(1)
            # Generate AI description for the event
            event_description = self._generate_event_description(event_url, ai_service, force_ai)
            return event_description
        
        markdown = re.sub(r'\[event: ([^\]]+)\]', replace_event, markdown)
        
        return markdown
    
    def _generate_video_description(self, video_path: str, ai_service, force_ai: bool = False) -> str:
        """Generate AI description for a video."""
        try:
            # Convert video path to proper URL format
            if video_path.startswith('out/videos/'):
                # Convert to public stories URL with consistent format
                path_parts = video_path.split('/')
                if len(path_parts) >= 3:
                    try:
                        date_part = path_parts[2]  # Get date from out/videos/YYYY-MM-DD/
                        filename = path_parts[-1]  # Get filename
                        # Convert to YYYY/MM/DD format
                        date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                        public_path = f"stories/{date_obj.strftime('%Y/%m/%d')}/{filename}"
                        video_path = public_path
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse video path {video_path}: {e}")
                        pass
            
            # Convert to Cloudflare R2 URL for API consumption
            if video_path.startswith('stories/') or video_path.startswith('/stories/'):
                # Remove leading slash if present
                clean_path = video_path.lstrip('/')
                cloudflare_url = self.utils.get_cloudflare_url(clean_path)
                video_path = cloudflare_url
            
            # Generate thumbnail URL for the video
            thumbnail_url = self.utils.get_video_thumbnail_url(video_path, "")
            
            if video_path.startswith(('https://', '/stories/')):
                # Escape video path for HTML attribute to prevent XSS
                escaped_video_path = html.escape(video_path, quote=True)
                
                if thumbnail_url:
                    # Escape thumbnail URL for HTML attribute to prevent XSS
                    escaped_thumbnail_url = html.escape(thumbnail_url, quote=True)
                    return f'<video controls poster="{escaped_thumbnail_url}" src="{escaped_video_path}"></video>'
                else:
                    return f'<video controls src="{escaped_video_path}"></video>'
            else:
                # For non-secure paths, just show the link
                return f"**Video:** [Watch Story]({video_path})"
                
        except Exception as e:
            logger.warning(f"Failed to generate video description: {e}")
            return f"**Video:** [Watch Story]({video_path})"
    
    def _generate_pr_description(self, pr_url: str, ai_service, force_ai: bool = False) -> str:
        """Generate AI description for a PR."""
        try:
            # Sanitize PR URL to prevent markdown/script injection
            if self._is_safe_url(pr_url):
                return f"**PR:** [{pr_url}]({pr_url})"
            else:
                logger.warning(f"Skipping unsafe PR URL: {pr_url}")
                return f"**PR:** {pr_url}"
        except Exception as e:
            logger.warning(f"Failed to generate PR description: {e}")
            return f"**PR:** {pr_url}"
    
    def _generate_clip_description(self, clip_url: str, ai_service, force_ai: bool = False) -> str:
        """Generate AI description for a Twitch clip."""
        try:
            # Find the clip data
            clip_data = None
            for clip in self.clips:
                if clip.get('url') == clip_url:
                    clip_data = clip
                    break
            
            if clip_data:
                if self._is_safe_url(clip_url):
                    description = f"**Clip:** [Watch]({clip_url})"
                else:
                    description = f"**Clip:** Watch"
                if clip_data.get('duration') is not None:
                    description += f" ({clip_data['duration']}s)"
                if clip_data.get('view_count'):
                    description += f" - {clip_data['view_count']} views"
                return description
            else:
                if self._is_safe_url(clip_url):
                    return f"**Clip:** [Watch]({clip_url})"
                else:
                    return f"**Clip:** Watch"
        except Exception as e:
            logger.warning(f"Failed to generate clip description: {e}")
            if self._is_safe_url(clip_url):
                return f"**Clip:** [Watch]({clip_url})"
            else:
                return f"**Clip:** Watch"
    
    def _generate_event_description(self, event_url: str, ai_service, force_ai: bool = False) -> str:
        """Generate AI description for a GitHub event."""
        try:
            # Find the event data
            event_data = None
            for event in self.events:
                if event.get('url') == event_url:
                    event_data = event
                    break
            
            if event_data:
                if self._is_safe_url(event_url):
                    description = f"**Event:** [View]({event_url})"
                else:
                    description = f"**Event:** View"
                if event_data.get('actor'):
                    description += f" by {event_data['actor']}"
                return description
            else:
                if self._is_safe_url(event_url):
                    return f"**Event:** [View]({event_url})"
                else:
                    return f"**Event:** View"
        except Exception as e:
            logger.warning(f"Failed to generate event description: {e}")
            if self._is_safe_url(event_url):
                return f"**Event:** [View]({event_url})"
            else:
                return f"**Event:** View"
    
    def _is_safe_url(self, url: str) -> bool:
        """
        Check if a URL is safe for markdown rendering.
        
        Args:
            url: URL string to validate
            
        Returns:
            True if URL is safe, False otherwise
        """
        if not url or not isinstance(url, str):
            return False
        
        # Only allow http/https schemes
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Check for potentially dangerous characters that could break markdown
        dangerous_chars = ['<', '>', '"', "'", '`', '\\', '{', '}', '[', ']', '|']
        if any(char in url for char in dangerous_chars):
            return False
        
        # Basic URL format validation
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
        except Exception:
            return False
        
        return True
