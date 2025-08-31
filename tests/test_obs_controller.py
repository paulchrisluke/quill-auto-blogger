from services.obs_controller import OBSController
from services.auth import AuthService
import os
import time
import tempfile
import shutil

def test_obs_dry_run():
    # Clear any existing OBS credentials cache
    auth_service = AuthService()
    if auth_service.obs_credentials_file.exists():
        auth_service.obs_credentials_file.unlink()
    
    # Set environment variables
    os.environ["OBS_DRY_RUN"] = "true"
    os.environ["OBS_HOST"] = "127.0.0.1"
    os.environ["OBS_PORT"] = "4455"
    os.environ["OBS_PASSWORD"] = "test_password"
    os.environ["OBS_SCENE"] = "test_scene"
    
    c = OBSController()
    assert c.start_recording().ok
    assert c.stop_recording().ok

def test_obs_real_recording():
    """Test actual recording functionality with file creation."""
    # Clear any existing OBS credentials cache
    auth_service = AuthService()
    if auth_service.obs_credentials_file.exists():
        auth_service.obs_credentials_file.unlink()
    
    # Set environment variables for real recording
    os.environ["OBS_DRY_RUN"] = "false"
    os.environ["OBS_HOST"] = "127.0.0.1"
    os.environ["OBS_PORT"] = "4455"
    os.environ["OBS_PASSWORD"] = "jaScnQwqHA5Vwdfy"  # Use actual password
    os.environ["OBS_SCENE"] = "Display Reg"
    
    # Get initial file count in OBS recordings directory
    obs_recordings_dir = os.path.expanduser("~/Movies/OBS-Recordings")
    if not os.path.exists(obs_recordings_dir):
        # Skip test if OBS recordings directory doesn't exist
        return
    
    initial_files = set()
    if os.path.exists(obs_recordings_dir):
        initial_files = set(os.listdir(obs_recordings_dir))
    
    c = OBSController()
    
    # Start recording
    start_result = c.start_recording()
    assert start_result.ok, f"Start recording failed: {start_result.error}"
    
    # Wait a moment for recording to start
    time.sleep(2)
    
    # Stop recording
    stop_result = c.stop_recording()
    assert stop_result.ok, f"Stop recording failed: {stop_result.error}"
    
    # Wait for file to be written
    time.sleep(3)
    
    # Check for new files
    final_files = set()
    if os.path.exists(obs_recordings_dir):
        final_files = set(os.listdir(obs_recordings_dir))
    
    new_files = final_files - initial_files
    assert len(new_files) > 0, f"No new recording files created. Expected files in {obs_recordings_dir}, but none were found."
    
    # Check that at least one new file is a video file
    video_files = [f for f in new_files if f.endswith(('.mp4', '.mov', '.mkv'))]
    assert len(video_files) > 0, f"No video files created. New files: {new_files}"
    
    print(f"✅ Created {len(video_files)} new video file(s): {video_files}")
