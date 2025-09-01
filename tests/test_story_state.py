import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from services.story_state import StoryState

def test_state_roundtrip(tmp_path: Path):
    # seed digest
    date_str = "2025-08-27"
    date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ddir = tmp_path / "data" / date_str
    ddir.mkdir(parents=True)
    p = ddir / "PRE-CLEANED-digest.json"
    p.write_text(json.dumps({
        "version":"2","date":date_str,
        "twitch_clips":[], "github_events":[],
        "metadata":{}, "frontmatter":{}, 
        "story_packets":[{"id":"story_1","explainer":{"status":"missing"}}]
    }, indent=2))
    s = StoryState(data_dir=str(tmp_path/"data"))
    s.begin_recording(date, "story_1")
    s.end_recording(date, "story_1", raw_path="raw/foo.mkv")
    obj = json.loads(p.read_text())
    pkt = obj["story_packets"][0]
    assert pkt["explainer"]["status"] == "recorded"
    assert pkt["video"]["status"] == "pending"
    assert pkt["video"]["raw_recording_path"] == "raw/foo.mkv"

def test_naive_datetime_rejected(tmp_path: Path):
    """Test that naive datetimes are rejected by default."""
    # seed digest
    date_str = "2025-08-27"
    naive_date = datetime.strptime(date_str, "%Y-%m-%d")  # No timezone info
    ddir = tmp_path / "data" / date_str
    ddir.mkdir(parents=True)
    p = ddir / "PRE-CLEANED-digest.json"
    p.write_text(json.dumps({
        "version":"2","date":date_str,
        "twitch_clips":[], "github_events":[],
        "metadata":{}, "frontmatter":{}, 
        "story_packets":[{"id":"story_1","explainer":{"status":"missing"}}]
    }, indent=2))
    s = StoryState(data_dir=str(tmp_path/"data"))
    
    # Should raise ValueError for naive datetime
    with pytest.raises(ValueError, match="Timezone-aware datetime required"):
        s.begin_recording(naive_date, "story_1")
    
    with pytest.raises(ValueError, match="Timezone-aware datetime required"):
        s.end_recording(naive_date, "story_1")

def test_naive_datetime_with_assume_utc(tmp_path: Path):
    """Test that naive datetimes are accepted when assume_utc=True."""
    # seed digest
    date_str = "2025-08-27"
    naive_date = datetime.strptime(date_str, "%Y-%m-%d")  # No timezone info
    ddir = tmp_path / "data" / date_str
    ddir.mkdir(parents=True)
    p = ddir / "PRE-CLEANED-digest.json"
    p.write_text(json.dumps({
        "version":"2","date":date_str,
        "twitch_clips":[], "github_events":[],
        "metadata":{}, "frontmatter":{}, 
        "story_packets":[{"id":"story_1","explainer":{"status":"missing"}}]
    }, indent=2))
    s = StoryState(data_dir=str(tmp_path/"data"))
    
    # Should work with assume_utc=True
    s.begin_recording(naive_date, "story_1", assume_utc=True)
    s.end_recording(naive_date, "story_1", assume_utc=True)
    
    # Verify the state was updated
    obj = json.loads(p.read_text())
    pkt = obj["story_packets"][0]
    assert pkt["explainer"]["status"] == "recorded"
    assert pkt["video"]["status"] == "pending"


def test_bounded_recording_completion(tmp_path: Path):
    """Test that bounded recording properly updates video status and timing."""
    # seed digest
    date_str = "2025-08-27"
    date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ddir = tmp_path / "data" / date_str
    ddir.mkdir(parents=True)
    p = ddir / "PRE-CLEANED-digest.json"
    p.write_text(json.dumps({
        "version":"2","date":date_str,
        "twitch_clips":[], "github_events":[],
        "metadata":{}, "frontmatter":{}, 
        "story_packets":[{"id":"story_1","explainer":{"status":"missing"}}]
    }, indent=2))
    
    s = StoryState(data_dir=str(tmp_path/"data"))
    
    # First begin recording to set started_at
    s.begin_recording(date, "story_1")
    
    # Complete bounded recording
    duration = 60
    s.complete_bounded_recording(date, "story_1", duration)
    
    # Verify the state was updated correctly
    obj = json.loads(p.read_text())
    pkt = obj["story_packets"][0]
    
    # Check explainer status
    assert pkt["explainer"]["status"] == "recorded"
    assert "started_at" in pkt["explainer"]
    assert "completed_at" in pkt["explainer"]
    
    # Check video status and timing
    assert pkt["video"]["status"] == "recorded"
    assert pkt["video"]["duration_s"] == duration
    assert pkt["video"]["started_at"] == pkt["explainer"]["started_at"]
    assert "ended_at" in pkt["video"]
    
    # Verify timestamps are ISO format
    import re
    iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{6}\+\d{2}:\d{2}$'
    assert re.match(iso_pattern, pkt["video"]["started_at"])
    assert re.match(iso_pattern, pkt["video"]["ended_at"])
