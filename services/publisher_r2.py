"""
R2 publisher service for static site and blog JSON publishing.
Handles idempotent uploads with MD5/ETag comparison.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional
import boto3
from botocore.exceptions import ClientError

from services.auth import AuthService

logger = logging.getLogger(__name__)


class R2Publisher:
    """Handles publishing static site files and blog JSON to R2 with idempotency."""
    
    def __init__(self):
        self.auth_service = AuthService()
        self.r2_credentials = self.auth_service.get_r2_credentials()
        
        if not self.r2_credentials:
            raise ValueError(
                "R2 credentials not found. Please set R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_S3_ENDPOINT, and R2_BUCKET environment variables"
            )
        
        # Initialize S3 client for R2
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
        
        self.bucket = self.r2_credentials.bucket
    
    def _hash_md5(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _should_skip(self, r2_key: str, local_md5: str) -> bool:
        """Check if file should be skipped (identical content already exists)."""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=r2_key)
            etag = response.get('ETag', '').strip('"')  # Remove quotes from ETag
            return etag == local_md5
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code in ('404', 'NotFound', 'NoSuchKey'):
                return False  # File doesn't exist, should upload
            logger.warning(f"Error checking R2 object {r2_key}: {e}", exc_info=True)
            return False  # On error, proceed with upload
    
    def _headers_for(self, file_path: Path) -> Dict[str, str]:
        """Get appropriate headers for file type."""
        suffix = file_path.suffix.lower()
        
        if suffix == '.html':
            return {
                'ContentType': 'text/html; charset=utf-8',
                'CacheControl': 'public, max-age=3600'
            }
        elif suffix == '.json':
            return {
                'ContentType': 'application/json',
                'CacheControl': 'public, max-age=300'
            }
        else:
            return {
                'ContentType': 'application/octet-stream',
                'CacheControl': 'public, max-age=300'
            }
    
    def publish_site(self, local_dir: Path) -> Dict[str, bool]:
        """Upload index.html and docs.html idempotently."""
        results = {}
        
        if not local_dir.exists():
            logger.error(f"Site directory does not exist: {local_dir}")
            return results
        
        site_files = ['index.html', 'docs.html']
        
        for filename in site_files:
            file_path = local_dir / filename
            if not file_path.exists():
                logger.warning(f"Site file not found: {file_path}")
                results[filename] = False
                continue
            
            try:
                local_md5 = self._hash_md5(file_path)
                r2_key = filename
                
                if self._should_skip(r2_key, local_md5):
                    logger.info(f"↻ Skipped {filename} (identical content)")
                    results[filename] = True
                    continue
                
                # Upload file
                with open(file_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket,
                        Key=r2_key,
                        Body=f,
                        **self._headers_for(file_path)
                    )
                
                logger.info(f"✓ Uploaded {filename}")
                results[filename] = True
                
            except Exception as e:
                logger.error(f"✗ Failed to upload {filename}: {e}")
                results[filename] = False
        
        return results
    
    def publish_blogs(self, blogs_dir: Path) -> Dict[str, bool]:
        """Upload API-v3 digest JSON files idempotently."""
        results = {}
        
        if not blogs_dir.exists():
            logger.error(f"Blogs directory does not exist: {blogs_dir}")
            return results
        
        # Find all API-v3 digest files
        api_v3_files = list(blogs_dir.rglob("API-v3-*_digest.json"))
        
        if not api_v3_files:
            logger.info("No API-v3 digest files found")
            return results
        
        for file_path in api_v3_files:
            try:
                # Calculate R2 key: blogs/YYYY-MM-DD/API-v3-YYYY-MM-DD_digest.json
                relative_path = file_path.relative_to(blogs_dir)
                r2_key = f"blogs/{relative_path}"
                
                local_md5 = self._hash_md5(file_path)
                
                if self._should_skip(r2_key, local_md5):
                    logger.info(f"↻ Skipped {r2_key} (identical content)")
                    results[str(relative_path)] = True
                    continue
                
                # Upload file
                with open(file_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket,
                        Key=r2_key,
                        Body=f,
                        **self._headers_for(file_path)
                    )
                
                logger.info(f"✓ Uploaded {r2_key}")
                results[str(relative_path)] = True
                
            except Exception as e:
                logger.error(f"✗ Failed to upload {file_path}: {e}")
                results[str(relative_path)] = False
        
        return results
