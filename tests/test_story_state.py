import json
from datetime import datetime, timezone
from pathlib import Path
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
