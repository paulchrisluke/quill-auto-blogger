"""
Transcription service using ffmpeg and Cloudflare Workers AI Whisper API.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import httpx

from services.utils import CacheManager


class TranscriptionService:
    """Handles video to audio conversion and transcription."""
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.cloudflare_account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
        self.cloudflare_api_token = os.getenv('CLOUDFLARE_API_TOKEN')
        
        if not self.cloudflare_account_id or not self.cloudflare_api_token:
            raise ValueError("Cloudflare credentials not configured")
    
    def extract_audio(self, video_path: Path, output_path: Optional[Path] = None) -> Path:
        """Extract audio from video using ffmpeg."""
        if output_path is None:
            # Create temporary file
            temp_dir = Path(tempfile.gettempdir())
            output_path = temp_dir / f"audio_{video_path.stem}.wav"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # ffmpeg command to extract audio
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',  # Mono
            '-y',  # Overwrite output
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg failed: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")
    
    def transcribe_audio(self, audio_path: Path) -> str:
        """Transcribe audio using Cloudflare Workers AI Whisper API."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Read audio file
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        # Prepare request
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/ai/run/@cf/openai/whisper"
        headers = {
            "Authorization": f"Bearer {self.cloudflare_api_token}",
            "Content-Type": "application/octet-stream"
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, content=audio_data)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get('success') and 'result' in result:
                    return result['result'].get('text', '')
                else:
                    raise RuntimeError(f"Transcription failed: {result}")
                    
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP error during transcription: {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Transcription error: {e}")
    
    def transcribe_video(self, video_path: Path) -> tuple[str, Path]:
        """Extract audio from video and transcribe it."""
        # Extract audio
        audio_path = self.extract_audio(video_path)
        
        try:
            # Transcribe audio
            transcript = self.transcribe_audio(audio_path)
            return transcript, audio_path
        finally:
            # Clean up temporary audio file
            if audio_path.exists() and audio_path.parent == Path(tempfile.gettempdir()):
                audio_path.unlink()
    
    def download_and_transcribe(self, video_url: str, clip_id: str) -> tuple[str, Path, Path]:
        """Download video, extract audio, and transcribe."""
        # Create temporary video file
        temp_dir = Path(tempfile.gettempdir())
        video_path = temp_dir / f"video_{clip_id}.mp4"
        
        try:
            # Download video
            self._download_video(video_url, video_path)
            
            # Extract audio
            audio_path = self.extract_audio(video_path)
            
            # Transcribe
            transcript = self.transcribe_audio(audio_path)
            
            return transcript, video_path, audio_path
            
        except Exception as e:
            # Clean up on error
            for path in [video_path, audio_path]:
                if path and path.exists():
                    path.unlink()
            raise e
    
    def _download_video(self, url: str, output_path: Path):
        """Download video from URL."""
        try:
            with httpx.Client() as client:
                with client.stream('GET', url) as response:
                    response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                            
        except Exception as e:
            raise RuntimeError(f"Failed to download video: {e}")
    
    def cleanup_temp_files(self, *file_paths: Path):
        """Clean up temporary files."""
        for file_path in file_paths:
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass  # Ignore cleanup errors
