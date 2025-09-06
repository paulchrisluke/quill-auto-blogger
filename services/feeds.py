"""
Feed generation service for RSS and sitemap.
Generates feeds that link to canonical Nuxt frontend URLs.
"""

import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def _safe_cdata(content: str) -> str:
    """Make content safe for CDATA by splitting ]] sequences."""
    if not content:
        return content
    # Replace ]] with ]]]]><![CDATA[> to prevent CDATA termination
    return content.replace("]]>", "]]]]><![CDATA[>")


class FeedGenerator:
    """Generate RSS feeds and sitemaps for blog discovery."""
    
    def __init__(self, frontend_domain: str, api_domain: str):
        self.frontend_domain = frontend_domain.rstrip("/")
        self.api_domain = api_domain.rstrip("/")
    
    def generate_rss_feed(self, blogs_data: List[Dict[str, Any]]) -> str:
        """
        Generate RSS 2.0 feed XML.
        
        Args:
            blogs_data: List of blog digest data
            
        Returns:
            RSS XML string
        """
        # Sort by date descending (newest first)
        sorted_blogs = sorted(blogs_data, key=lambda x: x.get('datePublished', x.get('date', '')), reverse=True)
        
        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:sy="http://purl.org/rss/1.0/modules/syndication/">
  <channel>
    <title>Paul Chris Luke - PCL Labs</title>
    <link>{self.frontend_domain}</link>
    <description>Daily development log with AI-enhanced content, Twitch clips, and GitHub events. Featuring automation, programming insights, and technical tutorials from PCL Labs.</description>
    <language>en-us</language>
    <lastBuildDate>{datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}</lastBuildDate>
    <atom:link href="{self.api_domain}/rss.xml" rel="self" type="application/rss+xml" />
    <sy:updatePeriod>daily</sy:updatePeriod>
    <sy:updateFrequency>1</sy:updateFrequency>
    <generator>Quill Auto Blogger v3.0</generator>
    <managingEditor>paulchrisluke@example.com (Paul Chris Luke)</managingEditor>
    <webMaster>paulchrisluke@example.com (Paul Chris Luke)</webMaster>
    <category>Technology</category>
    <category>Programming</category>
    <category>Development</category>
    <image>
      <url>{self.frontend_domain}/pcl-labs-logo.svg</url>
      <title>Paul Chris Luke - PCL Labs</title>
      <link>{self.frontend_domain}</link>
      <width>144</width>
      <height>144</height>
    </image>
"""
        
        for blog in sorted_blogs:
            # Handle both frontmatter and published formats
            if 'frontmatter' in blog:
                # Legacy format with frontmatter
                frontmatter = blog.get('frontmatter', {})
                date_str = blog.get('date', '')
                
                if not date_str or not frontmatter:
                    continue
                
                # Parse date for RSS format
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                rss_date = date_obj.strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                # Get canonical URL
                canonical_url = frontmatter.get('canonical', f"{self.frontend_domain}/blog/{date_str}")
                
                # Get description from lead or content
                description = frontmatter.get('lead', '')
                if not description and 'content' in blog:
                    content = blog['content'] if isinstance(blog['content'], str) else blog['content'].get('body', '')
                    description = content[:200] + '...' if len(content) > 200 else content
                
                # Get image
                image_url = frontmatter.get('og', {}).get('og:image', '')
                
                # Get full content for content:encoded
                content_field = blog.get('content', '')
                full_content = content_field if isinstance(content_field, str) else content_field.get('body', description)
                
                # Escape values for XML
                title = html.escape(frontmatter.get('title', f'PCL Labs Devlog — {date_str}'))
                link = html.escape(canonical_url)
                creator = html.escape(frontmatter.get('author', 'Paul Chris Luke'))
            else:
                # Published format (top-level fields)
                date_str = blog.get('datePublished', '')
                
                if not date_str:
                    continue
                
                # Parse date for RSS format
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                rss_date = date_obj.strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                # Get canonical URL
                canonical_url = blog.get('url', f"{self.frontend_domain}/blog/{date_str}")
                
                # Get description - prefer summary when available
                description = blog.get('summary', '')
                if not description and 'content' in blog:
                    content = blog['content'] if isinstance(blog['content'], str) else blog['content'].get('body', '')
                    description = content[:200] + '...' if len(content) > 200 else content
                
                # Get image from media field
                media = blog.get('media', {})
                if isinstance(media, dict):
                    # Check for hero image first, then direct image
                    hero = media.get('hero', {})
                    if isinstance(hero, dict) and hero.get('image'):
                        image_url = hero['image']
                    else:
                        image_url = media.get('image', '')
                else:
                    image_url = ''
                
                # Get full content for content:encoded
                content_field = blog.get('content', '')
                full_content = content_field if isinstance(content_field, str) else content_field.get('body', description)
                
                # Escape values for XML
                title = html.escape(blog.get('title', f'PCL Labs Devlog — {date_str}'))
                link = html.escape(canonical_url)
                creator = html.escape('Paul Chris Luke')
            
            try:
                
                # Make content safe for CDATA
                safe_description = _safe_cdata(description)
                safe_full_content = _safe_cdata(full_content)
                
                rss_content += f"""    <item>
      <title>{title}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{rss_date}</pubDate>
      <description><![CDATA[{safe_description}]]></description>
      <content:encoded><![CDATA[{safe_full_content}]]></content:encoded>
      <dc:creator>{creator}</dc:creator>
      <dc:date>{date_str}T00:00:00Z</dc:date>"""
                
                # Add categories from tags
                tags = frontmatter.get('tags', []) if 'frontmatter' in blog else blog.get('tags', [])
                for tag in tags[:5]:  # Limit to 5 categories
                    escaped_tag = html.escape(tag)
                    rss_content += f"""
      <category>{escaped_tag}</category>"""
                
                if image_url:
                    # Infer MIME type from file extension
                    mime_type = "image/jpeg"  # default
                    if image_url.lower().endswith('.png'):
                        mime_type = "image/png"
                    elif image_url.lower().endswith('.gif'):
                        mime_type = "image/gif"
                    elif image_url.lower().endswith('.webp'):
                        mime_type = "image/webp"
                    elif image_url.lower().endswith('.svg'):
                        mime_type = "image/svg+xml"
                    
                    rss_content += f"""
      <enclosure url="{image_url}" type="{mime_type}" length="0" />"""
                
                rss_content += """
    </item>
