"""
Utility functions for caching, deduplication, and file management.
"""

import json
import os
import shutil
import tempfile
import logging
import errno
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

from models import SeenIds, CacheEntry

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching and deduplication of fetched data."""
    
    def __init__(self):
        self.data_dir = Path("data")
        self.cache_dir = Path.home() / ".cache" / "my-activity"
        self.seen_ids_file = self.data_dir / "seen_ids.json"
        
        # Ensure directories exist
        self.data_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create seen IDs
        self.seen_ids = self._load_seen_ids()
    
    def _load_seen_ids(self) -> SeenIds:
        """Load seen IDs from file or create new."""
        if self.seen_ids_file.exists():
            try:
                with open(self.seen_ids_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return SeenIds(**data)
            except Exception:
                pass
        
        return SeenIds()
    
    def _save_seen_ids(self):
        """Save seen IDs to file."""
        self.seen_ids.last_updated = datetime.now()
        with open(self.seen_ids_file, 'w', encoding='utf-8') as f:
            f.write(self.seen_ids.model_dump_json(indent=2))
    
    def is_seen(self, item_id: str, item_type: str) -> bool:
        """Check if an item has been seen before."""
        if item_type == "twitch_clip":
            return item_id in self.seen_ids.twitch_clips
        elif item_type == "github_event":
            return item_id in self.seen_ids.github_events
        return False
    
    def mark_seen(self, item_id: str, item_type: str):
        """Mark an item as seen."""
        if item_type == "twitch_clip":
            if item_id not in self.seen_ids.twitch_clips:
                self.seen_ids.twitch_clips.append(item_id)
        elif item_type == "github_event":
            if item_id not in self.seen_ids.github_events:
                self.seen_ids.github_events.append(item_id)
        
        self._save_seen_ids()
    
    def get_data_dir(self, date: Optional[datetime] = None) -> Path:
        """Get the data directory for a specific date."""
        if date is None:
            date = datetime.now()
        
        date_dir = self.data_dir / date.strftime("%Y-%m-%d")
        date_dir.mkdir(exist_ok=True)
        return date_dir
    
    def _resolve_secure_path(self, filename: str, date: Optional[datetime] = None) -> Path:
        """
        Resolve a secure file path within the data directory.
        
        This method prevents path traversal attacks by:
        1. Checking for path traversal attempts before sanitization
        2. Sanitizing the filename
        3. Resolving the path relative to the data directory
        4. Ensuring the final path stays within the data directory
        
        Args:
            filename: The filename to resolve
            date: Optional date for subdirectory organization
            
        Returns:
            A secure Path object within the data directory
            
        Raises:
            ValueError: If the resolved path would escape the data directory
        """
        # Check for path traversal attempts before sanitization
        # Parse the filename and check each component for traversal attempts
        try:
            # Use pathlib.Path to parse the filename and get its components
            path_obj = Path(filename)
            
            # Reject absolute paths
            if path_obj.is_absolute():
                raise ValueError(f"Absolute path not allowed: {filename}")
            # Reject drive-qualified names (Windows)
            if getattr(path_obj, "drive", ""):
                raise ValueError(f"Drive-qualified name not allowed: {filename}")
            
            # Check each path component for traversal attempts
            for component in path_obj.parts:
                if component == '..':
                    raise ValueError(f"Path traversal detected: {filename} contains '..' component")
                elif component == '.':
                    raise ValueError(f"Path traversal detected: {filename} contains '.' component")
            
            # Reject filenames containing path separators (should be a single component)
            if len(path_obj.parts) > 1:
                raise ValueError(f"Path separators not allowed in filename: {filename}")
                
        except ValueError:
            # Re-raise ValueError exceptions from our checks
            raise
        except Exception as e:
            # Handle any other path parsing errors
            raise ValueError(f"Invalid filename format: {filename}") from e
        
        # Sanitize the filename
        sanitized_filename = sanitize_filename(filename)
        
        # Check for empty sanitized filename
        if not sanitized_filename:
            raise ValueError(f"Empty/invalid filename after sanitization: '{filename}'")
        
        # Get the base data directory
        data_dir = self.get_data_dir(date)
        
        # Resolve the path relative to the data directory
        try:
            # Use resolve() to handle any path components and get absolute path
            resolved_path = (data_dir / sanitized_filename).resolve()
            
            # Ensure the resolved path is within the data directory
            # Use resolve() on data_dir to get its absolute path for comparison
            data_dir_abs = data_dir.resolve()
            
            # Additional safety check using os.path.commonpath to ensure containment
            try:
                common_path = os.path.commonpath([str(resolved_path), str(data_dir_abs)])
                if os.path.normpath(common_path) != os.path.normpath(str(data_dir_abs)):
                    raise ValueError(f"Path traversal detected: {filename} would resolve outside of {data_dir_abs}")
            except ValueError:
                # If commonpath fails, fall back to pathlib containment check
                try:
                    resolved_path.relative_to(data_dir_abs)
                except ValueError:
                    raise ValueError(f"Path traversal detected: {filename} would resolve to {resolved_path} outside of {data_dir_abs}")
            
            return resolved_path
            
        except RuntimeError as e:
            # Handle any path resolution errors
            raise ValueError(f"Invalid path: {filename}") from e
    
    def save_json(self, filename: str, data: Dict[str, Any], date: Optional[datetime] = None, overwrite: bool = False):
        """Save data as JSON file."""
        file_path = self._resolve_secure_path(filename, date)
        return self.atomic_write_json(file_path, data, overwrite=overwrite)
    
    def load_json(self, filename: str, date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Load data from JSON file."""
        # Use _resolve_secure_path to get the safe destination path
        file_path = self._resolve_secure_path(filename, date)
        
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
    
    def persist_file(self, temp_path: Path, filename: str, date: Optional[datetime] = None, overwrite: bool = False) -> Path:
        """Move a temporary file to persistent storage and return the new path."""
        if not temp_path.exists():
            raise FileNotFoundError(f"Temporary file not found: {temp_path}")
        
        # Use _resolve_secure_path to get the safe destination path
        persistent_path = self._resolve_secure_path(filename, date)
        
        # Ensure the resolved path's parent directories exist
        persistent_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if destination exists and overwrite is not allowed
        if persistent_path.exists() and not overwrite:
            raise FileExistsError(f"Destination file already exists: {persistent_path}. Set overwrite=True to allow replacement.")
        
        # Perform atomic replace using os.replace
        try:
            os.replace(temp_path, persistent_path)
        except OSError as e:
            if getattr(e, "errno", None) == errno.EXDEV:
                # Files are on different filesystems, use copy + replace strategy
                temp_in_same_dir = None
                try:
                    # Create temporary file in same directory as destination
                    with tempfile.NamedTemporaryFile(delete=False, dir=persistent_path.parent) as temp_file:
                        temp_in_same_dir = Path(temp_file.name)
                    
                    # Copy contents to temporary file in same directory
                    shutil.copy2(temp_path, temp_in_same_dir)
                    
                    # Ensure data is flushed to disk before replace
                    with open(temp_in_same_dir, "rb", buffering=0) as _fh:
                        os.fsync(_fh.fileno())
                    
                    # Atomic replace within same filesystem
                    os.replace(temp_in_same_dir, persistent_path)
                    
                    # Clean up original temp file
                    temp_path.unlink()
                    
                except Exception as copy_error:
                    # Clean up temporary files on error
                    if temp_in_same_dir and temp_in_same_dir.exists():
                        try:
                            temp_in_same_dir.unlink()
                        except OSError as cleanup_err:
                            logger.warning("Failed to remove temp file %s: %s", temp_in_same_dir, cleanup_err)
                    raise RuntimeError(f"Failed to copy file across filesystems: {copy_error}") from copy_error
            else:
                # Re-raise non-EXDEV exceptions as RuntimeError
                raise RuntimeError(f"Failed to persist file from {temp_path} to {persistent_path}: {e}") from e
        except PermissionError as e:
            raise RuntimeError(f"Permission denied persisting file from {temp_path} to {persistent_path}: {e}") from e
        
        return persistent_path
    
    def delete_persisted_file(self, file_path: Path) -> bool:
        """Delete a persisted file from storage.
        
        Args:
            file_path: Path to the persisted file to delete
            
        Returns:
            True if file was deleted successfully, False if file didn't exist
        """
        try:
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            logger.warning("Failed to delete persisted file %s: %s", file_path, e)
            return False

    def clear_cache(self):
        """Clear all cached data and seen IDs."""
        # Clear seen IDs
        self.seen_ids = SeenIds()
        self._save_seen_ids()
        
        # Clear cache directory
        if self.cache_dir.exists():
            for file in self.cache_dir.iterdir():
                if file.is_file():
                    file.unlink()
        
        logger.info("Cache cleared successfully")
    
    def atomic_write_json(self, file_path: Path, data: Dict[str, Any], overwrite: bool = False) -> Path:
        """Atomically write JSON data to a file with cross-filesystem support.
        
        Args:
            file_path: Path to write the JSON file to
            data: Data to serialize as JSON
            overwrite: Whether to overwrite existing files
            
        Returns:
            Path to the written file
            
        Raises:
            FileExistsError: If file exists and overwrite=False
            RuntimeError: If writing fails
        """
        if file_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {file_path}. Set overwrite=True to allow replacement.")
        
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                # Use a more robust serialization approach
                def safe_serializer(obj):
                    if hasattr(obj, 'model_dump'):
                        return obj.model_dump(mode='json')
                    elif hasattr(obj, 'dict'):
                        return obj.dict()
                    elif hasattr(obj, '__dict__'):
                        return obj.__dict__
                    else:
                        return str(obj)
                
                json.dump(data, f, indent=2, default=safe_serializer)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise
        
        return file_path


