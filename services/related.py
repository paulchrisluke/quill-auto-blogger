"""
Python-only related posts scorer for M5.
Scores posts based on tags overlap, title similarity, and recency.
"""

import json
import logging
import math
import os
import httpx
from datetime import datetime, date
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class RelatedPostsService:
    """
    Service for finding related blog posts.
    
    This service can find related posts from both local and remote repositories.
    When working on a PR, it will check the remote repo's main branch to find
    published posts that could be related to the current content.
    
    Features:
    - Local post discovery from blogs/ directory
    - Remote post discovery from GitHub API
    - Smart scoring based on tags, title similarity, and recency
    - Automatic deduplication of local and remote posts
    - Fallback to local-only when remote API is unavailable
    """
    
    def __init__(self):
        self.blogs_dir = Path("blogs")
        self.cache_dir = Path("blogs/.cache/m5")
        self.github_api_base = "https://api.github.com"
    
    def find_related_posts(
        self, 
        current_date: str, 
        current_tags: List[str], 
        current_title: str,
        max_posts: int = 3,
        repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find related posts based on scoring algorithm.
        
        Args:
            current_date: Current post date (YYYY-MM-DD)
            current_tags: Current post tags
            current_title: Current post title
            max_posts: Maximum number of related posts to return
            repo: Repository to check for published posts (defaults to self.default_repo)
            
        Returns:
            List of related post dictionaries with title, url, score, image, and description
        """
        # Find all published blog posts - try local first, then remote
        published_posts = []
        if self.blogs_dir.exists():
            published_posts = self._load_local_final_digests()
        

        
        # If no local posts or we're working on a PR, check remote repo
        if not published_posts or repo:
            remote_repo = repo or "paulchrisluke/pcl-labs"
            try:
                remote_posts = self._fetch_published_posts_from_remote(remote_repo)
                if remote_posts:
                    # If we found remote posts, use them exclusively to avoid broken links
                    published_posts = remote_posts
                    logger.info(f"Using {len(remote_posts)} remote posts from {remote_repo} to avoid broken links")
                else:
                    # No remote posts found - this could mean the blogs directory doesn't exist
                    # or there are no published posts yet
                    if repo:
                        logger.info(f"No remote posts found in {remote_repo} - this may be a new repo or no blogs published yet")
                        # When working on a PR, be conservative and don't include local posts
                        # that might not exist on the target branch
                        # But preserve local posts as fallback instead of clearing them
                        logger.info("Preserving local posts as fallback")
                    else:
                        # No repo specified, safe to use local posts
                        logger.info("No remote posts found, using local posts")
            except Exception as e:
                logger.warning(f"Failed to fetch remote posts from {remote_repo}: {e}")
                # Continue with local posts as fallback instead of clearing them
                if repo:
                    logger.info("Remote fetch failed, preserving local posts as fallback")
        
        if not published_posts:
            return []
        
        # Score each post
        scored_posts = []
        
        for post in published_posts:
            if post["date"] == current_date:
                continue  # Skip current post
            
            # Validate post has required fields
            if not post.get("title") or not post.get("tags"):
                logger.debug(f"Skipping post {post.get('date', 'unknown')} - missing title or tags")
                continue
            
            score = self._compute_related_score(
                current_tags, 
                current_title, 
                current_date,
                post["tags"], 
                post["title"], 
                post["date"]
            )
            
            # Only include posts with a meaningful score
            if score > 0.0:
                # Format date to ISO format with timezone
                date_str = post["date"]
                if date_str and not date_str.endswith("Z"):
                    # Convert YYYY-MM-DD to YYYY-MM-DDTHH:MM:SSZ
                    date_str = f"{date_str}T00:00:00Z"
                
                related_post = {
                    "title": post["title"],
                    "url": post.get("url", f"https://paulchrisluke.com/blog/{post.get('date', '')}"),
                    "score": round(score, 3),
                    "date": date_str,
                    "image": self._get_featured_image(post),
                    "description": post.get("description", ""),
                    "tags": post.get("tags", [])
                }
                scored_posts.append(related_post)
            else:
                logger.debug(f"Skipping post {post['title']} - score too low: {score}")
        
        # Sort by score descending and return top results
        scored_posts.sort(key=lambda x: x["score"], reverse=True)
        return scored_posts[:max_posts]
    
    def _find_published_posts(self) -> List[Dict[str, Any]]:
        """Find all published blog posts from digest files."""
        posts = []
        
        # Scan blogs directory for digest files
        for date_dir in self.blogs_dir.iterdir():
            if not date_dir.is_dir():
                continue
            
            try:
                # Validate date format
                datetime.strptime(date_dir.name, "%Y-%m-%d")
            except ValueError:
                continue
            
            # Look for pre-cleaned digest
            digest_file = date_dir / f"PRE-CLEANED-{date_dir.name}_digest.json"
            if digest_file.exists():
                try:
                    with open(digest_file, 'r', encoding='utf-8') as f:
                        digest = json.load(f)
                    
                    # Extract post information
                    if "frontmatter" in digest:
                        frontmatter = digest["frontmatter"]
                        post_info = {
                            "date": digest["date"],
                            "title": frontmatter.get("title", ""),
                            "tags": frontmatter.get("tags", []),
                            "description": frontmatter.get("description", ""),
                            "path": f"/blog/{digest['date']}",
                            "digest": digest  # Store full digest for image extraction
                        }
                        posts.append(post_info)
                        
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to load digest {digest_file}: {e}")
        
        return posts
    
    def _fetch_published_posts_from_remote(self, repo: str) -> List[Dict[str, Any]]:
        """
        Fetch published blog posts from the remote repo's main branch.
        
        Args:
            repo: Repository in format 'owner/repo'
            
        Returns:
            List of post information dictionaries
        """
        posts = []
        
        try:
            # Get GitHub token from environment
            github_token = os.getenv("GITHUB_TOKEN")
            if not github_token:
                logger.warning("No GITHUB_TOKEN found, cannot fetch remote posts")
                return posts
            
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Fetch the blogs directory contents from main branch
            api_url = f"{self.github_api_base}/repos/{repo}/contents/blogs"
            logger.info(f"Fetching remote posts from {api_url}")
            
            with httpx.Client(timeout=30.0) as client:
                response = client.get(api_url, headers=headers)
                
                if response.status_code == 404:
                    logger.info(f"No blogs directory found in {repo}")
                    return posts
                elif response.status_code != 200:
                    logger.warning(f"Failed to fetch blogs directory from {repo}: HTTP {response.status_code}")
                    return posts
                
                contents = response.json()
                
                # Process each date directory
                for item in contents:
                    if item["type"] == "dir":
                        date_str = item["name"]
                        
                        # Validate date format
                        try:
                            datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            logger.debug(f"Skipping non-date directory: {date_str}")
                            continue
                        
                        # Look for pre-cleaned digest in this date directory
                        digest_url = f"{api_url}/{date_str}/PRE-CLEANED-{date_str}_digest.json"
                        
                        try:
                            digest_response = client.get(digest_url, headers=headers)
                            if digest_response.status_code == 200:
                                # Parse the raw JSON content from the response
                                try:
                                    digest = digest_response.json()
                                    
                                    # Extract post information
                                    if "frontmatter" in digest:
                                        frontmatter = digest["frontmatter"]
                                        post_info = {
                                            "date": digest["date"],
                                            "title": frontmatter.get("title", ""),
                                            "tags": frontmatter.get("tags", []),
                                            "description": frontmatter.get("description", ""),
                                            "path": f"/blog/{digest['date']}",
                                            "digest": digest  # Store full digest for image extraction
                                        }
                                        posts.append(post_info)
                                        logger.info(f"Found remote post: {date_str} - {post_info['title']}")
                                    else:
                                        logger.debug(f"Skipping digest {date_str} - not v2 or missing frontmatter")
                                except json.JSONDecodeError as e:
                                    logger.debug(f"Failed to parse digest JSON for {date_str}: {e}")
                                    continue
                            elif digest_response.status_code == 404:
                                logger.debug(f"No digest found for {date_str}")
                            else:
                                logger.debug(f"Failed to fetch digest for {date_str}: HTTP {digest_response.status_code}")
                                    
                        except Exception as e:
                            logger.debug(f"Could not fetch digest for {date_str}: {e}")
                            continue
                            
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error fetching remote posts from {repo}: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.warning(f"Request error fetching remote posts from {repo}: {e}")
        except Exception as e:
            logger.warning(f"Failed to fetch remote posts from {repo}: {e}")
        
        logger.info(f"Found {len(posts)} remote posts from {repo}")
        return posts
    
    def _compute_related_score(
        self,
        current_tags: List[str],
        current_title: str,
        current_date: str,
        post_tags: List[str],
        post_title: str,
        post_date_str: str
    ) -> float:
        """
        Compute relatedness score between current post and candidate post.
        
        Scoring algorithm:
        - Tags overlap: 60% weight
        - Title similarity (Jaccard): 20% weight  
        - Recency decay: 20% weight (90-day half-life)
        """
        try:
            current_date_obj = datetime.strptime(current_date, "%Y-%m-%d").date()
            post_date = datetime.strptime(post_date_str, "%Y-%m-%d").date()
        except ValueError:
            return 0.0
        
        # Tags overlap score (60% weight)
        tags_score = self._compute_tags_overlap(current_tags, post_tags)
        
        # Title similarity score (20% weight)
        title_score = self._compute_title_similarity(current_title, post_title)
        
        # Recency decay score (20% weight)
        recency_score = self._compute_recency_decay(current_date_obj, post_date)
        
        # Weighted combination
        final_score = (
            tags_score * 0.6 +
            title_score * 0.2 +
            recency_score * 0.2
        )
        
        return final_score
    
    def _compute_tags_overlap(self, current_tags: List[str], post_tags: List[str]) -> float:
        """Compute tags overlap score (0.0 to 1.0)."""
        if not current_tags or not post_tags:
            return 0.0
        
        # Convert to sets for overlap calculation
        current_set = set(tag.lower() for tag in current_tags)
        post_set = set(tag.lower() for tag in post_tags)
        
        if not current_set or not post_set:
            return 0.0
        
        # Jaccard similarity
        intersection = len(current_set & post_set)
        union = len(current_set | post_set)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _compute_title_similarity(self, current_title: str, post_title: str) -> float:
        """Compute title similarity using Jaccard on word tokens (0.0 to 1.0)."""
        if not current_title or not post_title:
            return 0.0
        
        # Tokenize titles (simple word splitting)
        current_words = set(current_title.lower().split())
        post_words = set(post_title.lower().split())
        
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'daily', 'devlog', 'development', 'log'
        }
        current_words -= stop_words
        post_words -= stop_words
        
        if not current_words or not post_words:
            return 0.0
        
        # Jaccard similarity
        intersection = len(current_words & post_words)
        union = len(current_words | post_words)
        
        if union == 0:
            return 0.0
        
        # If no common words after stop word removal, return 0.0
        if intersection == 0:
            return 0.0
        
        return intersection / union
    
    def _compute_recency_decay(self, current_date: date, post_date: date) -> float:
        """Compute recency decay score (0.0 to 1.0) with 90-day half-life."""
        days_diff = abs((current_date - post_date).days)
        
        if days_diff == 0:
            return 1.0
        
        # Exponential decay with 90-day half-life
        # score = 0.5^(days_diff / 90)
        decay_factor = days_diff / 90.0
        score = math.pow(0.5, decay_factor)
        
        return max(0.0, min(1.0, score))
    
    def _get_featured_image(self, post: Dict[str, Any]) -> Optional[str]:
        """Extract featured image URL from post data."""
        try:
            digest = post.get("digest", {})
            
            # Try to get from frontmatter og:image
            frontmatter = digest.get("frontmatter", {})
            og_data = frontmatter.get("og", {})
            if og_data.get("og:image"):
                return og_data["og:image"]
            
            # Try to get from story packets
            story_packets = digest.get("story_packets", [])
            if story_packets:
                first_story = story_packets[0]
                video_data = first_story.get("video", {})
                thumbnails = video_data.get("thumbnails", {})
                if thumbnails.get("intro"):
                    # Convert to proper CDN URL
                    thumbnail_path = thumbnails["intro"]
                    if not thumbnail_path.startswith('http'):
                        return f"https://media.paulchrisluke.com/assets/{thumbnail_path}"
                    return thumbnail_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting featured image for post {post.get('title', 'unknown')}: {e}")
            return None
    
    def _load_local_final_digests(self) -> List[Dict[str, Any]]:
        """Load all FINAL and PRE-CLEANED digests from the local blogs directory."""
        posts = []
        
        try:
            # Find all FINAL and PRE-CLEANED digest files
            final_files = list(self.blogs_dir.rglob("FINAL-*_digest.json"))
            pre_cleaned_files = list(self.blogs_dir.rglob("PRE-CLEANED-*_digest.json"))
            all_files = final_files + pre_cleaned_files
            
            for file_path in all_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        digest = json.load(f)
                    
                    # Extract post information
                    frontmatter = digest.get("frontmatter", {})
                    post_date = digest.get("date", "")
                    
                    if not post_date or not frontmatter:
                        continue
                    
                    # Create post data structure
                    post_data = {
                        "title": frontmatter.get("title", ""),
                        "date": post_date,
                        "tags": frontmatter.get("tags", []),
                        "description": frontmatter.get("description", ""),
                        "url": f"https://paulchrisluke.com/blog/{post_date}",
                        "digest": digest
                    }
                    
                    posts.append(post_data)
                    
                except Exception as e:
                    logger.warning(f"Failed to load FINAL digest {file_path}: {e}")
                    continue
            
            logger.info(f"Loaded {len(posts)} posts from local FINAL digests")
            return posts
            
        except Exception as e:
            logger.error(f"Failed to load local FINAL digests: {e}")
            return []