"""
                
            except Exception as e:
                logger.warning(f"Failed to process blog {date_str} for RSS: {e}")
                continue
        
        rss_content += """  </channel>
</rss>"""
        
        return rss_content
    
    def generate_sitemap(self, blogs_data: List[Dict[str, Any]]) -> str:
        """
        Generate XML sitemap.
        
        Args:
            blogs_data: List of blog digest data
            
        Returns:
            Sitemap XML string
        """
        # Sort by date descending (newest first)
        sorted_blogs = sorted(blogs_data, key=lambda x: x.get('datePublished', x.get('date', '')), reverse=True)
        
        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{self.frontend_domain}</loc>
    <lastmod>{datetime.utcnow().strftime('%Y-%m-%d')}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""
        
        for blog in sorted_blogs:
            frontmatter = blog.get('frontmatter', {})
            date_str = blog.get('date', '')
            
            if not date_str or not frontmatter:
                continue
            
            # Get canonical URL
            canonical_url = frontmatter.get('canonical', f"{self.frontend_domain}/blog/{date_str}")
            
            # Get last modified date from blog data
            lastmod_date = self._get_lastmod_date(blog, date_str)
            
            # Escape XML special characters in canonical_url
            escaped_url = html.escape(canonical_url, quote=True)
            sitemap_content += f"""
  <url>
    <loc>{escaped_url}</loc>
    <lastmod>{lastmod_date}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>"""
        
        sitemap_content += """
