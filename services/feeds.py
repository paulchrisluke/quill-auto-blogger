"""
Feed generation service for RSS and sitemap.
Generates feeds that link to canonical Nuxt frontend URLs.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


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
        sorted_blogs = sorted(blogs_data, key=lambda x: x.get('date', ''), reverse=True)
        
        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Daily Devlog</title>
    <link>{self.frontend_domain}</link>
    <description>Daily development log with Twitch clips and GitHub events</description>
    <language>en-us</language>
    <lastBuildDate>{datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}</lastBuildDate>
    <atom:link href="{self.api_domain}/rss.xml" rel="self" type="application/rss+xml" />
"""
        
        for blog in sorted_blogs:
            frontmatter = blog.get('frontmatter', {})
            date_str = blog.get('date', '')
            
            if not date_str or not frontmatter:
                continue
            
            try:
                # Parse date for RSS format
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                rss_date = date_obj.strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                # Get canonical URL
                canonical_url = frontmatter.get('canonical', f"{self.frontend_domain}/blog/{date_str}")
                
                # Get description from lead or content
                description = frontmatter.get('lead', '')
                if not description and 'content' in blog:
                    content = blog['content'].get('body', '')
                    description = content[:200] + '...' if len(content) > 200 else content
                
                # Get image
                image_url = frontmatter.get('og', {}).get('og:image', '')
                
                rss_content += f"""    <item>
      <title>{frontmatter.get('title', f'Daily Devlog — {date_str}')}</title>
      <link>{canonical_url}</link>
      <guid>{canonical_url}</guid>
      <pubDate>{rss_date}</pubDate>
      <description><![CDATA[{description}]]></description>"""
                
                if image_url:
                    rss_content += f"""
      <enclosure url="{image_url}" type="image/jpeg" length="0" />"""
                
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
        sorted_blogs = sorted(blogs_data, key=lambda x: x.get('date', ''), reverse=True)
        
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
            
            sitemap_content += f"""
  <url>
    <loc>{canonical_url}</loc>
    <lastmod>{date_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>"""
        
        sitemap_content += """
</urlset>"""
        
        return sitemap_content
    
    def generate_blogs_index(self, blogs_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate blogs index JSON with enhanced Blog schema for API consumption.
        
        Args:
            blogs_data: List of blog digest data
            
        Returns:
            Blogs index dictionary with schema.org Blog structure
        """
        # Sort by date descending (newest first)
        sorted_blogs = sorted(blogs_data, key=lambda x: x.get('date', ''), reverse=True)
        
        # Generate BlogPosting entries for schema.org
        blog_posts = []
        blogs_list = []
        
        for blog in sorted_blogs:
            frontmatter = blog.get('frontmatter', {})
            date_str = blog.get('date', '')
            
            if not date_str or not frontmatter:
                continue
            
            # Get canonical URL
            canonical_url = frontmatter.get('canonical', f"{self.frontend_domain}/blog/{date_str}")
            
            # Get the best image for this blog post
            best_image = blog.get('image')  # Use the image field directly from the blog data
            
            # Create BlogPosting schema entry
            blog_posting = {
                "@type": "BlogPosting",
                "headline": frontmatter.get('title', f'Daily Devlog — {date_str}'),
                "description": frontmatter.get('description', frontmatter.get('lead', '')),
                "url": canonical_url,
                "datePublished": date_str,
                "author": {
                    "@type": "Person",
                    "name": frontmatter.get('author', 'Paul Chris Luke')
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
                "date": date_str,
                "title": frontmatter.get('title', f'Daily Devlog — {date_str}'),
                "author": frontmatter.get('author', 'Paul Chris Luke'),
                "canonical_url": canonical_url,
                "api_url": f"{self.api_domain}/blogs/{date_str}/API-v3-{date_str}_digest.json",
                "tags": frontmatter.get('tags', []),
                "lead": frontmatter.get('lead', ''),
                "description": frontmatter.get('description', ''),
                "story_count": len(blog.get('story_packets', [])),
                "has_video": any(
                    packet.get('video', {}).get('status') == 'rendered' 
                    for packet in blog.get('story_packets', [])
                )
            }
            blogs_list.append(blog_entry)
        
        # Create enhanced blogs index with schema.org Blog structure
        blogs_index = {
            "@context": "https://schema.org",
            "@type": "Blog",
            "name": "Daily Devlog",
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
                    "url": f"{self.frontend_domain}/pcl-labs-logo.svg"
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
