"""
Twitch API service for fetching clips and processing them.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional
import httpx

from models import TwitchClip
from services.auth import AuthService
from services.transcribe import TranscriptionService
from services.utils import CacheManager, generate_filename, sanitize_filename


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
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": start_date.isoformat() + "Z",
            "ended_at": end_date.isoformat() + "Z",
            "first": 100  # Max clips per request
        }
        
        clips = []
        
        try:
            with httpx.Client() as client:
                response = client.get(f"{self.base_url}/clips", headers=headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                for clip_data in data.get("data", []):
                    clip = self._parse_clip_data(clip_data)
                    
                    # Check if we've already processed this clip
                    if not self.cache_manager.is_seen(clip.id, "twitch_clip"):
                        clips.append(clip)
                
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
        """Process a clip: download, transcribe, and save."""
        try:
            # Check if already processed
            if self.cache_manager.is_seen(clip.id, "twitch_clip"):
                print(f"Clip {clip.id} already processed, skipping")
                return True
            
            print(f"Processing clip: {clip.title}")
            
            # Download and transcribe
            transcript, video_path, audio_path = self.transcribe_service.download_and_transcribe(
                clip.url, clip.id
            )
            
            # Update clip with paths and transcript
            clip.transcript = transcript
            clip.video_path = str(video_path)
            clip.audio_path = str(audio_path)
            
            # Save clip data
            self._save_clip(clip)
            
            # Mark as seen
            self.cache_manager.mark_seen(clip.id, "twitch_clip")
            
            # Clean up temporary files
            self.transcribe_service.cleanup_temp_files(video_path, audio_path)
            
            print(f"Successfully processed clip: {clip.title}")
            return True
            
        except Exception as e:
            print(f"Error processing clip {clip.id}: {e}")
            return False
    
    def _save_clip(self, clip: TwitchClip):
        """Save clip data to JSON file."""
        # Generate filename
        safe_title = sanitize_filename(clip.title)
        filename = generate_filename("twitch_clip", f"{clip.id}_{safe_title}")
        
        # Convert to dict for JSON serialization
        clip_data = clip.model_dump()
        
        # Save to data directory
        self.cache_manager.save_json(filename, clip_data, clip.created_at)
    
    def get_user_id(self, username: str) -> Optional[str]:
        """Get Twitch broadcaster ID from username."""
        headers = self.auth_service.get_twitch_headers()
        params = {"login": username}
        
        try:
            with httpx.Client() as client:
                response = client.get(f"{self.base_url}/users", headers=headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                users = data.get("data", [])
                
                if users:
                    return users[0]["id"]  # This is the broadcaster ID
                return None
                
        except Exception as e:
            print(f"Error getting broadcaster ID for {username}: {e}")
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