</urlset>"""
        
        return sitemap_content
    
    def _get_lastmod_date(self, blog: Dict[str, Any], date_str: str) -> str:
        """
        Get the last modified date for a blog post.
        
        Priority:
        1. dateModified from schema
        2. datePublished from schema
        3. Frontmatter date
        4. Blog date
        5. Current date as fallback
        """
        try:
            frontmatter = blog.get('frontmatter', {})
            schema = frontmatter.get('schema', {})
            
            # Try new top-level schema format first
            if schema.get('dateModified'):
                date_modified = schema['dateModified']
                if 'T' in date_modified:
                    return date_modified.split('T')[0]
                return date_modified
            
            if schema.get('datePublished'):
                date_published = schema['datePublished']
                if 'T' in date_published:
                    return date_published.split('T')[0]
                return date_published
            
            # Get dates from schema
            from services.utils import get_schema_property
            
            date_modified = get_schema_property(schema, 'dateModified')
            if date_modified:
                # Convert to YYYY-MM-DD format
                if 'T' in date_modified:
                    return date_modified.split('T')[0]
                return date_modified
            
            # Try datePublished
            date_published = get_schema_property(schema, 'datePublished')
            if date_published:
                # Convert to YYYY-MM-DD format
                if 'T' in date_published:
                    return date_published.split('T')[0]
                return date_published
            
            # Try frontmatter date
            if frontmatter.get('date'):
                return frontmatter['date']
            
            # Use blog date
            if date_str:
                return date_str
            
            # Fallback to current date
            return datetime.utcnow().strftime('%Y-%m-%d')
            
        except Exception as e:
            logger.error(f"Error getting lastmod date for blog {date_str}: {e}")
            return date_str or datetime.utcnow().strftime('%Y-%m-%d')
    
    def generate_blogs_index(self, blogs_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate blogs index JSON with enhanced Blog schema for API consumption.
        
        Args:
            blogs_data: List of blog digest data
            
        Returns:
            Blogs index dictionary with schema.org Blog structure
        """
        # Sort by date descending (newest first)
        sorted_blogs = sorted(blogs_data, key=lambda x: x.get('datePublished', x.get('date', '')), reverse=True)
        
        # Generate BlogPosting entries for schema.org
        blog_posts = []
        blogs_list = []
        
        for blog in sorted_blogs:
            # Handle published format
            if 'frontmatter' in blog:
                frontmatter = blog.get('frontmatter', {})
                date_str = blog.get('date', '')
                title = frontmatter.get('title', f'PCL Labs Devlog — {date_str}')
                description = frontmatter.get('description', frontmatter.get('lead', ''))
                author = frontmatter.get('author', 'Paul Chris Luke')
                tags = frontmatter.get('tags', [])
                canonical_url = frontmatter.get('canonical', f"{self.frontend_domain}/blog/{date_str}")
            else:
                # Published format (publish package)
                date_str = blog.get('datePublished', '')
                # Handle two different publish package formats:
                # 1. Dict content format: content.title, content.summary
                # 2. String content format: title, summary (top-level)
                content = blog.get('content', {})
                if isinstance(content, dict):
                    # Dict content format
                    title = content.get('title', blog.get('title', f'PCL Labs Devlog — {date_str}'))
                    description = content.get('summary', blog.get('summary', ''))
                    tags = content.get('tags', blog.get('tags', []))
                else:
                    # String content format (content is the body text)
                    title = blog.get('title', f'PCL Labs Devlog — {date_str}')
                    description = blog.get('summary', '')
                    tags = blog.get('tags', [])
                author = 'Paul Chris Luke'  # Default author
                canonical_url = blog.get('url', f"{self.frontend_domain}/blog/{date_str}")
            
            if not date_str or not title:
                continue
            
            # Get the best image for this blog post
            best_image = blog.get('image')  # Use the image field directly from the blog data
            
            # Create BlogPosting schema entry
            blog_posting = {
                "@type": "BlogPosting",
                "headline": title,
                "description": description,
                "url": canonical_url,
                "datePublished": date_str,
                "author": {
                    "@type": "Person",
                    "name": author
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "PCL Labs",
                    "logo": {
                        "@type": "ImageObject",
                        "url": f"{self.frontend_domain}/pcl-labs-logo.svg"
                    }
                }
            }
            
            # Add image if available
            if best_image:
                blog_posting["image"] = best_image
            blog_posts.append(blog_posting)
            
            # Create API-friendly blog entry
            blog_entry = {
                "datePublished": date_str,
                "title": title,
                "author": author,
                "canonical_url": canonical_url,
                "api_url": f"{self.api_domain}/blogs/{date_str}/{date_str}_page.publish.json",
                "tags": tags,
                "description": description,
                "story_count": len(blog.get('story_packets', [])),
                "has_video": any(
                    story.get('videoId') is not None 
                    for story in blog.get('story_packets', [])
                )
            }
            blogs_list.append(blog_entry)
        
        # Create enhanced blogs index with schema.org Blog structure
        blogs_index = {
            "@context": "https://schema.org",
            "@type": "Blog",
            "name": "Paul Chris Luke - PCL Labs",
            "url": f"{self.frontend_domain}/blog",
            "description": "Daily development log with AI-enhanced content and automation",
            "author": {
                "@type": "Person",
                "name": "Paul Chris Luke",
                "url": f"{self.frontend_domain}/about"
            },
            "publisher": {
                "@type": "Organization",
                "name": "PCL Labs",
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=1200&h=630&fit=crop"
                }
            },
            "blogPost": blog_posts,
            "meta": {
                "generated_at": datetime.utcnow().isoformat(),
                "total_blogs": len(sorted_blogs),
                "frontend_domain": self.frontend_domain,
                "api_domain": self.api_domain
            },
            "blogs": blogs_list
        }
        
        return blogs_index
