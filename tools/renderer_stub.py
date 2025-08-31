#!/usr/bin/env python3
"""
Local video renderer for story packets (M1.5).
Generates 1080x1920 MP4 videos from digest story_packets using FFmpeg.
"""

import json
import subprocess
import textwrap
from pathlib import Path
from typing import List, Dict, Any
import logging
import sys

# Add parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.media import probe_duration, file_exists

logger = logging.getLogger(__name__)


def sanitize_story_id(story_id: str) -> str:
    """Sanitize story ID for safe use in filenames."""
    if not story_id:
        return "unknown"
    
    # Replace invalid characters with underscores
    import re
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', story_id)
    
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    # Truncate to reasonable length
    if len(sanitized) > 50:
        sanitized = sanitized[:50]
    
    # Fallback if result is empty
    if not sanitized:
        return "unknown"
    
    return sanitized


def make_card(text: str, out_png: Path, w: int = 1080, h: int = 1920, pad: int = 60) -> None:
    """Create a text card image using FFmpeg drawtext filter."""
    # Escape special characters for FFmpeg
    escaped_text = text.replace("'", "\\'").replace(":", "\\:").replace('"', '\\"')
    
    # FFmpeg command to create text card
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=white:s={w}x{h}:d=1",
        "-vf", f"drawtext=text='{escaped_text}':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=48:fontcolor=black:box=1:boxcolor=white:boxborderw=5",
        "-vframes", "1",
        "-y",  # Overwrite output
        str(out_png)
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Created card: {out_png}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed creating card: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg.")


def concat(images: List[Path], out_mp4: Path, slate_sec: int = 6) -> None:
    """Concatenate image sequence into MP4 video."""
    if not images:
        raise ValueError("No images provided for concatenation")
    
    # Build input list for FFmpeg
    inputs = []
    for img in images:
        inputs.extend(["-loop", "1", "-t", str(slate_sec), "-i", str(img)])
    
    # Build filter complex for scaling and concatenation
    scale_filters = []
    for i in range(len(images)):
        scale_filters.append(f"[{i}:v]scale=1080:-2,setsar=1[v{i}]")
    
    # Concatenation filter
    concat_inputs = "".join([f"[v{i}]" for i in range(len(images))])
    concat_filter = f"{concat_inputs}concat=n={len(images)}:v=1:a=0,format=yuv420p[v]"
    
    # Combine all filters
    filter_complex = ";".join(scale_filters + [concat_filter])
    
    cmd = [
        "ffmpeg",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-r", "30",  # 30fps
        "-y",  # Overwrite output
        str(out_mp4)
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Created video: {out_mp4}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed creating video: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg.")


def render_for_packet(packet: Dict[str, Any], out_dir: Path) -> str:
    """Render video for a single story packet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract packet data
    title = packet.get("title_human") or packet.get("title_raw", "Untitled")
    why = packet.get("why", "")
    highlights = packet.get("highlights", [])
    story_id = sanitize_story_id(packet.get("id", "unknown"))
    
    # Generate image sequence
    images = []
    
    # 1. Intro card with title
    intro = out_dir / f"{story_id}_01_intro.png"
    make_card(title, intro)
    images.append(intro)
    
    # 2. Why card (if available)
    if why:
        why_card = out_dir / f"{story_id}_02_why.png"
        # Wrap text for better readability
        wrapped_why = textwrap.fill(f"Why: {why}", width=28)
        make_card(wrapped_why, why_card)
        images.append(why_card)
    
    # 3. Highlights cards (up to 2)
    for i, highlight in enumerate(highlights[:2], start=3):
        highlight_card = out_dir / f"{story_id}_{i:02d}_hl.png"
        # Wrap text and add bullet point
        wrapped_highlight = textwrap.fill(f"• {highlight}", width=28)
        make_card(wrapped_highlight, highlight_card)
        images.append(highlight_card)
    
    # 4. Outro card
    outro = out_dir / f"{story_id}_99_outro.png"
    make_card("More in the blog → paulchrisluke.com", outro)
    images.append(outro)
    
    # Create final video
    out_mp4 = out_dir / f"{story_id}.mp4"
    concat(images, out_mp4)
    
    return str(out_mp4)


def get_video_duration(video_path: Path) -> float:
    """Get video duration using ffprobe."""
    duration = probe_duration(str(video_path))
    return round(duration, 2) if duration else 0.0


def render_from_digest(digest_path: Path, out_dir: Path) -> bool:
    """Render videos for all story packets in a digest."""
    # Load digest data
    try:
        with open(digest_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        raise RuntimeError(f"Could not load digest {digest_path}: {e}")
    
    story_packets = data.get("story_packets", [])
    if not story_packets:
        logger.info("No story packets found in digest")
        return False
    
    changed = False
    
    for packet in story_packets:
        # Check if already rendered and file exists
        video_info = packet.get("video", {}) or {}
        if video_info.get("status") == "rendered":
            dst_path = video_info.get("path")
            if dst_path and file_exists(dst_path):
                logger.info(f"Skipping {packet.get('id')} - already rendered")
                # Probe duration if missing
                if not video_info.get("duration_s"):
                    duration = probe_duration(dst_path)
                    if duration:
                        video_info["duration_s"] = round(duration, 2)
                        changed = True
                continue
        
        # Render video
        try:
            out_mp4 = render_for_packet(packet, out_dir)
            
            # Update packet with video info
            if "video" not in packet:
                packet["video"] = {}
            
            packet["video"]["status"] = "rendered"
            packet["video"]["path"] = out_mp4
            packet["video"]["canvas"] = "1080x1920"
            
            # Get duration
            duration = get_video_duration(Path(out_mp4))
            if duration > 0:
                packet["video"]["duration_s"] = duration
            
            changed = True
            logger.info(f"Rendered video for {packet.get('id')}: {out_mp4}")
            
        except Exception as e:
            logger.error(f"Failed to render video for {packet.get('id')}: {e}")
            # Mark as failed
            if "video" not in packet:
                packet["video"] = {}
            packet["video"]["status"] = "failed"
            packet["video"]["error"] = str(e)
    
    # Save updated digest if changed
    if changed:
        try:
            with open(digest_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Updated digest: {digest_path}")
        except Exception as e:
            logger.error(f"Failed to save updated digest: {e}")
    
    return changed


def main():
    """Main entry point for command line usage."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python renderer_stub.py YYYY-MM-DD")
        sys.exit(1)
    
    date = sys.argv[1]
    
    # Validate date format
    try:
        from datetime import datetime
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        print("Error: Date must be in YYYY-MM-DD format")
        sys.exit(1)
    
    # Setup paths
    digest_path = Path(f"blogs/{date}/PRE-CLEANED-{date}_digest.json")
    out_dir = Path(f"out/videos/{date}")
    
    if not digest_path.exists():
        print(f"Error: Digest not found: {digest_path}")
        sys.exit(1)
    
    # Render videos
    try:
        changed = render_from_digest(digest_path, out_dir)
        if changed:
            print(f"Successfully rendered videos for {date}")
        else:
            print(f"No new videos to render for {date}")
    except Exception as e:
        print(f"Error rendering videos: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