def generate_filename(prefix: str, identifier: str, extension: str = "json") -> str:
    """Generate a filename with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{identifier}_{timestamp}.{extension}"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe filesystem use.
    
    Replaces invalid characters with underscores, collapses whitespace into underscores,
    and ensures the filename is safe for cross-platform filesystem use.
    """
    # Trim whitespace
    filename = filename.strip()
    
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Collapse repeated underscores
    while '__' in filename:
        filename = filename.replace('__', '_')
    
    # Remove leading/trailing dots and underscores
    filename = filename.strip('._')
    
    # Replace remaining whitespace with underscores
    filename = "_".join(filename.split())
    # Collapse repeated underscores (post-whitespace normalization)
    while '__' in filename:
        filename = filename.replace('__', '_')
    
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    
    if not filename:
        filename = "untitled"
    
    return filename


def get_file_hash(file_path: Path) -> str:
    """Get SHA256 hash of a file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def validate_story_id(story_id: str) -> bool:
    """
    Validate story_id to prevent path traversal and CLI misuse.
    
    Args:
        story_id: The story ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not story_id or not isinstance(story_id, str):
        return False
    
    # Reject IDs that start with hyphens to prevent CLI option injection
    if story_id.startswith('-'):
        return False
    
    # Enforce ASCII-only characters
    if not story_id.isascii():
        return False
    
    # Restrict to safe charset: alphanumeric, hyphens, underscores only
    if not story_id.replace('-', '').replace('_', '').isalnum():
        return False
    
    # Limit length to prevent abuse
    if len(story_id) > 50:
        return False
    
    # Prevent common path traversal patterns
    dangerous_patterns = ['..', '/', '\\', '~']
    if any(pattern in story_id for pattern in dangerous_patterns):
        return False
    
    return True
