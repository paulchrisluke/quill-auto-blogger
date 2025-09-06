"""
GitHub API service for fetching user and repository activity.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)

from models import GitHubEvent
from services.auth import AuthService
from services.utils import CacheManager, generate_filename, sanitize_filename


class GitHubService:
    """Handles GitHub API interactions and activity processing."""
    
    def __init__(self):
        self.auth_service = AuthService()
        self.cache_manager = CacheManager()
        self.base_url = "https://api.github.com"
    
    def fetch_user_activity(self, username: str, days_back: int = 7) -> List[GitHubEvent]:
        """Fetch recent activity for a GitHub user."""
        headers = self.auth_service.get_github_headers()
        
        # Calculate date range
        since_dt = datetime.utcnow() - timedelta(days=days_back)
        since_date = since_dt.isoformat() + "Z"
        
        events = []
        
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0), http2=True) as client:
                # Get user events
                response = client.get(
                    f"{self.base_url}/users/{username}/events",
                    headers=headers,
                    params={"per_page": 100}
                )
                
                # Handle non-2xx status codes and surface 429 retry hints
                if response.status_code == 429:
                    logger.error("GitHub API rate limit exceeded. Consider reducing request frequency.")
                    response.raise_for_status()
                elif response.status_code >= 400:
                    logger.error("GitHub API HTTP %d error: %s", response.status_code, response.text)
                    response.raise_for_status()
                data = response.json()
                events_data = data
                
                # Follow pagination
                while 'next' in (response.links or {}):
                    next_url = response.links['next']['url']
                    response = client.get(next_url, headers=headers)
                    response.raise_for_status()
                    page = response.json()
                    events_data.extend(page)
                
                # Preemptive throttling using X-RateLimit-Remaining
                ratelimit_remaining = response.headers.get("X-RateLimit-Remaining")
                if ratelimit_remaining is not None:
                    try:
                        remaining = int(ratelimit_remaining)
                        if remaining <= 5:
                            reset = response.headers.get("X-RateLimit-Reset")
                            delay = 1.0
                            if reset:
                                try:
                                    # GitHub returns epoch seconds
                                    delay = max(1.0, float(reset) - time.time())
                                except (ValueError, TypeError):
                                    pass
                            logger.info("Rate limit remaining: %d, sleeping %.2fs (preemptive)", remaining, delay)
                            time.sleep(delay)
                    except (ValueError, TypeError):
                        pass  # Ignore invalid header values
                
                for event_data in events_data:
                    # Filter by date
                    event_date = datetime.fromisoformat(
                        event_data["created_at"].replace("Z", "+00:00")
                    )
                    if event_date < since_dt.replace(tzinfo=event_date.tzinfo):
                        continue
                    
                    event = self._parse_event_data(event_data)
                    
                    # Check if we've already processed this event
                    if not self.cache_manager.is_seen(event.id, "github_event"):
                        events.append(event)
                
                return events
                
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"GitHub API error: {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Error fetching user activity: {e}")
    
    def fetch_repo_activity(self, repo: str, days_back: int = 7) -> List[GitHubEvent]:
        """Fetch recent activity for a GitHub repository."""
        headers = self.auth_service.get_github_headers()
        
        # Calculate date range
        since_dt = datetime.utcnow() - timedelta(days=days_back)
        since_date = since_dt.isoformat() + "Z"
        
        events = []
        
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0), http2=True) as client:
                # Get repository events
                response = client.get(
                    f"{self.base_url}/repos/{repo}/events",
                    headers=headers,
                    params={"per_page": 100}
                )
                
                # Handle non-2xx status codes and surface 429 retry hints
                if response.status_code == 429:
                    logger.error("GitHub API rate limit exceeded for repo activity. Consider reducing request frequency.")
                    response.raise_for_status()
                elif response.status_code >= 400:
                    logger.error("GitHub API HTTP %d error for repo activity: %s", response.status_code, response.text)
                    response.raise_for_status()
                data = response.json()
                events_data = data
                
                # Follow pagination
                while 'next' in (response.links or {}):
                    next_url = response.links['next']['url']
                    response = client.get(next_url, headers=headers)
                    response.raise_for_status()
                    page = response.json()
                    events_data.extend(page)
                
                # Preemptive throttling using X-RateLimit-Remaining
                ratelimit_remaining = response.headers.get("X-RateLimit-Remaining")
                if ratelimit_remaining is not None:
                    try:
                        remaining = int(ratelimit_remaining)
                        if remaining <= 5:
                            reset = response.headers.get("X-RateLimit-Reset")
                            delay = 1.0
                            if reset:
                                try:
                                    # GitHub returns epoch seconds
                                    delay = max(1.0, float(reset) - time.time())
                                except (ValueError, TypeError):
                                    pass
                            logger.info("Rate limit remaining: %d, sleeping %.2fs (preemptive)", remaining, delay)
                            time.sleep(delay)
                    except (ValueError, TypeError):
                        pass  # Ignore invalid header values
                
                for event_data in events_data:
                    # Filter by date
                    event_date = datetime.fromisoformat(
                        event_data["created_at"].replace("Z", "+00:00")
                    )
                    if event_date < since_dt.replace(tzinfo=event_date.tzinfo):
                        continue
                    
                    event = self._parse_event_data(event_data)
                    
                    # Check if we've already processed this event
                    if not self.cache_manager.is_seen(event.id, "github_event"):
                        events.append(event)
                
                return events
                
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"GitHub API error: {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Error fetching repo activity: {e}")
    
    def _parse_event_data(self, event_data: dict) -> GitHubEvent:
        """Parse GitHub API event data into GitHubEvent model."""
        # Extract basic info
        event_id = event_data["id"]
        event_type = event_data["type"]
        repo = event_data["repo"]["name"] if event_data.get("repo") else "unknown"
        actor = event_data["actor"]["login"] if event_data.get("actor") else "unknown"
        created_at = datetime.fromisoformat(event_data["created_at"].replace("Z", "+00:00"))
        
        # Extract additional details based on event type
        details = {}
        url = None
        title = None
        body = None
        
        if event_type == "PushEvent":
            payload = event_data.get("payload", {})
            commits = payload.get("commits", [])
            
            # Extract commit SHA - try head first, then first commit
            commit_sha = payload.get("head")
            if not commit_sha and commits:
                commit_sha = commits[0].get("id") or commits[0].get("sha")
            
            details = {
                "commits": len(commits),
                "branch": payload.get("ref", "").replace("refs/heads/", ""),
                "commit_sha": commit_sha,
                "commit_messages": [
                    commit.get("message", "") 
                    for commit in commits
                ]
            }
        
        elif event_type == "PullRequestEvent":
            pr = event_data.get("payload", {}).get("pull_request", {})
            details = {
                "action": event_data.get("payload", {}).get("action"),
                "number": pr.get("number"),
                "state": pr.get("state"),
                "merged": pr.get("merged", False)
            }
            url = pr.get("html_url")
            title = pr.get("title")
            body = pr.get("body")
        
        elif event_type == "IssuesEvent":
            issue = event_data.get("payload", {}).get("issue", {})
            details = {
                "action": event_data.get("payload", {}).get("action"),
                "number": issue.get("number"),
                "state": issue.get("state")
            }
            url = issue.get("html_url")
            title = issue.get("title")
            body = issue.get("body")
        
        elif event_type == "CreateEvent":
            details = {
                "ref_type": event_data.get("payload", {}).get("ref_type"),
                "ref": event_data.get("payload", {}).get("ref")
            }
        
        elif event_type == "DeleteEvent":
            details = {
                "ref_type": event_data.get("payload", {}).get("ref_type"),
                "ref": event_data.get("payload", {}).get("ref")
            }
        
        else:
            # For other event types, store the full payload
            details = event_data.get("payload", {})
        
        return GitHubEvent(
            id=str(event_id),
            type=event_type,
            repo=repo,
            actor=actor,
            created_at=created_at,
            details=details,
            url=url,
            title=title,
            body=body
        )
    
    def save_event(self, event: GitHubEvent) -> bool:
        """Save GitHub event to JSON file."""
        try:
            # Check if already processed
            if self.cache_manager.is_seen(event.id, "github_event"):
                logger.info("Event %s already processed, skipping", event.id)
                return True
            
            logger.info("Processing event: %s in %s", event.type, event.repo)
            
            # Generate filename
            safe_repo = sanitize_filename(event.repo)
            filename = generate_filename("github_event", f"{event.id}_{safe_repo}")
            
            # Convert to dict for JSON serialization
            event_data = event.model_dump()
            
            # Save to data directory
            self.cache_manager.save_json(filename, event_data, event.created_at)
            
            # Mark as seen
            self.cache_manager.mark_seen(event.id, "github_event")
            
            logger.info("Successfully processed event: %s", event.type)
            return True
            
        except Exception as e:
            logger.exception("Error processing event %s", event.id)
            return False
    
    def get_user_info(self, username: str) -> Optional[dict]:
        """Get GitHub user information."""
        headers = self.auth_service.get_github_headers()
        
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0), http2=True) as client:
                response = client.get(f"{self.base_url}/users/{username}", headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.exception("Error getting user info for %s", username)
            return None
    
    def get_repo_info(self, repo: str) -> Optional[dict]:
        """Get GitHub repository information."""
        headers = self.auth_service.get_github_headers()
        
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=30.0), http2=True) as client:
                response = client.get(f"{self.base_url}/repos/{repo}", headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.exception("Error getting repo info for %s", repo)
            return None
