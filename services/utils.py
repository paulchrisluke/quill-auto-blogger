"""
Utility functions for caching, deduplication, and file management.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

from models import SeenIds, CacheEntry


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
                with open(self.seen_ids_file, 'r') as f:
                    data = json.load(f)
                    return SeenIds(**data)
            except Exception:
                pass
        
        return SeenIds()
    
    def _save_seen_ids(self):
        """Save seen IDs to file."""
        self.seen_ids.last_updated = datetime.now()
        with open(self.seen_ids_file, 'w') as f:
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
    
    def save_json(self, filename: str, data: Dict[str, Any], date: Optional[datetime] = None):
        """Save data as JSON file."""
        data_dir = self.get_data_dir(date)
        file_path = data_dir / filename
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        return file_path
    
    def load_json(self, filename: str, date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Load data from JSON file."""
        data_dir = self.get_data_dir(date)
        file_path = data_dir / filename
        
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        
        return None
    
    def persist_file(self, temp_path: Path, filename: str, date: Optional[datetime] = None) -> Path:
        """Move a temporary file to persistent storage and return the new path."""
        if not temp_path.exists():
            raise FileNotFoundError(f"Temporary file not found: {temp_path}")
        
        data_dir = self.get_data_dir(date)
        persistent_path = data_dir / filename
        
        # Ensure the target directory exists
        persistent_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        temp_path.rename(persistent_path)
        
        return persistent_path
    
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
        
        print("Cache cleared successfully")


def generate_filename(prefix: str, identifier: str, extension: str = "json") -> str:
    """Generate a filename with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{identifier}_{timestamp}.{extension}"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe filesystem use."""
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename


def get_file_hash(file_path: Path) -> str:
    """Get SHA256 hash of a file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()
