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

    def load_digest(self, date: datetime) -> tuple[Dict[str, Any], Path]:
        """Public method to load a digest for read-only access."""
        return self._load_digest(date)

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

    def _normalize_date(self, date: datetime, assume_utc: bool = False) -> datetime:
        """
        Normalize datetime to UTC.
        
        Args:
            date: The datetime to normalize
            assume_utc: If True and date is naive, assume it's UTC. 
                       If False (default), raise ValueError for naive datetimes.
        
        Returns:
            Timezone-aware datetime in UTC
            
        Raises:
            ValueError: If date is naive and assume_utc is False
        """
        if date.tzinfo is None:
            if assume_utc:
                return date.replace(tzinfo=timezone.utc)
            else:
                raise ValueError(
                    "Timezone-aware datetime required. Pass assume_utc=True to "
                    "explicitly treat naive datetime as UTC, or ensure the datetime "
                    "has timezone information."
                )
        else:
            return date.astimezone(timezone.utc)

    def begin_recording(self, date: datetime, story_id: str, assume_utc: bool = False) -> Dict[str, Any]:
        """
        Begin recording for a story.
        
        Args:
            date: Timezone-aware datetime for the story date
            story_id: Identifier for the story
            assume_utc: If True and date is naive, assume it's UTC. 
                       If False (default), raise ValueError for naive datetimes.
        
        Returns:
            Updated story packet
            
        Raises:
            ValueError: If date is naive and assume_utc is False
        """
        digest, file_path = self._load_digest(date)
        packet = self._find_story(digest, story_id)
        # Normalize date to UTC
        normalized_date = self._normalize_date(date, assume_utc)
        # Use current UTC time for started_at, not the story date
        now = datetime.now(timezone.utc).isoformat()
        # Ensure explainer dict exists
        packet.setdefault("explainer", {})
        packet["explainer"]["status"] = "recording"
        packet["explainer"]["started_at"] = now
        self._save_digest(normalized_date, digest, file_path)
        return packet

    def end_recording(self, date: datetime, story_id: str, raw_path: Optional[str]=None, assume_utc: bool = False) -> Dict[str, Any]:
        """
        End recording for a story.
        
        Args:
            date: Timezone-aware datetime for the story date
            story_id: Identifier for the story
            raw_path: Optional path to the raw recording file
            assume_utc: If True and date is naive, assume it's UTC. 
                       If False (default), raise ValueError for naive datetimes.
        
        Returns:
            Updated story packet
            
        Raises:
            ValueError: If date is naive and assume_utc is False
        """
        digest, file_path = self._load_digest(date)
        packet = self._find_story(digest, story_id)
        # Normalize date to UTC
        normalized_date = self._normalize_date(date, assume_utc)
        # Use current UTC time for completed_at, not the story date
        now = datetime.now(timezone.utc).isoformat()
        # Ensure explainer dict exists
        packet.setdefault("explainer", {})
        packet["explainer"]["status"] = "recorded"
        packet["explainer"]["completed_at"] = now
        # Ensure video dict exists
        packet.setdefault("video", {})
        packet["video"]["status"] = "pending"
        if raw_path:
            packet["video"]["raw_recording_path"] = raw_path
        self._save_digest(normalized_date, digest, file_path)
        return packet

    @staticmethod
    def _find_story(digest: Dict[str, Any], story_id: str) -> Dict[str, Any]:
        for p in digest.get("story_packets", []):
            if p.get("id") == story_id:
                return p
        raise KeyError(f"Story {story_id} not found")
