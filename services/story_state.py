from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class StoryState:
    """
    Mutates v2 digest: story_packets[*].explainer.status & video placeholders.
    """

    def __init__(self, data_dir: str = "blogs") -> None:
        self.data_dir = Path(data_dir)

    def _load_digest(self, date: str) -> Dict[str, Any]:
        # Locate PRE-CLEANED digest for date
        dir_path = self.data_dir / date
        candidates = sorted(dir_path.glob("PRE-CLEANED-*digest.json"))
        if not candidates:
            raise FileNotFoundError(f"No digest found for {date}")
        with open(candidates[-1], "r") as f:
            return json.load(f)

    def _save_digest(self, date: str, digest: Dict[str, Any]) -> None:
        dir_path = self.data_dir / date
        dir_path.mkdir(parents=True, exist_ok=True)
        # overwrite last candidate for simplicity
        out_path = sorted(dir_path.glob("PRE-CLEANED-*digest.json"))[-1]
        with open(out_path, "w") as f:
            json.dump(digest, f, indent=2)

    def begin_recording(self, date: str, story_id: str) -> Dict[str, Any]:
        digest = self._load_digest(date)
        packet = self._find_story(digest, story_id)
        now = datetime.utcnow().isoformat() + "Z"
        packet["explainer"]["status"] = "recording"
        packet["explainer"]["started_at"] = now
        self._save_digest(date, digest)
        return packet

    def end_recording(self, date: str, story_id: str, raw_path: Optional[str]=None) -> Dict[str, Any]:
        digest = self._load_digest(date)
        packet = self._find_story(digest, story_id)
        now = datetime.utcnow().isoformat() + "Z"
        packet["explainer"]["status"] = "recorded"
        packet["explainer"]["completed_at"] = now
        packet.setdefault("video", {})
        packet["video"]["status"] = "pending"
        if raw_path:
            packet["video"]["raw_recording_path"] = raw_path
        self._save_digest(date, digest)
        return packet

    @staticmethod
    def _find_story(digest: Dict[str, Any], story_id: str) -> Dict[str, Any]:
        for p in digest.get("story_packets", []):
            if p.get("id") == story_id:
                return p
        raise KeyError(f"Story {story_id} not found")
