"""
Twitch API service for fetching clips and processing them.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import httpx

from models import TwitchClip
from services.auth import AuthService
from services.transcribe import TranscriptionService
from services.utils import CacheManager, generate_filename, sanitize_filename

logger = logging.getLogger(__name__)


class TwitchService:
    """Handles Twitch API interactions and clip processing."""
    
    def __init__(self):
        self.auth_service = AuthService()
        self.transcribe_service = TranscriptionService()
        self.cache_manager = CacheManager()
        self.base_url = "https://api.twitch.tv/helix"
    
    def fetch_clips(self, broadcaster_id: str, days_back: int = 7) -> List[TwitchClip]:
        """Fetch recent clips for a broadcaster."""
        headers = self.auth_service.get_twitch_headers()
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": start_date.isoformat().replace("+00:00", "Z"),
            "ended_at": end_date.isoformat().replace("+00:00", "Z"),
            "first": 100  # Max clips per request
        }
        
        clips = []
        
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0), http2=True) as client:
                cursor = None
                while True:
                    q = dict(params)
                    if cursor:
                        q["after"] = cursor
                    # Minimal retry/backoff for 429
                    for attempt in range(3):
                        resp = client.get(f"{self.base_url}/clips", headers=headers, params=q)
                        if resp.status_code != 429:
                            break
                        reset = float(resp.headers.get("Ratelimit-Reset", "1"))
                        time.sleep(min(reset, 5.0))  # cap sleep to 5s
                    resp.raise_for_status()
                    data = resp.json()

                    for clip_data in data.get("data", []):
                        clip = self._parse_clip_data(clip_data)
                        if not self.cache_manager.is_seen(clip.id, "twitch_clip"):
                            clips.append(clip)

                    cursor = (data.get("pagination") or {}).get("cursor")
                    if not cursor:
                        break
                return clips
                
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Twitch API error: {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Error fetching clips: {e}")
    
    def _parse_clip_data(self, clip_data: dict) -> TwitchClip:
        """Parse Twitch API clip data into TwitchClip model."""
        return TwitchClip(
            id=clip_data["id"],
            title=clip_data["title"],
            url=clip_data["url"],
            broadcaster_name=clip_data["broadcaster_name"],
            created_at=datetime.fromisoformat(clip_data["created_at"].replace("Z", "+00:00")),
            duration=float(clip_data.get("duration", 0)),
            view_count=int(clip_data.get("view_count", 0)),
            language=clip_data.get("language", "en")
        )
    
    def process_clip(self, clip: TwitchClip) -> bool:
        """Process a clip: download, transcribe, and save.

        Idempotent: returns True if saved or already seen; False on error.
        """
        try:
            # Check if already processed
            if self.cache_manager.is_seen(clip.id, "twitch_clip"):
                logger.info("Clip %s already processed, skipping", clip.id)
                return True
            
            logger.info("Processing clip: %s", clip.title)
            
            # Download and transcribe using yt-dlp
            transcript, video_path, audio_path = self.transcribe_service.download_and_transcribe(
                clip.url, clip.id
            )
            
            # Move temporary files to persistent storage
            video_filename = f"video_{clip.id}_{sanitize_filename(clip.title)}.mp4"
            audio_filename = f"audio_{clip.id}_{sanitize_filename(clip.title)}.wav"
            
            persistent_video_path = self.cache_manager.persist_file(video_path, video_filename, clip.created_at)
            persistent_audio_path = self.cache_manager.persist_file(audio_path, audio_filename, clip.created_at)
            
            # Update clip with persistent paths and transcript
            clip.transcript = transcript
            clip.video_path = str(persistent_video_path)
            clip.audio_path = str(persistent_audio_path)
            
            # Save clip data
            self._save_clip(clip)
            
            # Mark as seen
            self.cache_manager.mark_seen(clip.id, "twitch_clip")
            
            logger.info("Successfully processed clip with transcript: %s", clip.title)
        except Exception:
            logger.exception("Error processing clip %s", clip.id)
            return False
        else:
            return True
    
    def _save_clip(self, clip: TwitchClip):
        """Save clip data to JSON file."""
        # Generate filename
        safe_title = sanitize_filename(clip.title)
        filename = generate_filename("twitch_clip", f"{clip.id}_{safe_title}")
        
        # Convert to dict for JSON serialization, excluding None values
        clip_data = clip.model_dump(exclude_none=True)
        
        # Save to data directory
        self.cache_manager.save_json(filename, clip_data, clip.created_at)
    
    def get_user_id(self, username: str) -> Optional[str]:
        """Get Twitch broadcaster ID from username."""
        headers = self.auth_service.get_twitch_headers()
        params = {"login": username}
        
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=10.0), http2=True) as client:
                response = client.get(f"{self.base_url}/users", headers=headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                users = data.get("data", [])
                
                if users:
                    return users[0]["id"]  # This is the broadcaster ID
                return None
                
        except Exception:
            logger.exception("Error getting broadcaster ID for %s", username)
            return None
    
    def fetch_clips_by_username(self, username: str, days_back: int = 7) -> List[TwitchClip]:
        """Fetch clips by username (converts to broadcaster ID first)."""
        broadcaster_id = self.get_user_id(username)
        if not broadcaster_id:
            raise ValueError(f"Could not find broadcaster ID for username: {username}")
        
        return self.fetch_clips(broadcaster_id, days_back)
    
    def fetch_clips_by_broadcaster_id(self, broadcaster_id: str, days_back: int = 7) -> List[TwitchClip]:
        """Fetch clips by broadcaster ID directly."""
        return self.fetch_clips(broadcaster_id, days_back)
