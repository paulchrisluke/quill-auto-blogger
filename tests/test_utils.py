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
        
        # Ensure data directory exists
        self.cache_manager.data_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    def test_save_json_overwrite_false(self):
        """Test that save_json raises FileExistsError when file exists and overwrite=False."""
        test_data = {"key": "value", "number": 123}
        filename = "test.json"
        
        # Save file first time
        self.cache_manager.save_json(filename, test_data)
        
        # Try to save again without overwrite flag
        with pytest.raises(FileExistsError):
            self.cache_manager.save_json(filename, test_data)
    
    def test_save_json_overwrite_true(self):
        """Test that save_json allows overwriting when overwrite=True."""
        test_data1 = {"key": "value1", "number": 123}
        test_data2 = {"key": "value2", "number": 456}
        filename = "test.json"
        
        # Save file first time
        self.cache_manager.save_json(filename, test_data1)
        
        # Save again with overwrite flag
        file_path = self.cache_manager.save_json(filename, test_data2, overwrite=True)
        
        # Verify the file was overwritten
        with open(file_path, 'r') as f:
            loaded_data = json.load(f)
        
        assert loaded_data == test_data2
    
    def test_persist_file(self):
        """Test persisting a temporary file."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            filename = "persisted_test.txt"
            persistent_path = self.cache_manager.persist_file(temp_path, filename)
            
            assert persistent_path.exists()
            assert persistent_path.read_text() == "test content"
            assert not temp_path.exists()  # Original temp file should be moved
        finally:
            # Clean up temp file if it still exists
            if temp_path.exists():
                temp_path.unlink()
    
    def test_persist_file_overwrite_false(self):
        """Test that persist_file raises FileExistsError when destination exists and overwrite=False."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            filename = "persisted_test.txt"
            
            # Persist file first time
            self.cache_manager.persist_file(temp_path, filename)
            
            # Create another temp file
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
                f2.write("different content")
                temp_path2 = Path(f2.name)
            
            try:
                # Try to persist to same destination without overwrite flag
                with pytest.raises(FileExistsError):
                    self.cache_manager.persist_file(temp_path2, filename)
            finally:
                if temp_path2.exists():
                    temp_path2.unlink()
        finally:
            # Clean up temp file if it still exists
            if temp_path.exists():
                temp_path.unlink()
    
    def test_persist_file_overwrite_true(self):
        """Test that persist_file allows overwriting when overwrite=True."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            filename = "persisted_test.txt"
            
            # Persist file first time
            self.cache_manager.persist_file(temp_path, filename)
            
            # Create another temp file
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
                f2.write("different content")
                temp_path2 = Path(f2.name)
            
            try:
                # Persist to same destination with overwrite flag
                persistent_path = self.cache_manager.persist_file(temp_path2, filename, overwrite=True)
                
                assert persistent_path.exists()
                assert persistent_path.read_text() == "different content"
                assert not temp_path2.exists()  # Original temp file should be moved
            finally:
                if temp_path2.exists():
                    temp_path2.unlink()
        finally:
            # Clean up temp file if it still exists
            if temp_path.exists():
                temp_path.unlink()
    
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
    
    def test_persist_file_path_traversal_rejected(self):
        """Test that persist_file rejects path traversal attempts."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            # Test path traversal in filename
            with pytest.raises(ValueError, match="Path traversal detected"):
                self.cache_manager.persist_file(temp_path, "../evil.json", overwrite=True)
            
            # Verify no file was written outside the intended directory
            evil_path = self.cache_manager.data_dir.parent / "evil.json"
            assert not evil_path.exists()
            
        finally:
            # Clean up temp file if it still exists
            if temp_path.exists():
                temp_path.unlink()
    
    def test_save_json_path_traversal_rejected(self):
        """Test that save_json rejects path traversal attempts."""
        test_data = {"x": 1}
        
        # Test path traversal in filename
        with pytest.raises(ValueError, match="Path traversal detected"):
            self.cache_manager.save_json("../evil.json", test_data, overwrite=True)
        
        # Verify no file was written outside the intended directory
        evil_path = self.cache_manager.data_dir.parent / "evil.json"
        assert not evil_path.exists()

    def test_load_json_path_traversal_rejected(self):
        """Test that load_json rejects path traversal attempts."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            self.cache_manager.load_json("../evil.json")


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
        assert len(parts) >= 4  # prefix, identifier, date, time
        timestamp_part = f"{parts[2]}_{parts[3]}".split(".")[0]
        assert len(timestamp_part) == 15  # YYYYMMDD_HHMMSS (8 + 1 + 6)
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Test invalid characters
        assert sanitize_filename("file<name>") == "file_name"
        assert sanitize_filename("file:name") == "file_name"
        assert sanitize_filename("file/name") == "file_name"
        assert sanitize_filename("file\\name") == "file_name"
        assert sanitize_filename("file|name") == "file_name"
        assert sanitize_filename("file?name") == "file_name"
        assert sanitize_filename("file*name") == "file_name"
        
        # Test whitespace replacement with underscores
        assert sanitize_filename("  file name  ") == "file_name"
        
        # Test repeated underscores
        assert sanitize_filename("file__name") == "file_name"
        assert sanitize_filename("file___name") == "file_name"
        
        # Test leading/trailing dots and underscores
        assert sanitize_filename("._file_name_.") == "file_name"
        
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
