#!/usr/bin/env python3
"""
M2 Acceptance Test Script
Tests all M2 Capture & Control features
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from services.obs_controller import OBSController
from services.story_state import StoryState
from services.outline import generate_outline
from services.reminder import scan_and_notify

def test_obs_controller():
    """Test OBS Controller functionality"""
    print("🧪 Testing OBS Controller...")
    
    # Set dry run mode
    os.environ["OBS_DRY_RUN"] = "true"
    
    obs = OBSController()
    
    # Test start recording
    result = obs.start_recording()
    if not result.ok:
        print(f"❌ OBS start recording failed: {result.error}")
        return False
    print(f"✅ OBS start recording: {result.info}")
    
    # Test stop recording
    result = obs.stop_recording()
    if not result.ok:
        print(f"❌ OBS stop recording failed: {result.error}")
        return False
    print(f"✅ OBS stop recording: {result.info}")
    
    return True

def test_story_state():
    """Test Story State persistence"""
    print("\n🧪 Testing Story State...")
    
    # Create a test digest
    test_date = "2025-08-31"
    test_dir = Path("test_data") / test_date
    test_dir.mkdir(parents=True, exist_ok=True)
    
    test_digest = {
        "version": "2",
        "date": test_date,
        "story_packets": [
            {
                "id": "test_story_1",
                "title_human": "Test Story",
                "explainer": {"status": "missing"}
            }
        ]
    }
    
    digest_file = test_dir / "PRE-CLEANED-test_digest.json"
    with open(digest_file, 'w') as f:
        json.dump(test_digest, f, indent=2)
    
    # Test story state
    state = StoryState(data_dir="test_data")
    
    # Test begin recording
    packet = state.begin_recording(test_date, "test_story_1")
    if packet["explainer"]["status"] != "recording":
        print("❌ Begin recording failed")
        return False
    print("✅ Begin recording successful")
    
    # Test end recording
    packet = state.end_recording(test_date, "test_story_1", "test/path.mkv")
    if packet["explainer"]["status"] != "recorded":
        print("❌ End recording failed")
        return False
    if packet["video"]["status"] != "pending":
        print("❌ Video status not set correctly")
        return False
    print("✅ End recording successful")
    
    # Cleanup
    import shutil
    shutil.rmtree("test_data")
    
    return True

def test_outline_generation():
    """Test outline generation"""
    print("\n🧪 Testing Outline Generation...")
    
    test_packet = {
        "title_human": "Test Feature",
        "why": "This is a test feature for validation",
        "highlights": ["Feature 1", "Feature 2", "Feature 3", "Feature 4"]
    }
    
    outline = generate_outline(test_packet)
    
    if "# Hook: Test Feature" not in outline:
        print("❌ Outline generation failed")
        return False
    
    if "Feature 1" not in outline or "Feature 2" not in outline:
        print("❌ Highlights not included in outline")
        return False
    
    print("✅ Outline generation successful")
    print(f"Generated outline:\n{outline}")
    
    return True

def test_cli_functionality():
    """Test CLI functionality"""
    print("\n🧪 Testing CLI Functionality...")
    
    # Test CLI help
    import subprocess
    try:
        result = subprocess.run(
            ["python", "-m", "cli.devlog", "--help"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("❌ CLI help failed")
            return False
        print("✅ CLI help successful")
    except Exception as e:
        print(f"❌ CLI test failed: {e}")
        return False
    
    return True

def test_real_digest_integration():
    """Test with real digest files"""
    print("\n🧪 Testing Real Digest Integration...")
    
    # Check if we have real digest files
    digest_path = Path("blogs/2025-08-27/PRE-CLEANED-2025-08-27_digest.json")
    if not digest_path.exists():
        print("⚠️  No real digest files found, skipping real integration test")
        return True
    
    try:
        state = StoryState()
        digest = state._load_digest("2025-08-27")
        
        if not digest.get("story_packets"):
            print("⚠️  No story packets in digest, skipping real integration test")
            return True
        
        # Test with first story
        story = digest["story_packets"][0]
        outline = generate_outline(story)
        
        if not outline:
            print("❌ Real outline generation failed")
            return False
        
        print("✅ Real digest integration successful")
        print(f"Story: {story.get('title_human', story.get('title_raw'))}")
        print(f"Outline preview: {outline[:100]}...")
        
    except Exception as e:
        print(f"❌ Real digest integration failed: {e}")
        return False
    
    return True

def main():
    """Run all acceptance tests"""
    print("🚀 M2 Capture & Control Acceptance Tests")
    print("=" * 50)
    
    tests = [
        ("OBS Controller", test_obs_controller),
        ("Story State", test_story_state),
        ("Outline Generation", test_outline_generation),
        ("CLI Functionality", test_cli_functionality),
        ("Real Digest Integration", test_real_digest_integration),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All M2 features working correctly!")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
