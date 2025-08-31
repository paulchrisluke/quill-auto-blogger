"""
Transcription service using ffmpeg, yt-dlp, and Cloudflare Workers AI Whisper API.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import httpx
import yt_dlp
from httpx import Timeout

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
        
        # Prepare request
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/ai/run/@cf/openai/whisper"
        headers = {
            "Authorization": f"Bearer {self.cloudflare_api_token}",
            "Content-Type": "application/octet-stream"
        }
        
        try:
            with open(audio_path, 'rb') as f:  # keep handle for streaming
                timeout = Timeout(connect=10.0, read=60.0, write=None, pool=None)
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(url, headers=headers, content=f)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get('success') and 'result' in result:
                    return result['result'].get('text', '')
                else:
                    raise RuntimeError(f"Transcription error: {result}")
                    
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
        audio_path = None  # Initialize to None to avoid UnboundLocalError
        
        try:
            # Download video
            self._download_video(video_url, video_path)
            
            # Extract audio
            audio_path = self.extract_audio(video_path)
            
            # Transcribe
            transcript = self.transcribe_audio(audio_path)
            
            return transcript, video_path, audio_path
            
        except Exception as e:
            # Clean up on error - iterate over paths safely
            for path in [video_path, audio_path]:
                if path and path.exists():
                    try:
                        path.unlink()
                    except Exception:
                        pass  # Ignore cleanup errors
            raise RuntimeError(f"Failed to download and transcribe video: {e}") from e
    
    def _download_video(self, url: str, output_path: Path):
        """Download video from URL using yt-dlp for Twitch clips."""
        try:
            # Use yt-dlp for Twitch clips, regular download for other URLs
            if 'clips.twitch.tv' in url or 'twitch.tv' in url:
                return self._download_with_ytdlp(url, output_path)
            else:
                return self._download_with_httpx(url, output_path)
                            
        except (yt_dlp.DownloadError, httpx.HTTPError, OSError) as e:
            raise RuntimeError(f"Failed to download video: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error during download: {e}") from e
    
    def _download_with_ytdlp(self, url: str, output_path: Path):
        """Download video using yt-dlp."""
        # Get the base path without extension to handle format mismatches
        base_path = output_path.with_suffix('')
        
        ydl_opts = {
            'outtmpl': str(base_path) + '.%(ext)s',  # Let yt-dlp choose extension
            'format': 'best[ext=mp4]/best',  # Prefer MP4 format
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find the actual downloaded file (may have different extension)
            # Filter for likely video/audio file extensions and exclude unwanted files
            allowed_extensions = {'.mp4', '.mkv', '.webm', '.m4a', '.mp3', '.mov', '.flv', '.avi', '.wmv', '.flac', '.wav', '.aac', '.ogg'}
            unwanted_suffixes = {'.info.json', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.vtt', '.srt'}
            
            candidate_files = []
            for file_path in base_path.parent.glob(f"{base_path.name}.*"):
                # Skip files with unwanted suffixes
                if any(file_path.name.endswith(suffix) for suffix in unwanted_suffixes):
                    continue
                
                # Include files with allowed extensions
                if file_path.suffix.lower() in allowed_extensions:
                    candidate_files.append(file_path)
            
            if not candidate_files:
                raise RuntimeError(f"yt-dlp download failed - no valid video/audio files found. Searched for files matching {base_path.name}.*")
            
            # Sort by modification time (newest first) and pick the freshest file
            candidate_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            actual_path = candidate_files[0]
            
            # If the actual file has a different extension than expected, rename it
            if actual_path.suffix != output_path.suffix:
                try:
                    # Use atomic replace to overwrite output_path with actual_path
                    os.replace(actual_path, output_path)
                except (OSError, PermissionError) as e:
                    # Clean up the actual file if replace fails
                    cleanup_error = None
                    try:
                        if actual_path.exists():
                            actual_path.unlink()
                    except OSError as cleanup_exc:
                        cleanup_error = cleanup_exc
                    
                    # Re-raise with full context including cleanup errors
                    if cleanup_error:
                        raise RuntimeError(f"Failed to rename downloaded file from {actual_path} to {output_path}: {e} (cleanup also failed: {cleanup_error})") from e
                    else:
                        raise RuntimeError(f"Failed to rename downloaded file from {actual_path} to {output_path}: {e}") from e
            else:
                # Same extension; nothing else to do
                pass
                
        except yt_dlp.DownloadError as e:
            raise RuntimeError(f"yt-dlp download failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error in yt-dlp download: {e}") from e
    
    def _download_with_httpx(self, url: str, output_path: Path):
        """Download video using httpx (for non-Twitch URLs)."""
        try:
            timeout = Timeout(connect=10.0, read=30.0, write=None, pool=None)
            with httpx.Client(timeout=timeout) as client:
                with client.stream('GET', url) as response:
                    response.raise_for_status()
                    
                    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
                    try:
                        with open(tmp_path, 'wb') as f:
                            for chunk in response.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                            f.flush()
                            try:
                                os.fsync(f.fileno())
                            except (OSError, TypeError):
                                # Skip fsync if not supported or in test environment
                                pass
                        os.replace(tmp_path, output_path)
                    except Exception:
                        # Best-effort cleanup; ignore if it doesn't exist
                        try:
                            if tmp_path.exists():
                                tmp_path.unlink()
                        except OSError:
                            pass
                        raise
                            
        except httpx.HTTPError as e:
            raise RuntimeError(f"httpx download failed: {e}") from e
        except OSError as e:
            raise RuntimeError(f"File system error during download: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error in httpx download: {e}") from e
    
    def cleanup_temp_files(self, *file_paths: Path):
        """Clean up temporary files."""
        for file_path in file_paths:
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass  # Ignore cleanup errors
