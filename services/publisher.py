"""
Video publisher service for local and R2 storage.
"""

import os
import logging
import shutil
import re
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

from services.auth import AuthService

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def sanitize_story_id(story_id: str) -> str:
    """Sanitize story_id to prevent path traversal and ensure safe filenames."""
    if not story_id:
        return "unknown"
    
    # Remove any path traversal attempts and normalize
    sanitized = re.sub(r'[./\\]', '_', story_id)
    
    # Remove any other potentially dangerous characters
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', sanitized)
    
    # Ensure it's not empty after sanitization
    if not sanitized:
        return "unknown"
    
    # Limit length to prevent extremely long filenames
    return sanitized[:50]


class Publisher:
    """Handles video publishing to local storage or R2.
    
    Note: R2 object operations now use the S3-compatible API with Access Key ID/Secret
    instead of the deprecated Bearer token approach. Use R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY, and R2_S3_ENDPOINT environment variables.
    """
    
    # Allowed publish targets
    ALLOWED_TARGETS = {"local", "r2"}
    
    def __init__(self):
        # Normalize and validate PUBLISH_TARGET
        publish_target = os.getenv("PUBLISH_TARGET", "local").lower().strip()
        if publish_target not in self.ALLOWED_TARGETS:
            raise ValueError(
                f"Invalid PUBLISH_TARGET '{publish_target}'. "
                f"Must be one of: {', '.join(sorted(self.ALLOWED_TARGETS))}"
            )
        self.publish_target = publish_target
        
        self.public_root = Path(os.getenv("PUBLIC_ROOT", "public"))
        self.public_base_url = os.getenv("PUBLIC_BASE_URL", "")
        
        # Initialize AuthService for R2 credentials
        self.auth_service = AuthService()
        
        # Get R2 credentials from AuthService
        self.r2_credentials = None
        if self.publish_target == "r2":
            self.r2_credentials = self.auth_service.get_r2_credentials()
            if not self.r2_credentials:
                raise ValueError(
                    "R2 credentials not found. Please set R2_ACCESS_KEY_ID, "
                    "R2_SECRET_ACCESS_KEY, R2_S3_ENDPOINT, and R2_BUCKET environment variables"
                )
            
            # Initialize S3 client for R2
            # Handle both Pydantic SecretStr and plain string types for secret_access_key
            secret_key = self.r2_credentials.secret_access_key
            if hasattr(secret_key, 'get_secret_value'):
                aws_secret_access_key = secret_key.get_secret_value()
            else:
                aws_secret_access_key = str(secret_key) if secret_key is not None else ""
            
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.r2_credentials.access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                endpoint_url=self.r2_credentials.endpoint,
                region_name=self.r2_credentials.region
            )
    
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
        
        # Sanitize story_id to prevent path traversal
        sanitized_story_id = sanitize_story_id(story_id)
        
        # Parse date for directory structure
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        year = str(date_obj.year)
        month = f"{date_obj.month:02d}"
        day = f"{date_obj.day:02d}"
        
        if self.publish_target == "r2":
            return self._publish_to_r2(local_path, year, month, day, sanitized_story_id)
        else:
            return self._publish_to_local(local_path, year, month, day, sanitized_story_id)
    
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
        """Publish video to R2 storage using Cloudflare REST API."""
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
        if self.r2_credentials.public_base_url:
            return f"{self.r2_credentials.public_base_url.rstrip('/')}/{r2_key}"
        else:
            # Generate presigned URL for private bucket access
            try:
                presigned_url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.r2_credentials.bucket,
                        'Key': r2_key
                    },
                    ExpiresIn=3600  # 1 hour expiration
                )
                return presigned_url
            except Exception as e:
                logger.error(f"Failed to generate presigned URL for {r2_key}: {e}")
                raise RuntimeError(
                    f"R2_PUBLIC_BASE_URL not configured and failed to generate presigned URL. "
                    f"Please set R2_PUBLIC_BASE_URL for public access or ensure R2 credentials are valid."
                )
    
    def _r2_file_exists(self, key: str) -> bool:
        """Check if file exists in R2 bucket using S3-compatible API."""
        try:
            self.s3_client.head_object(Bucket=self.r2_credentials.bucket, Key=key)
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404' or error_code == 'NoSuchKey':
                return False
            logger.warning(f"Could not check R2 file existence for {key}: {e}")
            return False
        except Exception as e:
            logger.warning(f"Could not check R2 file existence for {key}: {e}")
            return False
    
    def _upload_to_r2(self, local_path: str, r2_key: str) -> None:
        """Upload file to R2 bucket using S3-compatible API."""
        try:
            with open(local_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.r2_credentials.bucket,
                    r2_key,
                    ExtraArgs={'ContentType': 'video/mp4'}
                )
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"Failed to upload {local_path} to R2 key {r2_key}: {e}")
            raise RuntimeError(f"Failed to upload to R2: {e}")
        except Exception as e:
            logger.error(f"Unexpected error uploading {local_path} to R2 key {r2_key}: {e}")
            raise RuntimeError(f"Failed to upload to R2: {e}")
    
    def get_asset_url(self, date: str, story_id: str, asset_type: str = "video") -> Optional[str]:
        """
        Get public URL for a story asset.
        
        Args:
            date: Date in YYYY-MM-DD format
            story_id: Story identifier
            asset_type: Type of asset (video, image, highlight)
            
        Returns:
            Public URL for the asset, or None if not found
        """
        try:
            # Parse date
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            year = str(date_obj.year)
            month = f"{date_obj.month:02d}"
            day = f"{date_obj.day:02d}"
            
            # Sanitize story ID
            safe_story_id = sanitize_story_id(story_id)
            
            if asset_type == "video":
                # Get video URL
                if self.publish_target == "r2":
                    r2_key = f"stories/{year}/{month}/{day}/{safe_story_id}.mp4"
                    if self._r2_file_exists(r2_key):
                        if self.r2_credentials.public_base_url:
                            return f"{self.r2_credentials.public_base_url.rstrip('/')}/{r2_key}"
                        else:
                            # Generate presigned URL
                            return self.s3_client.generate_presigned_url(
                                'get_object',
                                Params={'Bucket': self.r2_credentials.bucket, 'Key': r2_key},
                                ExpiresIn=3600
                            )
                else:
                    # Local storage
                    local_path = self.public_root / "stories" / year / month / day / f"{safe_story_id}.mp4"
                    if local_path.exists():
                        if self.public_base_url:
                            return f"{self.public_base_url.rstrip('/')}/stories/{year}/{month}/{day}/{safe_story_id}.mp4"
                        else:
                            return f"/stories/{year}/{month}/{day}/{safe_story_id}.mp4"
            
            elif asset_type == "image":
                # For images, check intro first, then why, then outro
                if self.publish_target == "r2":
                    for img_type in ["intro", "why", "outro"]:
                        r2_key = f"stories/{year}/{month}/{day}/{safe_story_id}_{img_type}.png"
                        if self._r2_file_exists(r2_key):
                            if self.r2_credentials.public_base_url:
                                return f"{self.r2_credentials.public_base_url.rstrip('/')}/{r2_key}"
                            else:
                                return self.s3_client.generate_presigned_url(
                                    'get_object',
                                    Params={'Bucket': self.r2_credentials.bucket, 'Key': r2_key},
                                    ExpiresIn=3600
                                )
                else:
                    # Local storage
                    for img_type in ["intro", "why", "outro"]:
                        local_path = self.public_root / "stories" / year / month / day / f"{safe_story_id}_{img_type}.png"
                        if local_path.exists():
                            if self.public_base_url:
                                return f"{self.public_base_url.rstrip('/')}/stories/{year}/{month}/{day}/{safe_story_id}_{img_type}.png"
                            else:
                                return f"/stories/{year}/{month}/{day}/{safe_story_id}_{img_type}.png"
            
            elif asset_type == "highlight":
                # For highlights, check hl_01, hl_02, etc.
                if self.publish_target == "r2":
                    for hl_num in range(1, 10):  # Check up to hl_09
                        r2_key = f"stories/{year}/{month}/{day}/{safe_story_id}_hl_{hl_num:02d}.png"
                        if self._r2_file_exists(r2_key):
                            if self.r2_credentials.public_base_url:
                                return f"{self.r2_credentials.public_base_url.rstrip('/')}/{r2_key}"
                            else:
                                return self.s3_client.generate_presigned_url(
                                    'get_object',
                                    Params={'Bucket': self.r2_credentials.bucket, 'Key': r2_key},
                                    ExpiresIn=3600
                                )
                else:
                    # Local storage
                    for hl_num in range(1, 10):  # Check up to hl_09
                        local_path = self.public_root / "stories" / year / month / day / f"{safe_story_id}_hl_{hl_num:02d}.png"
                        if local_path.exists():
                            if self.public_base_url:
                                return f"{self.public_base_url.rstrip('/')}/stories/{year}/{month}/{day}/{safe_story_id}_hl_{hl_num:02d}.png"
                            else:
                                return f"/stories/{year}/{month}/{day}/{safe_story_id}_hl_{hl_num:02d}.png"
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get asset URL for {date}/{story_id}/{asset_type}: {e}")
            return None
    
    def list_story_assets(self, date: str, story_id: str) -> Dict[str, List[str]]:
        """
        List all available assets for a story.
        
        Args:
            date: Date in YYYY-MM-DD format
            story_id: Story identifier
            
        Returns:
            Dictionary mapping asset types to lists of asset URLs
        """
        assets = {
            "video": None,
            "images": [],
            "highlights": []
        }
        
        try:
            # Get video
            video_url = self.get_asset_url(date, story_id, "video")
            if video_url:
                assets["video"] = video_url
            
            # Get images
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            year = str(date_obj.year)
            month = f"{date_obj.month:02d}"
            day = f"{date_obj.day:02d}"
            safe_story_id = sanitize_story_id(story_id)
            
            if self.publish_target == "r2":
                # Check R2 for images
                for img_type in ["intro", "why", "outro"]:
                    r2_key = f"stories/{year}/{month}/{day}/{safe_story_id}_{img_type}.png"
                    if self._r2_file_exists(r2_key):
                        if self.r2_credentials.public_base_url:
                            assets["images"].append(f"{self.r2_credentials.public_base_url.rstrip('/')}/{r2_key}")
                        else:
                            assets["images"].append(self.s3_client.generate_presigned_url(
                                'get_object',
                                Params={'Bucket': self.r2_credentials.bucket, 'Key': r2_key},
                                ExpiresIn=3600
                            ))
                
                # Check for highlights
                for i in range(1, 10):  # Check for up to 9 highlights
                    r2_key = f"stories/{year}/{month}/{day}/{safe_story_id}_hl_{i:02d}.png"
                    if self._r2_file_exists(r2_key):
                        if self.r2_credentials.public_base_url:
                            assets["highlights"].append(f"{self.r2_credentials.public_base_url.rstrip('/')}/{r2_key}")
                        else:
                            assets["highlights"].append(self.s3_client.generate_presigned_url(
                                'get_object',
                                Params={'Bucket': self.r2_credentials.bucket, 'Key': r2_key},
                                ExpiresIn=3600
                            ))
            else:
                # Local storage
                story_path = self.public_root / "stories" / year / month / day
                if story_path.exists():
                    for asset_file in story_path.glob(f"{safe_story_id}_*.png"):
                        # Separate highlights from regular images
                        if "_hl_" in asset_file.name:
                            # This is a highlight file
                            if self.public_base_url:
                                assets["highlights"].append(f"{self.public_base_url.rstrip('/')}/stories/{year}/{month}/{day}/{asset_file.name}")
                            else:
                                assets["highlights"].append(f"/stories/{year}/{month}/{day}/{asset_file.name}")
                        else:
                            # This is a regular image (intro, why, outro, etc.)
                            if self.public_base_url:
                                assets["images"].append(f"{self.public_base_url.rstrip('/')}/stories/{year}/{month}/{day}/{asset_file.name}")
                            else:
                                assets["images"].append(f"/stories/{year}/{month}/{day}/{asset_file.name}")
            
            return assets
            
        except Exception as e:
            logger.error(f"Failed to list story assets for {date}/{story_id}: {e}")
            return assets


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
