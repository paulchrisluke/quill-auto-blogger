"""
Post-processing service for AI-generated blog content.
Handles adding specific links, data, formatting, and technical precision.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

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
        
        # Add video embeds with proper URLs and track processed clips
        processed_content, processed_clips = self._add_video_embeds(processed_content, digest)
        
        # Add specific data points (view counts, commit hashes, etc.)
        # Skip clips that were already processed in _add_video_embeds
        processed_content = self._add_specific_data(processed_content, digest, processed_clips)
        
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
    
    def _add_video_embeds(self, content: str, digest: Dict[str, Any]) -> tuple[str, set]:
        """Add video embeds with proper URLs and return processed clip titles."""
        twitch_clips = digest.get('twitch_clips', [])
        processed_clips = set()
        
        for clip in twitch_clips:
            clip_title = clip.get('title', '')
            clip_url = clip.get('url', '')
            
            if clip_title and clip_url:
                # Look for clip title references and add video embeds
                title_pattern = rf'"{re.escape(clip_title)}"'
                # Extract clip ID from URL for proper embed with validation
                clip_id = self._extract_clip_id_from_url(clip_url)
                
                if not clip_id:
                    self.logger.warning(f"Skipping video embed for invalid clip URL: {clip_url}")
                    continue
                
                video_embed = (
                    f'<iframe '
                    f'src="https://clips.twitch.tv/embed?clip={clip_id}&parent=yourdomain.com" '
                    f'width="640" height="360" frameborder="0" scrolling="no" allowfullscreen="true">'
                    f'</iframe>'
                )
                
                if re.search(title_pattern, content):
                    # Add video embed after the title reference
                    content = re.sub(
                        title_pattern,
                        f'"{clip_title}"\n\n{video_embed}',
                        content
                    )
                    processed_clips.add(clip_title)
                    self.logger.info(f"Added video embed for clip: {clip_title}")
        
        return content, processed_clips
    
    def _add_specific_data(self, content: str, digest: Dict[str, Any], processed_clips: set) -> str:
        """Add specific data points like view counts, commit hashes, etc."""
        twitch_clips = digest.get('twitch_clips', [])
        
        for clip in twitch_clips:
            clip_title = clip.get('title', '')
            view_count = clip.get('view_count', 0)
            
            # Skip clips that were already processed in _add_video_embeds
            if clip_title in processed_clips:
                continue
                
            if clip_title and view_count:
                # Add specific view count data
                title_pattern = rf'"{re.escape(clip_title)}"'
                if re.search(title_pattern, content):
                    # Format view count with thousands separators
                    formatted_view_count = f"{view_count:,}"
                    # Add view count after the title
                    content = re.sub(title_pattern, f'"{clip_title}" ({formatted_view_count} views)', content)
                    self.logger.info(f"Added view count for clip: {clip_title} ({formatted_view_count} views)")
        
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
    
    def _validate_twitch_clip_url(self, url: str) -> bool:
        """Validate that a URL is a proper Twitch clip URL."""
        if not url:
            return False
        
        try:
            parsed = urlparse(url)
            # Check if it's a valid Twitch clip URL
            return (
                parsed.scheme in ['http', 'https'] and
                parsed.netloc in ['clips.twitch.tv', 'www.clips.twitch.tv'] and
                parsed.path and
                len(parsed.path.split('/')) >= 2  # Should have /clip_id format
            )
        except Exception as e:
            self.logger.warning(f"Error validating Twitch URL {url}: {e}")
            return False
    
    def _extract_clip_id_from_url(self, url: str) -> Optional[str]:
        """Extract clip ID from Twitch clip URL with validation."""
        if not self._validate_twitch_clip_url(url):
            self.logger.warning(f"Invalid Twitch clip URL format: {url}")
            return None
        
        try:
            # Extract clip ID from URL path (e.g., /clip_id -> clip_id)
            clip_id = url.split('/')[-1]
            
            # Basic validation of clip ID format
            if not clip_id or len(clip_id) < 3:
                self.logger.warning(f"Invalid clip ID extracted from URL: {url}")
                return None
            
            return clip_id
        except Exception as e:
            self.logger.error(f"Error extracting clip ID from URL {url}: {e}")
            return None
    
    def _construct_thumbnail_url(self, clip_id: str) -> Optional[str]:
        """Construct Twitch thumbnail URL with error handling."""
        if not clip_id:
            return None
        
        try:
            # Use the standard Twitch clips thumbnail format
            thumbnail_url = f"https://clips-media-assets2.twitch.tv/{clip_id}-preview-480x272.jpg"
            self.logger.debug(f"Constructed thumbnail URL: {thumbnail_url}")
            return thumbnail_url
        except Exception as e:
            self.logger.error(f"Error constructing thumbnail URL for clip ID {clip_id}: {e}")
            return None
    
    def enhance_frontmatter(self, frontmatter: Dict[str, Any], digest: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance frontmatter with specific technical data."""
        enhanced = frontmatter.copy()
        
        # Add specific image from best clip with proper error handling
        twitch_clips = digest.get('twitch_clips', [])
        if twitch_clips:
            try:
                # Use the clip with highest view count for the image
                best_clip = max(twitch_clips, key=lambda x: x.get('view_count', 0))
                clip_url = best_clip.get('url')
                
                if clip_url:
                    # Extract and validate clip ID
                    clip_id = self._extract_clip_id_from_url(clip_url)
                    if clip_id:
                        # Construct thumbnail URL with error handling
                        thumbnail_url = self._construct_thumbnail_url(clip_id)
                        if thumbnail_url:
                            enhanced['image'] = thumbnail_url
                            self.logger.info(f"Added thumbnail URL for clip: {clip_id}")
                        else:
                            self.logger.warning(f"Failed to construct thumbnail URL for clip: {clip_id}")
                    else:
                        self.logger.warning(f"Failed to extract valid clip ID from URL: {clip_url}")
                else:
                    self.logger.warning("Best clip has no URL, skipping thumbnail generation")
            except Exception as e:
                self.logger.error(f"Error processing best clip for thumbnail: {e}")
                # Continue without thumbnail rather than failing completely
        
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
