"""
Media utilities for video processing and metadata extraction.
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def probe_duration(path: str) -> Optional[float]:
    """
    Probe video duration using ffprobe.
    
    Args:
        path: Path to video file
        
    Returns:
        Duration in seconds, or None if ffprobe fails or is unavailable
    """
    try:
        result = subprocess.run([
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path)
        ], capture_output=True, text=True, check=True)
        
        duration = float(result.stdout.strip())
        logger.info(f"Probed duration for {path}: {duration}s")
        return duration
        
    except subprocess.CalledProcessError as e:
        logger.warning(f"ffprobe failed for {path}: {e}")
        return None
    except FileNotFoundError:
        logger.warning("ffprobe not found. Install ffmpeg to enable duration probing.")
        return None
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse duration for {path}: {e}")
        return None


def file_exists(path: str) -> bool:
    """
    Check if a file exists at the given path.
    
    Args:
        path: Path to check
        
    Returns:
        True if file exists, False otherwise
    """
    return Path(path).exists()
