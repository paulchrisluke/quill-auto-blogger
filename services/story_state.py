from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

class StoryState:
    """
    Mutates v2 digest: story_packets[*].explainer.status & video placeholders.
    """

    def __init__(self, data_dir: str = "blogs") -> None:
        self.data_dir = Path(data_dir)

    def _load_digest(self, date: datetime) -> tuple[Dict[str, Any], Path]:
        # Convert datetime to YYYY-MM-DD format for file paths
        date_str = date.strftime("%Y-%m-%d")
        # Locate PRE-CLEANED digest for date
        dir_path = self.data_dir / date_str
        candidates = sorted(dir_path.glob("PRE-CLEANED-*digest.json"))
        if not candidates:
            raise FileNotFoundError(f"No digest found for {date_str}")
        file_path = candidates[-1]
        with open(file_path, "r") as f:
            return json.load(f), file_path

    def _save_digest(self, date: datetime, digest: Dict[str, Any], file_path: Path) -> None:
        # Convert datetime to YYYY-MM-DD format for file paths
        date_str = date.strftime("%Y-%m-%d")
        dir_path = self.data_dir / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        # Write atomically to avoid partial/corrupt JSON on crash
        temp_path = file_path.with_suffix('.tmp')
        with open(temp_path, "w") as f:
            json.dump(digest, f, indent=2)
        temp_path.replace(file_path)

    def begin_recording(self, date: datetime, story_id: str) -> Dict[str, Any]:
        digest, file_path = self._load_digest(date)
        packet = self._find_story(digest, story_id)
        # Ensure date is timezone-aware and convert to UTC
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        else:
            date = date.astimezone(timezone.utc)
        now = date.isoformat()
        packet["explainer"]["status"] = "recording"
        packet["explainer"]["started_at"] = now
        self._save_digest(date, digest, file_path)
        return packet

    def end_recording(self, date: datetime, story_id: str, raw_path: Optional[str]=None) -> Dict[str, Any]:
        digest, file_path = self._load_digest(date)
        packet = self._find_story(digest, story_id)
        # Ensure date is timezone-aware and convert to UTC
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        else:
            date = date.astimezone(timezone.utc)
        now = date.isoformat()
        packet["explainer"]["status"] = "recorded"
        packet["explainer"]["completed_at"] = now
        packet.setdefault("video", {})
        packet["video"]["status"] = "pending"
        if raw_path:
            packet["video"]["raw_recording_path"] = raw_path
        self._save_digest(date, digest, file_path)
        return packet

    @staticmethod
    def _find_story(digest: Dict[str, Any], story_id: str) -> Dict[str, Any]:
        for p in digest.get("story_packets", []):
            if p.get("id") == story_id:
                return p
        raise KeyError(f"Story {story_id} not found")
