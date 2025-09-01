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
    # Set HOME environment variable so os.path.expanduser resolves to tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    
    c = OBSController()
    assert c.start_recording().ok
    assert c.stop_recording().ok

def test_obs_real_recording(monkeypatch, tmp_path):
    """Test actual recording functionality with file creation."""
    # Skip test if TEST_OBS_PASSWORD is not provided
    test_password = os.getenv("TEST_OBS_PASSWORD")
    if not test_password:
        pytest.skip("TEST_OBS_PASSWORD environment variable not set")
    
    # Capture real user home and compute OBS recordings directory before monkeypatching
    real_home = Path.home()
    obs_recordings_dir = real_home / "Movies" / "OBS-Recordings"
    if not obs_recordings_dir.exists():
        pytest.skip("OBS recordings directory doesn't exist")
    
    # Get initial file count in OBS recordings directory
    initial_files = set()
    if obs_recordings_dir.exists():
        initial_files = set(f.name for f in obs_recordings_dir.iterdir())
    
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
    # Set HOME environment variable so os.path.expanduser resolves to tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    
    # Skip test if OBS is not available
    try:
        c = OBSController()
        # Test connection first
        conn_result = c._connect()
        if not conn_result.ok:
            pytest.skip(f"OBS not available: {conn_result.error}")
    except Exception as e:
        pytest.skip(f"OBS not available: {e}")
    
    c = OBSController()
    
    # Start recording
    start_result = c.start_recording()
    assert start_result.ok, f"Start recording failed: {start_result.error}"
    
    # Poll for recording to start (max 10 seconds)
    max_wait = 10
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            # Reconnect if websocket was closed by start_recording()
            if c.ws is None:
                c._connect()
                # Wait for connection to be established
                reconnect_timeout = 2
                reconnect_start = time.time()
                while c.ws is None and time.time() - reconnect_start < reconnect_timeout:
                    time.sleep(0.1)
                if c.ws is None:
                    raise Exception("Failed to reconnect websocket")
            
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
        if obs_recordings_dir.exists():
            final_files = set(f.name for f in obs_recordings_dir.iterdir())
            new_files = final_files - initial_files
            if new_files:
                break
        time.sleep(0.5)
    
    assert len(new_files) > 0, f"No new recording files created. Expected files in {obs_recordings_dir}, but none were found."
    
    # Check that at least one new file is a video file
    video_files = [f for f in new_files if f.endswith(('.mp4', '.mov', '.mkv'))]
    assert len(video_files) > 0, f"No video files created. New files: {new_files}"
    
    print(f"✅ Created {len(video_files)} new video file(s): {video_files}")
