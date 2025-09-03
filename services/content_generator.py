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
        Generate complete blog content with optional AI enhancements.
        
        Args:
            ai_enabled: Whether to enable AI-assisted content generation
            force_ai: Whether to ignore cache and force AI regeneration
            related_enabled: Whether to include related posts block
            
        Returns:
            Complete blog content as a single string
        """
        content_parts = []
        
        # 1. Holistic intro (if available)
        if self.frontmatter.get("holistic_intro"):
            content_parts.append(self.frontmatter["holistic_intro"])
            content_parts.append("")
        
        # 2. Lead paragraph (if available)
        if self.frontmatter.get("lead"):
            content_parts.append(self.frontmatter["lead"])
            content_parts.append("")
        
        # 3. Summary paragraph
        content_parts.append(
            f"Today's development activities include {len(self.clips)} Twitch "
            f"{'clip' if len(self.clips)==1 else 'clips'} and {len(self.events)} GitHub "
            f"{'event' if len(self.events)==1 else 'events'}."
        )
        content_parts.append("")
        
        # 4. Stories section with integrated story packets
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
                        
                        # Add AI micro-intro if available
                        if packet.get('ai_micro_intro'):
                            content_parts.append(packet['ai_micro_intro'])
                            content_parts.append("")
                        
                        if packet.get('why'):
                            content_parts.append(f"**Why:** {packet['why']}")
                            content_parts.append("")
                        
                        if packet.get('highlights'):
                            content_parts.append("**Highlights:**")
                            for highlight in packet['highlights']:
                                content_parts.append(f"- {highlight}")
                            content_parts.append("")
                        
                        # Add video if available and rendered
                        if (packet.get('video', {}).get('path') and 
                            packet.get('video', {}).get('status') != 'pending'):
                            video_path = packet['video']['path']
                            
                            # Convert relative video paths to public URLs
                            if video_path.startswith('out/videos/'):
                                # Convert to public stories URL with consistent format
                                date_part = video_path.split('/')[2]  # Get date from out/videos/YYYY-MM-DD/
                                filename = video_path.split('/')[-1]  # Get filename
                                # Convert to YYYY/MM/DD format
                                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                                public_path = f"stories/{date_obj.strftime('%Y/%m/%d')}/{filename}"
                                video_path = public_path
                            
                            # Convert to Cloudflare R2 URL for API consumption
                            if video_path.startswith('stories/') or video_path.startswith('/stories/'):
                                # Remove leading slash if present
                                clean_path = video_path.lstrip('/')
                                cloudflare_url = self.utils.get_cloudflare_url(clean_path)
                                video_path = cloudflare_url
                            
                            # Add video embed for website preview (only for secure paths)
                            if video_path.startswith(('https://', '/stories/')):
                                # Escape video path for HTML attribute to prevent XSS
                                escaped_video_path = html.escape(video_path, quote=True)
                                
                                # Generate thumbnail URL for the video
                                thumbnail_url = self.utils.get_video_thumbnail_url(video_path, packet.get('id', ''))
                                
                                if thumbnail_url:
                                    # Escape thumbnail URL for HTML attribute to prevent XSS
                                    escaped_thumbnail_url = html.escape(thumbnail_url, quote=True)
                                    content_parts.append(f'<video controls poster="{escaped_thumbnail_url}" src="{escaped_video_path}"></video>')
                                else:
                                    content_parts.append(f'<video controls src="{escaped_video_path}"></video>')
                                content_parts.append("")
                            else:
                                # For non-secure paths, just show the link
                                content_parts.append(f"**Video:** [Watch Story]({video_path})")
                                content_parts.append("")
                        
                        # Add PR link
                        if packet.get('links', {}).get('pr_url'):
                            content_parts.append(f"**PR:** [{packet['links']['pr_url']}]({packet['links']['pr_url']})")
                            content_parts.append("")
                        
                        content_parts.append("---")
                        content_parts.append("")
        
        # 5. Twitch clips section (if not covered by stories)
        if self.clips and not self.story_packets:
            content_parts.append("## Twitch Clips")
            content_parts.append("")
            
            for clip in self.clips:
                content_parts.append(f"### {clip.get('title', 'Untitled Clip')}")
                if clip.get('duration') is not None:
                    content_parts.append(f"**Duration:** {clip['duration']} seconds")
                content_parts.append(f"**Views:** {clip.get('view_count', 'Unknown')}")
                content_parts.append(f"**URL:** {clip.get('url', '')}")
                content_parts.append("")
                
                if clip.get('transcript'):
                    content_parts.append("**Transcript:**")
                    content_parts.append(f"> {clip.get('transcript', '')}")
                    content_parts.append("")
        
        # 6. GitHub events section (if not covered by stories)
        if self.events and not self.story_packets:
            content_parts.append("## GitHub Activity")
            content_parts.append("")
            
            for event in self.events:
                content_parts.append(f"### {event.get('type', 'unknown')} in {event.get('repo', '')}")
                content_parts.append(f"**Actor:** {event.get('actor', 'Unknown')}")
                created = event.get('created_at', 'Unknown')
                if isinstance(created, (datetime, date)):
                    created = created.isoformat()
                content_parts.append(f"**Time:** {created}")
                
                if event.get('url'):
                    content_parts.append(f"**URL:** {event.get('url', '')}")
                
                if event.get('title'):
                    content_parts.append(f"**Title:** {event.get('title', '')}")
                
                if event.get('body'):
                    content_parts.append(f"**Description:** {event.get('body', '')}")
                
                # Add commit messages if available
                if event.get('details', {}).get('commit_messages'):
                    content_parts.append("**Commits:**")
                    for msg in event.get('details', {}).get('commit_messages', []):
                        content_parts.append(f"- {msg}")
                
                content_parts.append("")
        
        # 7. Wrap-up paragraph (if available)
        if self.frontmatter.get("wrap_up"):
            content_parts.append("")
            content_parts.append(self.frontmatter["wrap_up"])
            content_parts.append("")
        
        # 8. Related posts block
        if related_enabled:
            content_parts.extend(self._generate_related_posts())
        
        return "\n".join(content_parts)
    
    def _generate_related_posts(self) -> List[str]:
        """Generate related posts section."""
        try:
            from .related import RelatedPostsService
            
            related_service = RelatedPostsService()
            
            # Extract repo from GitHub events to check for related posts
            repo = None
            if self.events:
                # Get the first GitHub event's repo
                first_event = self.events[0]
                if first_event.get("repo"):
                    repo = first_event["repo"]
            
            related_posts = related_service.find_related_posts(
                self.target_date,
                self.frontmatter.get("tags", []),
                self.frontmatter.get("title", ""),
                repo=repo
            )
            
            if related_posts:
                return self._format_related_posts(related_posts)
            else:
                return self._format_no_related_posts()
                
        except Exception as e:
            logger.warning(f"Failed to generate related posts: {e}")
            return self._format_no_related_posts()
    
    def _format_related_posts(self, related_posts: List[Tuple[str, str, float]]) -> List[str]:
        """Format related posts block."""
        related_block = ["\n## Related posts\n"]
        
        for title, path, score in related_posts:
            related_block.append(f"- [{title}]({path})")
        
        related_block.append("")  # Add blank line
        related_block.extend(self._get_signature())
        
        return related_block
    
    def _format_no_related_posts(self) -> List[str]:
        """Format no related posts message."""
        no_posts = [
            "\n## Related posts\n",
            "No related posts found for this blog post."
        ]
        no_posts.extend(self._get_signature())
        
        return no_posts
    
    def _get_signature(self) -> List[str]:
        """Get the blog signature."""
        return [
            "\n---",
            "",
            "[https://upwork.com/freelancers/paulchrisluke](https://upwork.com/freelancers/paulchrisluke)",
            "",
            "_Hi. I'm Chris. I am a morally ambiguous technology marketer. Ridiculously rich people ask me to solve problems they didn't know they have. Book me on_ [Upwork](https://upwork.com/freelancers/paulchrisluke) _like a high-class hooker or find someone who knows how to get ahold of me._"
        ]
    
    def post_process_markdown(self, markdown: str, ai_enabled: bool, force_ai: bool) -> str:
        """
        Post-process markdown with AI inserts and enhancements.
        
        Args:
            markdown: Raw markdown content
            ai_enabled: Whether AI is enabled
            force_ai: Whether to force AI regeneration
            
        Returns:
            Enhanced markdown content
        """
        if not ai_enabled:
            return markdown
        
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
            if "schema" in self.frontmatter and "article" in self.frontmatter["schema"]:
                self.frontmatter["schema"]["article"]["image"] = best_image
            
            # 2. Title punch-up (optional)
            current_title = self.frontmatter.get("title", "")
            improved_title = ai_service.punch_up_title(self.target_date, current_title, force_ai)
            
            if improved_title:
                # Update frontmatter and H1
                self.frontmatter["title"] = improved_title
                # Also update og:title and headline in frontmatter
                if "og" in self.frontmatter:
                    self.frontmatter["og"]["og:title"] = improved_title
                if "schema" in self.frontmatter and "article" in self.frontmatter["schema"]:
                    self.frontmatter["schema"]["article"]["headline"] = improved_title
                markdown = self._update_title_in_markdown(markdown, improved_title)
            
            # 3. Story micro-intros
            markdown = self._insert_story_micro_intros(markdown, ai_service, force_ai)
            
            # 4. Generate holistic intro and wrap-up
            holistic_intro = ai_service.make_holistic_intro(self.target_date, inputs, force_ai)
            if holistic_intro:
                markdown = self._insert_holistic_intro(markdown, holistic_intro)
            
            wrap_up = ai_service.make_wrap_up(self.target_date, inputs, force_ai)
            if wrap_up:
                markdown = self._insert_wrap_up(markdown, wrap_up)
            
            # 5. Generate AI-suggested tags
            suggested_tags = ai_service.suggest_tags(self.target_date, inputs, force_ai)
            if suggested_tags:
                # Merge with existing tags, avoiding duplicates
                existing_tags = set(self.frontmatter.get("tags", []))
                existing_tags.update(suggested_tags)
                self.frontmatter["tags"] = list(existing_tags)
                
                # Also update schema keywords
                if "schema" in self.frontmatter and "article" in self.frontmatter["schema"]:
                    self.frontmatter["schema"]["article"]["keywords"] = list(existing_tags)
            
            return markdown
            
        except Exception as e:
            logger.warning(f"Post-processing failed: {e}")
            return markdown  # Return original markdown on error
    
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
    
    def _insert_story_micro_intros(self, markdown: str, ai_service, force_ai: bool = False) -> str:
        """Insert comprehensive story intros under each story heading."""
        for packet in self.story_packets:
            story_title = packet.get("title_human", "")
            if not story_title:
                continue
            
            # Find the story heading
            heading_pattern = rf"^(#### {re.escape(story_title)})$"
            
            # Prepare inputs for AI
            story_inputs = {
                "title": story_title,
                "why": packet.get("why", ""),
                "highlights_csv": ",".join(packet.get("highlights", []))
            }
            
            comprehensive_intro = ai_service.make_story_comprehensive_intro(self.target_date, story_inputs, force_ai)
            
            # Insert comprehensive intro after heading
            replacement = rf"\1\n\n{comprehensive_intro}\n"
            markdown = re.sub(heading_pattern, replacement, markdown, flags=re.MULTILINE)
        
        return markdown
    
    def _insert_holistic_intro(self, markdown: str, intro: str) -> str:
        """Insert holistic intro paragraph after the lead but before GitHub/Twitch stats."""
        lines = markdown.splitlines()
        
        # Find the line with "Today's development activities include..." or similar
        # This should be in the markdown body, not frontmatter
        for i, line in enumerate(lines):
            if "Today's development activities include" in line or "Twitch clips" in line or "GitHub events" in line:
                # Insert holistic intro before this line
                lines.insert(i, '')
                lines.insert(i, intro)
                lines.insert(i, '')
                break
        else:
            # If we can't find the stats line, insert after the first paragraph after H1
            for i, line in enumerate(lines):
                if line.startswith('# ') and not line.startswith('##'):
                    # Found H1, look for the next non-empty line (should be the lead)
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() and not lines[j].startswith('---'):
                            # Insert holistic intro after the lead
                            lines.insert(j + 1, '')
                            lines.insert(j + 2, intro)
                            lines.insert(j + 3, '')
                            break
                    break
        
        return '\n'.join(lines)
    
    def _insert_wrap_up(self, markdown: str, wrap_up: str) -> str:
        """Insert wrap-up section before the Related posts section."""
        lines = markdown.splitlines()
        
        # Find the "Related posts" section
        for i, line in enumerate(lines):
            if line.strip() == "## Related posts":
                # Insert wrap-up section before Related posts
                # Insert in correct order: header, blank, content, blank
                lines.insert(i, "## Wrap-Up")
                lines.insert(i + 1, '')
                lines.insert(i + 2, wrap_up)
                lines.insert(i + 3, '')
                break
        else:
            # If no Related posts section, append at the end
            lines.append("")
            lines.append("## Wrap-Up")
            lines.append("")
            lines.append(wrap_up)
        
        return '\n'.join(lines)
