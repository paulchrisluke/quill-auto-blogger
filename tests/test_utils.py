"""
Tests for utility functions and cache management.
"""

import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from services.utils import CacheManager, generate_filename, sanitize_filename, get_file_hash
from models import SeenIds


class TestCacheManager:
    """Test cases for CacheManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_manager = CacheManager()
        self.cache_manager.data_dir = self.temp_dir / "data"
        self.cache_manager.cache_dir = self.temp_dir / "cache"
        self.cache_manager.seen_ids_file = self.temp_dir / "seen_ids.json"
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_load_seen_ids_new(self):
        """Test loading seen IDs when file doesn't exist."""
        seen_ids = self.cache_manager._load_seen_ids()
        assert isinstance(seen_ids, SeenIds)
        assert seen_ids.twitch_clips == []
        assert seen_ids.github_events == []
    
    def test_load_seen_ids_existing(self):
        """Test loading seen IDs from existing file."""
        # Create test data
        test_data = {
            "twitch_clips": ["clip1", "clip2"],
            "github_events": ["event1"],
            "last_updated": datetime.now().isoformat()
        }
        
        with open(self.cache_manager.seen_ids_file, 'w') as f:
            json.dump(test_data, f)
        
        seen_ids = self.cache_manager._load_seen_ids()
        assert seen_ids.twitch_clips == ["clip1", "clip2"]
        assert seen_ids.github_events == ["event1"]
    
    def test_save_seen_ids(self):
        """Test saving seen IDs to file."""
        seen_ids = SeenIds(
            twitch_clips=["clip1"],
            github_events=["event1"]
        )
        self.cache_manager.seen_ids = seen_ids
        
        self.cache_manager._save_seen_ids()
        
        assert self.cache_manager.seen_ids_file.exists()
        
        with open(self.cache_manager.seen_ids_file, 'r') as f:
            data = json.load(f)
        
        assert data["twitch_clips"] == ["clip1"]
        assert data["github_events"] == ["event1"]
    
    def test_is_seen_twitch_clip(self):
        """Test checking if Twitch clip has been seen."""
        self.cache_manager.seen_ids.twitch_clips = ["clip1", "clip2"]
        
        assert self.cache_manager.is_seen("clip1", "twitch_clip") is True
        assert self.cache_manager.is_seen("clip3", "twitch_clip") is False
    
    def test_is_seen_github_event(self):
        """Test checking if GitHub event has been seen."""
        self.cache_manager.seen_ids.github_events = ["event1", "event2"]
        
        assert self.cache_manager.is_seen("event1", "github_event") is True
        assert self.cache_manager.is_seen("event3", "github_event") is False
    
    def test_mark_seen_twitch_clip(self):
        """Test marking Twitch clip as seen."""
        self.cache_manager.mark_seen("clip1", "twitch_clip")
        
        assert "clip1" in self.cache_manager.seen_ids.twitch_clips
        
        # Should not add duplicates
        self.cache_manager.mark_seen("clip1", "twitch_clip")
        assert self.cache_manager.seen_ids.twitch_clips.count("clip1") == 1
    
    def test_mark_seen_github_event(self):
        """Test marking GitHub event as seen."""
        self.cache_manager.mark_seen("event1", "github_event")
        
        assert "event1" in self.cache_manager.seen_ids.github_events
        
        # Should not add duplicates
        self.cache_manager.mark_seen("event1", "github_event")
        assert self.cache_manager.seen_ids.github_events.count("event1") == 1
    
    def test_get_data_dir_default(self):
        """Test getting data directory for current date."""
        data_dir = self.cache_manager.get_data_dir()
        assert data_dir.name == datetime.now().strftime("%Y-%m-%d")
    
    def test_get_data_dir_specific_date(self):
        """Test getting data directory for specific date."""
        test_date = datetime(2023, 1, 15)
        data_dir = self.cache_manager.get_data_dir(test_date)
        assert data_dir.name == "2023-01-15"
    
    def test_save_json(self):
        """Test saving JSON data."""
        test_data = {"key": "value", "number": 123}
        filename = "test.json"
        
        file_path = self.cache_manager.save_json(filename, test_data)
        
        assert file_path.exists()
        
        with open(file_path, 'r') as f:
            loaded_data = json.load(f)
        
        assert loaded_data == test_data
    
    def test_load_json_existing(self):
        """Test loading JSON data from existing file."""
        test_data = {"key": "value", "number": 123}
        filename = "test.json"
        
        # Save data first
        self.cache_manager.save_json(filename, test_data)
        
        # Load data
        loaded_data = self.cache_manager.load_json(filename)
        
        assert loaded_data == test_data
    
    def test_load_json_nonexistent(self):
        """Test loading JSON data from non-existent file."""
        loaded_data = self.cache_manager.load_json("nonexistent.json")
        assert loaded_data is None
    
    def test_clear_cache(self):
        """Test clearing cache."""
        # Create some test files
        self.cache_manager.seen_ids.twitch_clips = ["clip1"]
        self.cache_manager.seen_ids.github_events = ["event1"]
        self.cache_manager._save_seen_ids()
        
        # Create a test file in cache directory
        test_file = self.cache_manager.cache_dir / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("test content")
        
        # Clear cache
        self.cache_manager.clear_cache()
        
        # Check that seen IDs are reset
        assert self.cache_manager.seen_ids.twitch_clips == []
        assert self.cache_manager.seen_ids.github_events == []
        
        # Check that cache file is removed
        assert not test_file.exists()


class TestUtilityFunctions:
    """Test cases for utility functions."""
    
    def test_generate_filename(self):
        """Test filename generation."""
        filename = generate_filename("test", "123", "json")
        
        # Should contain prefix, identifier, timestamp, and extension
        assert filename.startswith("test_123_")
        assert filename.endswith(".json")
        
        # Should have timestamp in format YYYYMMDD_HHMMSS
        parts = filename.split("_")
        assert len(parts) >= 3
        assert len(parts[2].split(".")[0]) == 6  # HHMMSS
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Test invalid characters
        assert sanitize_filename("file<name>") == "file_name_"
        assert sanitize_filename("file:name") == "file_name"
        assert sanitize_filename("file/name") == "file_name"
        assert sanitize_filename("file\\name") == "file_name"
        assert sanitize_filename("file|name") == "file_name"
        assert sanitize_filename("file?name") == "file_name"
        assert sanitize_filename("file*name") == "file_name"
        
        # Test length limit
        long_name = "a" * 300
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 200
        
        # Test normal filename
        assert sanitize_filename("normal_file.txt") == "normal_file.txt"
    
    def test_get_file_hash(self):
        """Test file hash generation."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            file_hash = get_file_hash(temp_path)
            
            # Should be a valid SHA256 hash (64 hex characters)
            assert len(file_hash) == 64
            assert all(c in '0123456789abcdef' for c in file_hash)
            
        finally:
            temp_path.unlink()
