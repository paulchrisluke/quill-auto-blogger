"""
GitHub API service for fetching user and repository activity.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional
import httpx

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
        since_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat() + "Z"
        
        events = []
        
        try:
            with httpx.Client() as client:
                # Get user events
                response = client.get(
                    f"{self.base_url}/users/{username}/events",
                    headers=headers,
                    params={"per_page": 100}
                )
                response.raise_for_status()
                
                data = response.json()
                
                for event_data in data:
                    # Filter by date
                    event_date = datetime.fromisoformat(
                        event_data["created_at"].replace("Z", "+00:00")
                    )
                    if event_date < datetime.fromisoformat(since_date.replace("Z", "+00:00")):
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
        since_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat() + "Z"
        
        events = []
        
        try:
            with httpx.Client() as client:
                # Get repository events
                response = client.get(
                    f"{self.base_url}/repos/{repo}/events",
                    headers=headers,
                    params={"per_page": 100}
                )
                response.raise_for_status()
                
                data = response.json()
                
                for event_data in data:
                    # Filter by date
                    event_date = datetime.fromisoformat(
                        event_data["created_at"].replace("Z", "+00:00")
                    )
                    if event_date < datetime.fromisoformat(since_date.replace("Z", "+00:00")):
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
            details = {
                "commits": len(event_data.get("payload", {}).get("commits", [])),
                "branch": event_data.get("payload", {}).get("ref", "").replace("refs/heads/", ""),
                "commit_messages": [
                    commit.get("message", "") 
                    for commit in event_data.get("payload", {}).get("commits", [])
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
                print(f"Event {event.id} already processed, skipping")
                return True
            
            print(f"Processing event: {event.type} in {event.repo}")
            
            # Generate filename
            safe_repo = sanitize_filename(event.repo)
            filename = generate_filename("github_event", f"{event.id}_{safe_repo}")
            
            # Convert to dict for JSON serialization
            event_data = event.model_dump()
            
            # Save to data directory
            self.cache_manager.save_json(filename, event_data, event.created_at)
            
            # Mark as seen
            self.cache_manager.mark_seen(event.id, "github_event")
            
            print(f"Successfully processed event: {event.type}")
            return True
            
        except Exception as e:
            print(f"Error processing event {event.id}: {e}")
            return False
    
    def get_user_info(self, username: str) -> Optional[dict]:
        """Get GitHub user information."""
        headers = self.auth_service.get_github_headers()
        
        try:
            with httpx.Client() as client:
                response = client.get(f"{self.base_url}/users/{username}", headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Error getting user info for {username}: {e}")
            return None
    
    def get_repo_info(self, repo: str) -> Optional[dict]:
        """Get GitHub repository information."""
        headers = self.auth_service.get_github_headers()
        
        try:
            with httpx.Client() as client:
                response = client.get(f"{self.base_url}/repos/{repo}", headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Error getting repo info for {repo}: {e}")
            return None
