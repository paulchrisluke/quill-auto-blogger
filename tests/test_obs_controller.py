from services.obs_controller import OBSController
from services.auth import AuthService
import os
import time
import tempfile
import shutil
import pytest
from pathlib import Path

def test_obs_dry_run(monkeypatch, tmp_path):
    # Set up temporary cache directory
    cache_dir = tmp_path / ".cache" / "quill-auto-blogger"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock Path.home() to return our temporary directory
    def mock_home():
        return tmp_path
    
    # Set environment variables using monkeypatch
    monkeypatch.setenv("OBS_DRY_RUN", "true")
    monkeypatch.setenv("OBS_HOST", "127.0.0.1")
    monkeypatch.setenv("OBS_PORT", "4455")
    monkeypatch.setenv("OBS_PASSWORD", "test_password")
    monkeypatch.setenv("OBS_SCENE", "test_scene")
    
    # Mock Path.home() to return our temporary directory
    monkeypatch.setattr(Path, "home", mock_home)
    
    c = OBSController()
    assert c.start_recording().ok
    assert c.stop_recording().ok

def test_obs_real_recording(monkeypatch, tmp_path):
    """Test actual recording functionality with file creation."""
    # Skip test if TEST_OBS_PASSWORD is not provided
    test_password = os.getenv("TEST_OBS_PASSWORD")
    if not test_password:
        pytest.skip("TEST_OBS_PASSWORD environment variable not set")
    
    # Set up temporary cache directory
    cache_dir = tmp_path / ".cache" / "quill-auto-blogger"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock Path.home() to return our temporary directory
    def mock_home():
        return tmp_path
    
    # Set environment variables for real recording using monkeypatch
    monkeypatch.setenv("OBS_DRY_RUN", "false")
    monkeypatch.setenv("OBS_HOST", "127.0.0.1")
    monkeypatch.setenv("OBS_PORT", "4455")
    monkeypatch.setenv("OBS_PASSWORD", test_password)
    monkeypatch.setenv("OBS_SCENE", "Display Reg")
    
    # Mock Path.home() to return our temporary directory
    monkeypatch.setattr(Path, "home", mock_home)
    
    # Skip test if OBS is not available
    try:
        c = OBSController()
        # Test connection first
        conn_result = c._connect()
        if not conn_result.ok:
            pytest.skip(f"OBS not available: {conn_result.error}")
    except Exception as e:
        pytest.skip(f"OBS not available: {e}")
    
    # Get initial file count in OBS recordings directory
    obs_recordings_dir = os.path.expanduser("~/Movies/OBS-Recordings")
    if not os.path.exists(obs_recordings_dir):
        pytest.skip("OBS recordings directory doesn't exist")
    
    initial_files = set()
    if os.path.exists(obs_recordings_dir):
        initial_files = set(os.listdir(obs_recordings_dir))
    
    c = OBSController()
    
    # Start recording
    start_result = c.start_recording()
    assert start_result.ok, f"Start recording failed: {start_result.error}"
    
    # Poll for recording to start (max 10 seconds)
    max_wait = 10
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            rec_status = c.ws.get_record_status()
            if hasattr(rec_status, 'outputActive') and rec_status.outputActive:
                break
        except Exception:
            pass
        time.sleep(0.5)
    
    # Stop recording
    stop_result = c.stop_recording()
    assert stop_result.ok, f"Stop recording failed: {stop_result.error}"
    
    # Poll for new files with timeout (max 15 seconds)
    max_wait = 15
    start_time = time.time()
    new_files = set()
    
    while time.time() - start_time < max_wait:
        if os.path.exists(obs_recordings_dir):
            final_files = set(os.listdir(obs_recordings_dir))
            new_files = final_files - initial_files
            if new_files:
                break
        time.sleep(0.5)
    
    assert len(new_files) > 0, f"No new recording files created. Expected files in {obs_recordings_dir}, but none were found."
    
    # Check that at least one new file is a video file
    video_files = [f for f in new_files if f.endswith(('.mp4', '.mov', '.mkv'))]
    assert len(video_files) > 0, f"No video files created. New files: {new_files}"
    
    print(f"✅ Created {len(video_files)} new video file(s): {video_files}")
