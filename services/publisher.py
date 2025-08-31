"""
Video publisher service for local and R2 storage.
"""

import os
import logging
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime
import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class Publisher:
    """Handles video publishing to local storage or R2."""
    
    def __init__(self):
        self.publish_target = os.getenv("PUBLISH_TARGET", "local")
        self.public_root = Path(os.getenv("PUBLIC_ROOT", "public"))
        self.public_base_url = os.getenv("PUBLIC_BASE_URL", "")
        self.r2_bucket = os.getenv("R2_BUCKET", "")
        self.r2_public_base_url = os.getenv("R2_PUBLIC_BASE_URL", "")
        
        # Cloudflare credentials (reuse existing pattern)
        self.cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    
    def publish_video(self, local_path: str, target_date: str, story_id: str) -> str:
        """
        Publish video to target storage and return public URL/path.
        
        Args:
            local_path: Path to local video file
            target_date: Date in YYYY-MM-DD format
            story_id: Story identifier
            
        Returns:
            Public URL or path to the published video
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local video not found: {local_path}")
        
        # Parse date for directory structure
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        year = str(date_obj.year)
        month = f"{date_obj.month:02d}"
        day = f"{date_obj.day:02d}"
        
        if self.publish_target == "r2":
            return self._publish_to_r2(local_path, year, month, day, story_id)
        else:
            return self._publish_to_local(local_path, year, month, day, story_id)
    
    def _publish_to_local(self, local_path: str, year: str, month: str, day: str, story_id: str) -> str:
        """Publish video to local public directory."""
        # Create directory structure
        target_dir = self.public_root / "stories" / year / month / day
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Target file path
        target_path = target_dir / f"{story_id}.mp4"
        
        # Check if file already exists
        if target_path.exists():
            logger.info(f"Video already exists at {target_path}, reusing")
        else:
            # Copy file
            shutil.copy2(local_path, target_path)
            logger.info(f"Published video to {target_path}")
        
        # Return public path
        public_path = f"/stories/{year}/{month}/{day}/{story_id}.mp4"
        
        # Convert to absolute URL if base URL is configured
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}{public_path}"
        
        return public_path
    
    def _publish_to_r2(self, local_path: str, year: str, month: str, day: str, story_id: str) -> str:
        """Publish video to R2 storage."""
        if not self.cloudflare_account_id or not self.cloudflare_api_token:
            raise ValueError("Cloudflare credentials required for R2 publishing")
        
        if not self.r2_bucket:
            raise ValueError("R2_BUCKET environment variable required for R2 publishing")
        
        # R2 key path
        r2_key = f"stories/{year}/{month}/{day}/{story_id}.mp4"
        
        # Check if file already exists in R2
        if self._r2_file_exists(r2_key):
            logger.info(f"Video already exists in R2 at {r2_key}, reusing")
        else:
            # Upload to R2
            self._upload_to_r2(local_path, r2_key)
            logger.info(f"Published video to R2: {r2_key}")
        
        # Return public URL
        if self.r2_public_base_url:
            return f"{self.r2_public_base_url.rstrip('/')}/{r2_key}"
        else:
            # Fallback to R2 direct URL format
            return f"https://{self.r2_bucket}.r2.cloudflarestorage.com/{r2_key}"
    
    def _r2_file_exists(self, key: str) -> bool:
        """Check if file exists in R2 bucket."""
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/storage/buckets/{self.r2_bucket}/objects/{key}"
            
            with httpx.Client() as client:
                response = client.head(
                    url,
                    headers={"Authorization": f"Bearer {self.cloudflare_api_token}"}
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Could not check R2 file existence for {key}: {e}")
            return False
    
    def _upload_to_r2(self, local_path: str, r2_key: str) -> None:
        """Upload file to R2 bucket."""
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/storage/buckets/{self.r2_bucket}/objects/{r2_key}"
            
            with open(local_path, 'rb') as f:
                with httpx.Client() as client:
                    response = client.put(
                        url,
                        content=f.read(),
                        headers={
                            "Authorization": f"Bearer {self.cloudflare_api_token}",
                            "Content-Type": "video/mp4"
                        }
                    )
                    response.raise_for_status()
                    
        except Exception as e:
            raise RuntimeError(f"Failed to upload to R2: {e}")


def publish_video(local_path: str, target_date: str, story_id: str) -> str:
    """
    Convenience function to publish a video.
    
    Args:
        local_path: Path to local video file
        target_date: Date in YYYY-MM-DD format
        story_id: Story identifier
        
    Returns:
        Public URL or path to the published video
    """
    publisher = Publisher()
    return publisher.publish_video(local_path, target_date, story_id)
