"""
GitHub publisher service for publishing markdown content to GitHub repositories.
"""

import base64
import logging
import os
from typing import Dict, Any, Optional, List
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
        pr_body: Optional[str] = None,
        include_assets: bool = False,
        assets_info: Optional[Dict[str, Any]] = None
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
        
        # Skip file existence check when creating PR (we're creating new content)
        if not create_pr:
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
            # Check for existing PR first
            pr_title = pr_title or commit_message
            existing_pr = self._find_existing_pr(owner, repo, pr_title)
            
            if existing_pr:
                # Use existing PR branch
                feature_branch = existing_pr["head"]["ref"]
                target_branch = feature_branch
                logger.info(f"Found existing PR #{existing_pr['number']}, using branch: {feature_branch}")
            else:
                # Create new feature branch name
                feature_branch = f"blog/{path.replace('/', '_').replace('.md', '')}"
                target_branch = feature_branch
                logger.info(f"Creating new PR with feature branch: {feature_branch}")
            
            logger.info(f"Target branch for commit: {target_branch}")
        
        # Publish assets if requested
        asset_results = []
        if include_assets and assets_info:
            asset_results = self._publish_assets(
                owner=owner,
                repo=repo,
                branch=target_branch,
                assets_info=assets_info
            )
            
            # Ensure feature branch exists before committing
            # Check if we're using an existing PR branch
            existing_pr = self._find_existing_pr(owner, repo, pr_title or commit_message)
            if existing_pr and existing_pr["head"]["ref"] == feature_branch:
                logger.info(f"Using existing branch {feature_branch} from PR #{existing_pr['number']}")
            else:
                # Create new branch
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
        
        # Re-check file SHA on target branch before committing
        # This prevents 422 errors when the file differs on the feature branch
        if current_sha and target_branch != branch:
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(
                        f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                        headers=self.headers,
                        params={"ref": target_branch}
                    )
                    
                    if response.status_code == 200:
                        # File exists on target branch, use its SHA
                        file_data = response.json()
                        current_sha = file_data["content"]["sha"]
                    elif response.status_code == 404:
                        # File doesn't exist on target branch, don't include SHA
                        current_sha = None
                    else:
                        response.raise_for_status()
            except Exception as e:
                logger.warning(f"Failed to re-check file SHA on target branch: {e}")
                # Continue with original SHA if re-check fails
        
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
                        owner, repo, feature_branch, branch, 
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
    
    def _find_existing_pr(self, owner: str, repo: str, title: str) -> Optional[Dict[str, Any]]:
        """Find an existing pull request with the given title."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls",
                    headers=self.headers,
                    params={"state": "open", "per_page": 100}
                )
                response.raise_for_status()
                
                prs = response.json()
                for pr in prs:
                    if pr["title"] == title:
                        return pr
                return None
        except Exception as e:
            logger.warning(f"Failed to check for existing PRs: {e}")
            return None

    def _create_pull_request(
        self, 
        owner: str, 
        repo: str, 
        feature_branch: str, 
        base_branch: str,
        title: str,
        body: Optional[str]
    ) -> Dict[str, Any]:
        """Create a pull request for the published content."""

        try:
            with httpx.Client(timeout=30.0) as client:
                pr_data = {
                    "title": title,
                    "head": feature_branch,
                    "base": base_branch
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
    
    def _publish_assets(
        self,
        owner: str,
        repo: str,
        branch: str,
        assets_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Publish story assets (videos, thumbnails) to GitHub repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            branch: Target branch
            assets_info: Dictionary with asset information
            
        Returns:
            List of asset publishing results
        """
        results = []
        
        try:
            with httpx.Client(timeout=30.0) as client:
                for asset_path, asset_info in assets_info.items():
                    # Read asset file
                    local_path = asset_info["local_path"]
                    if not Path(local_path).exists():
                        logger.warning(f"Asset file not found: {local_path}")
                        continue
                    
                    # Read and encode asset
                    with open(local_path, 'rb') as f:
                        content_bytes = f.read()
                    content_b64 = base64.b64encode(content_bytes).decode('utf-8')
                    
                    # Check if asset exists and get SHA
                    current_sha = None
                    try:
                        response = client.get(
                            f"{self.base_url}/repos/{owner}/{repo}/contents/{asset_path}",
                            headers=self.headers,
                            params={"ref": branch}
                        )
                        
                        if response.status_code == 200:
                            file_data = response.json()
                            current_sha = file_data["sha"]
                            
                            # Check if content is identical
                            if file_data["content"] == content_b64:
                                logger.info(f"Asset {asset_path} unchanged, skipping")
                                continue
                        elif response.status_code != 404:
                            response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code != 404:
                            logger.warning(f"Failed to check asset {asset_path}: {e}")
                            continue
                    
                    # Prepare commit data
                    commit_data = {
                        "message": f"Add asset: {asset_path}",
                        "content": content_b64,
                        "branch": branch
                    }
                    
                    if current_sha:
                        commit_data["sha"] = current_sha
                    
                    # Publish asset
                    response = client.put(
                        f"{self.base_url}/repos/{owner}/{repo}/contents/{asset_path}",
                        headers=self.headers,
                        json=commit_data
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    # GitHub API returns nested structure for content updates
                    if "content" in result and "sha" in result["content"]:
                        content_sha = result["content"]["sha"]
                    elif "sha" in result:
                        content_sha = result["sha"]
                    else:
                        logger.error(f"Response missing 'sha' field: {result}")
                        raise RuntimeError(f"GitHub API response missing 'sha' field: {result}")
                    
                    results.append({
                        "path": asset_path,
                        "action": "updated" if current_sha else "created",
                        "sha": content_sha,
                        "html_url": result.get("html_url", "")
                    })
                    
                    logger.info(f"Published asset: {asset_path}")
                    
        except Exception as e:
            logger.error(f"Failed to publish assets: {e}")
            raise RuntimeError(f"Failed to publish assets: {e}")
        
        return results


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
    pr_body: Optional[str] = None,
    include_assets: bool = False,
    assets_info: Optional[Dict[str, Any]] = None
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
        pr_body=pr_body,
        include_assets=include_assets,
        assets_info=assets_info
    )
