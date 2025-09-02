"""
GitHub publisher service for publishing markdown content to GitHub repositories.
"""

import base64
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path
import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class GitHubPublisher:
    """Handles publishing markdown content to GitHub repositories."""
    
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError(
                "GITHUB_TOKEN environment variable is required. "
                "Please set it to a valid GitHub personal access token."
            )
        
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "quill-auto-blogger/1.0"
        }
    
    def publish_markdown(
        self,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
        path: str,
        content_md: str,
        commit_message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
        create_pr: bool = False,
        pr_title: Optional[str] = None,
        pr_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Publish markdown content to a GitHub repository.
        
        Args:
            owner: Repository owner (e.g., "paulchrisluke")
            repo: Repository name (e.g., "pcl-labs")
            branch: Target branch (default: "main")
            path: File path in repository (e.g., "content/blog/2025/08/27.md")
            content_md: Markdown content to publish
            commit_message: Git commit message
            author_name: Optional author name for commit
            author_email: Optional author email for commit
            create_pr: Whether to create a pull request
            pr_title: Optional PR title (defaults to commit message)
            pr_body: Optional PR body
            
        Returns:
            Dictionary with action result and metadata
        """
        # Validate inputs
        if not owner or not repo:
            raise ValueError("owner and repo are required")
        if not path:
            raise ValueError("path is required")
        if not content_md:
            raise ValueError("content_md is required")
        if not commit_message:
            raise ValueError("commit_message is required")
        
        # Base64 encode content
        content_bytes = content_md.encode('utf-8')
        content_b64 = base64.b64encode(content_bytes).decode('utf-8')
        
        # Check if file exists and get current SHA
        current_sha = None
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                    headers=self.headers,
                    params={"ref": branch}
                )
                
                if response.status_code == 200:
                    # File exists, get SHA for update
                    file_data = response.json()
                    current_sha = file_data["sha"]
                    
                    # Check if content is identical
                    if file_data["content"] == content_b64:
                        return {
                            "action": "skipped",
                            "branch": branch,
                            "path": path,
                            "sha": current_sha,
                            "html_url": file_data["html_url"],
                            "pr_url": None
                        }
                elif response.status_code != 404:
                    # Unexpected error
                    response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to check file existence: {e}")
            raise RuntimeError(f"Failed to check file existence: {e}")
        except httpx.RequestError as e:
            logger.error(f"Network error checking file existence: {e}")
            raise RuntimeError(f"Network error: {e}")
        
        # Initialize feature branch variable
        feature_branch = None
        
        # Determine target branch for commit
        target_branch = branch
        if create_pr:
            # Create feature branch name
            feature_branch = f"blog/{path.replace('/', '_').replace('.md', '')}"
            target_branch = feature_branch
            
            # Ensure feature branch exists before committing
            try:
                with httpx.Client(timeout=30.0) as client:
                    # Get the latest commit SHA from base branch
                    response = client.get(
                        f"{self.base_url}/repos/{owner}/{repo}/git/refs/heads/{branch}",
                        headers=self.headers
                    )
                    response.raise_for_status()
                    base_sha = response.json()["object"]["sha"]
                    
                    # Create feature branch from base branch
                    branch_data = {
                        "ref": f"refs/heads/{feature_branch}",
                        "sha": base_sha
                    }
                    
                    response = client.post(
                        f"{self.base_url}/repos/{owner}/{repo}/git/refs",
                        headers=self.headers,
                        json=branch_data
                    )
                    
                    if response.status_code == 422:
                        # Branch might already exist, try to get it
                        response = client.get(
                            f"{self.base_url}/repos/{owner}/{repo}/git/refs/heads/{feature_branch}",
                            headers=self.headers
                        )
                        if response.status_code != 200:
                            response.raise_for_status()
                    else:
                        response.raise_for_status()
                        
            except Exception as e:
                logger.error(f"Failed to create/verify feature branch: {e}")
                raise RuntimeError(f"Failed to create feature branch: {e}")
        
        # Prepare commit data
        commit_data = {
            "message": commit_message,
            "content": content_b64,
            "branch": target_branch
        }
        
        # Add SHA if updating existing file
        if current_sha:
            commit_data["sha"] = current_sha
        
        # Add author info if provided
        if author_name and author_email:
            commit_data["author"] = {
                "name": author_name,
                "email": author_email
            }
        
        # Create or update file
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.put(
                    f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                    headers=self.headers,
                    json=commit_data
                )
                response.raise_for_status()
                
                file_data = response.json()
                action = "updated" if current_sha else "created"
                
                result = {
                    "action": action,
                    "branch": branch,
                    "path": path,
                    "sha": file_data["content"]["sha"],
                    "html_url": file_data["content"]["html_url"],
                    "pr_url": None
                }
                
                # Create PR if requested
                if create_pr:
                    pr_result = self._create_pull_request(
                        owner, repo, feature_branch, path, 
                        pr_title or commit_message, pr_body
                    )
                    result["pr_url"] = pr_result["html_url"]
                
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to publish content: {e}")
            if e.response.status_code == 401:
                raise RuntimeError("GitHub authentication failed. Check your GITHUB_TOKEN.")
            elif e.response.status_code == 403:
                raise RuntimeError("GitHub permission denied. Check repository access.")
            elif e.response.status_code == 404:
                raise RuntimeError(f"Repository {owner}/{repo} not found or access denied.")
            else:
                raise RuntimeError(f"GitHub API error: {e}")
        except httpx.RequestError as e:
            logger.error(f"Network error publishing content: {e}")
            raise RuntimeError(f"Network error: {e}")
    
    def _create_pull_request(
        self, 
        owner: str, 
        repo: str, 
        feature_branch: str, 
        path: str,
        title: str,
        body: Optional[str]
    ) -> Dict[str, Any]:
        """Create a pull request for the published content."""
        # The feature branch is already created and committed to by publish_markdown
        # We need the base branch (e.g., 'main') to create the PR against it.
        base_branch_name = "main"  # Assuming 'main' as the base branch for the PR

        try:
            with httpx.Client(timeout=30.0) as client:
                pr_data = {
                    "title": title,
                    "head": feature_branch,
                    "base": base_branch_name
                }
                
                if body:
                    pr_data["body"] = body
                
                response = client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls",
                    headers=self.headers,
                    json=pr_data
                )
                response.raise_for_status()
                
                return response.json()
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create pull request: {e}")
            raise RuntimeError(f"Failed to create pull request: {e}")
        except httpx.RequestError as e:
            logger.error(f"Network error creating pull request: {e}")
            raise RuntimeError(f"Network error: {e}")


def publish_markdown(
    *,
    owner: str,
    repo: str,
    branch: str = "main",
    path: str,
    content_md: str,
    commit_message: str,
    author_name: Optional[str] = None,
    author_email: Optional[str] = None,
    create_pr: bool = False,
    pr_title: Optional[str] = None,
    pr_body: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to publish markdown content to GitHub.
    
    Args:
        owner: Repository owner
        repo: Repository name
        branch: Target branch (default: "main")
        path: File path in repository
        content_md: Markdown content to publish
        commit_message: Git commit message
        author_name: Optional author name for commit
        author_email: Optional author email for commit
        create_pr: Whether to create a pull request
        pr_title: Optional PR title
        pr_body: Optional PR body
        
    Returns:
        Dictionary with action result and metadata
    """
    publisher = GitHubPublisher()
    return publisher.publish_markdown(
        owner=owner,
        repo=repo,
        branch=branch,
        path=path,
        content_md=content_md,
        commit_message=commit_message,
        author_name=author_name,
        author_email=author_email,
        create_pr=create_pr,
        pr_title=pr_title,
        pr_body=pr_body
    )
