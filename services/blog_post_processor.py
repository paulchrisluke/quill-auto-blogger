"""
Post-processing service for AI-generated blog content.
Handles adding specific links, data, formatting, and technical precision.
"""

import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class BlogPostProcessor:
    """Post-processes AI-generated blog content with technical precision."""
    
    def __init__(self):
        self.logger = logger
    
    def process_blog_content(self, ai_content: str, digest: Dict[str, Any]) -> str:
        """
        Post-process AI-generated content with specific links, data, and formatting.
        
        Args:
            ai_content: The AI-generated markdown content
            digest: The enriched digest containing technical data
            
        Returns:
            Processed markdown content with technical precision
        """
        processed_content = ai_content
        
        # Add specific PR links
        processed_content = self._add_pr_links(processed_content, digest)
        
        # Add video embeds with proper URLs
        processed_content = self._add_video_embeds(processed_content, digest)
        
        # Add specific data points (view counts, commit hashes, etc.)
        processed_content = self._add_specific_data(processed_content, digest)
        
        # Add signature and call-to-action
        processed_content = self._add_signature(processed_content)
        
        return processed_content
    
    def _add_pr_links(self, content: str, digest: Dict[str, Any]) -> str:
        """Add specific PR links to the content."""
        github_events = digest.get('github_events', [])
        
        for event in github_events:
            if event.get('type') == 'PullRequestEvent' and event.get('details', {}).get('merged', False):
                pr_number = event.get('details', {}).get('number')
                pr_title = event.get('details', {}).get('title', '')
                
                if pr_number:
                    # Look for PR references in the content and add links
                    pr_pattern = rf'PR #{pr_number}'
                    pr_link = f'[PR #{pr_number}](https://github.com/paulchrisluke/pcl-labs/pull/{pr_number})'
                    
                    if re.search(pr_pattern, content):
                        content = re.sub(pr_pattern, pr_link, content)
                        self.logger.info(f"Added PR link for #{pr_number}: {pr_title}")
        
        return content
    
    def _add_video_embeds(self, content: str, digest: Dict[str, Any]) -> str:
        """Add video embeds with proper URLs."""
        twitch_clips = digest.get('twitch_clips', [])
        
        for clip in twitch_clips:
            clip_title = clip.get('title', '')
            clip_url = clip.get('url', '')
            
            if clip_title and clip_url:
                # Look for clip title references and add video embeds
                title_pattern = rf'"{re.escape(clip_title)}"'
                video_embed = f'<video controls src="{clip_url}"></video>'
                
                if re.search(title_pattern, content):
                    # Add video embed after the title reference
                    content = re.sub(title_pattern, f'"{clip_title}"\n\n{video_embed}', content)
                    self.logger.info(f"Added video embed for clip: {clip_title}")
        
        return content
    
    def _add_specific_data(self, content: str, digest: Dict[str, Any]) -> str:
        """Add specific data points like view counts, commit hashes, etc."""
        twitch_clips = digest.get('twitch_clips', [])
        
        for clip in twitch_clips:
            clip_title = clip.get('title', '')
            view_count = clip.get('view_count', 0)
            transcript = clip.get('transcript', '')
            
            if clip_title and view_count:
                # Add specific view count data
                title_pattern = rf'"{re.escape(clip_title)}"'
                if re.search(title_pattern, content):
                    # Add view count after the title
                    content = re.sub(title_pattern, f'"{clip_title}" ({view_count} views)', content)
                    self.logger.info(f"Added view count for clip: {clip_title} ({view_count} views)")
            
            # Add transcript quotes if they exist
            if transcript and clip_title:
                # Look for places where we can add transcript context
                # This is more complex and would need specific patterns
                pass
        
        return content
    
    def _add_signature(self, content: str) -> str:
        """Add the standard signature and call-to-action."""
        signature = """

---

*Want to see more of this beautiful chaos? Follow me on [Twitch](https://twitch.tv/paulchrisluke) for live coding sessions, or check out my other projects at [PCL Labs](https://paulchrisluke.com).*

*Hi. I'm Chris. I'm a morally ambiguous technology marketer and builder at PCL Labs. I turn raw events into stories with wit, irreverence, and emotional honesty. I help solve complex technical challenges through AI blog automation, schema-driven SEO, and developer workflow optimization. Book me on [Upwork](https://upwork.com/freelancers/paulchrisluke) or find someone who knows how to get ahold of me.*"""
        
        # Add signature if it's not already there
        if "morally ambiguous technology marketer" not in content:
            content += signature
        
        return content
    
    def enhance_frontmatter(self, frontmatter: Dict[str, Any], digest: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance frontmatter with specific technical data."""
        enhanced = frontmatter.copy()
        
        # Add specific image from best clip
        twitch_clips = digest.get('twitch_clips', [])
        if twitch_clips:
            # Use the clip with highest view count for the image
            best_clip = max(twitch_clips, key=lambda x: x.get('view_count', 0))
            if best_clip.get('url'):
                # Convert Twitch clip URL to thumbnail URL
                clip_id = best_clip['url'].split('/')[-1]
                thumbnail_url = f"https://clips-media-assets2.twitch.tv/{clip_id}-preview-480x272.jpg"
                enhanced['image'] = thumbnail_url
        
        # Add specific video data to schema
        if 'schema' in enhanced:
            video_data = []
            for clip in twitch_clips:
                if clip.get('url') and clip.get('title'):
                    video_data.append({
                        "@type": "VideoObject",
                        "name": clip['title'],
                        "contentUrl": clip['url'],
                        "uploadDate": clip.get('created_at', ''),
                        "duration": f"PT{int(clip.get('duration', 60))}S"
                    })
            
            if video_data:
                enhanced['schema']['video'] = video_data
        
        return enhanced
