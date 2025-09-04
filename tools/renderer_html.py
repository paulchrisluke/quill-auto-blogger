#!/usr/bin/env python3
"""
HTML→PNG slide renderer for story packets (M3).
Generates 1080x1920 PNG slides using Playwright + Jinja2, then stitches to MP4 via FFmpeg.
"""

import json
import os
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import re

from services.media import probe_duration, file_exists

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
    from jinja2 import Environment, FileSystemLoader
except ImportError as e:
    raise ImportError(f"Missing required dependency: {e}. Run: pip install playwright jinja2") from e

logger = logging.getLogger(__name__)

# Default placeholder for short text
DEFAULT_PLACEHOLDER = "Content placeholder text for display purposes"


def get_renderer_config() -> Dict[str, Any]:
    """Get renderer configuration from environment variables with validation."""
    # Validate viewport format
    viewport = os.getenv("RENDERER_VIEWPORT", "1080x1920")
    if not re.match(r'^\d+x\d+$', viewport):
        raise ValueError(f"Invalid viewport format: {viewport}. Expected format: WIDTHxHEIGHT")
    
    width, height = map(int, viewport.split("x"))
    
    # Validate fps
    fps_str = os.getenv("RENDERER_FPS", "30")
    try:
        fps = int(fps_str)
        if not (1 <= fps <= 120):
            raise ValueError(f"FPS must be between 1 and 120, got: {fps}")
    except ValueError as e:
        raise ValueError(f"Invalid FPS value '{fps_str}': {e}")
    
    # Validate slide duration
    slide_duration_str = os.getenv("RENDERER_SLIDE_SECONDS", "6")
    try:
        slide_duration = int(slide_duration_str)
        if slide_duration < 1:
            raise ValueError(f"Slide duration must be >= 1, got: {slide_duration}")
    except ValueError as e:
        raise ValueError(f"Invalid slide duration '{slide_duration_str}': {e}")
    
    # Validate CRF
    crf_str = os.getenv("RENDERER_CRF", "18")
    try:
        crf = int(crf_str)
        if not (0 <= crf <= 51):
            raise ValueError(f"CRF must be between 0 and 51, got: {crf}")
    except ValueError as e:
        raise ValueError(f"Invalid CRF value '{crf_str}': {e}")
    
    return {
        "viewport_width": width,
        "viewport_height": height,
        "fps": fps,
        "slide_duration": slide_duration,
        "crf": crf,
        "force": os.getenv("RENDERER_FORCE", "false").lower() == "true",
        "theme": os.getenv("RENDERER_THEME", "light")
    }


def sanitize_story_id(story_id: str) -> str:
    """Sanitize story ID for safe use in filenames."""
    if not story_id:
        return "unknown"
    
    # Replace invalid characters with underscores
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


def truncate_text(text: str, max_chars: int = 180) -> str:
    """Truncate text to max_chars and add ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars-3] + "..."


def clamp_text_length(text: str, max_chars: int = 180, min_chars: int = 10, default_placeholder: Optional[str] = None) -> str:
    """Clamp text length between min_chars and max_chars."""
    if not text:
        return "No content"
    
    # Remove extra whitespace
    text = " ".join(text.split())
    
    # Clamp to max length
    if len(text) > max_chars:
        text = truncate_text(text, max_chars)
    
    # Ensure minimum length by using default placeholder if needed
    if len(text) < min_chars:
        placeholder = default_placeholder or DEFAULT_PLACEHOLDER
        
        # Ensure placeholder meets min_chars requirement
        if len(placeholder) < min_chars:
            # Pad placeholder with dots if it's too short
            padding_needed = min_chars - len(placeholder)
            placeholder = placeholder + "." * padding_needed
        elif len(placeholder) > min_chars:
            # Truncate placeholder if it's too long
            placeholder = truncate_text(placeholder, min_chars)
        
        text = placeholder
    
    return text


def validate_text_quality(text: str, min_length: int = 5) -> bool:
    """Validate text quality for rendering."""
    if not text:
        return False
    
    # Check minimum length
    if len(text.strip()) < min_length:
        return False
    
    # Check for reasonable word count (avoid single characters)
    words = text.split()
    if len(words) < 2:
        return False
    
    return True


def validate_packet_content(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and provide fallbacks for packet content."""
    validated = packet.copy()
    
    # Validate title (minimum 12 chars)
    title = packet.get("title_human") or packet.get("title_raw", "")
    if not validate_text_quality(title, 12):
        validated["title_human"] = "Untitled Story"
    
    # Validate why (minimum 40 chars)
    why = packet.get("why", "")
    if not validate_text_quality(why, 40):
        validated["why"] = "This story represents important work and improvements to the codebase."
    
    # Validate highlights (at least 1)
    highlights = packet.get("highlights", [])
    valid_highlights = []
    for highlight in highlights:
        if validate_text_quality(highlight, 10):
            valid_highlights.append(clamp_text_length(highlight, 180, 10))
    
    if not valid_highlights:
        valid_highlights = ["Key improvements and updates to the system"]
    
    validated["highlights"] = valid_highlights
    
    return validated


def render_html_to_png(html_str: str, out_path: Path) -> None:
    """Render HTML string to PNG using Playwright."""
    config = get_renderer_config()
    start_time = time.time()
    
    browser = None
    temp_html_path = None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set viewport to configured slide dimensions
            page.set_viewport_size({
                "width": config["viewport_width"], 
                "height": config["viewport_height"]
            })
            
            # Write HTML to temp file and load it
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_str)
                temp_html_path = f.name
            
            # Load the HTML file
            page.goto(f"file://{temp_html_path}")
            
            # Wait for fonts to load
            page.wait_for_load_state("networkidle")
            
            # Wait for fonts to be ready to avoid layout shifts
            page.wait_for_function("document.fonts.ready")
            
            # Take screenshot of viewport only (not full page)
            page.screenshot(path=str(out_path), full_page=False)
            
            render_time = (time.time() - start_time) * 1000
            logger.info(f"Rendered PNG: {out_path} ({render_time:.0f}ms)")
                
    except PlaywrightError as e:
        render_time = (time.time() - start_time) * 1000
        logger.exception(f"Playwright error during HTML to PNG rendering after {render_time:.0f}ms")
        raise RuntimeError(f"Playwright browser error: {e}. Please ensure Playwright is installed and system dependencies are available.") from e
    except PlaywrightTimeoutError as e:
        render_time = (time.time() - start_time) * 1000
        logger.exception(f"Playwright timeout during HTML to PNG rendering after {render_time:.0f}ms")
        raise RuntimeError(f"Rendering timeout: {e}. The page may be too complex or network resources unavailable.") from e
    except Exception as e:
        render_time = (time.time() - start_time) * 1000
        logger.exception(f"Unexpected error during HTML to PNG rendering after {render_time:.0f}ms")
        raise RuntimeError(f"HTML rendering failed: {e}") from e
    finally:
        # Clean up resources even if browser crashes
        if temp_html_path:
            Path(temp_html_path).unlink(missing_ok=True)
        # Note: browser is automatically closed by the sync_playwright() context manager


class HtmlSlideRenderer:
    """Renders story slides using HTML templates and Playwright."""
    
    def __init__(self):
        # Setup Jinja2 environment with autoescape for security
        templates_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True  # Enable autoescape to prevent XSS
        )
        
        # Brand tokens path
        self.brand_tokens_path = str(Path(__file__).parent / "assets" / "brand-tokens.css")
        
        # Pre-load templates
        self.intro_template = self.env.get_template("story_intro.html")
        self.why_template = self.env.get_template("story_why.html")
        self.highlight_template = self.env.get_template("story_hl.html")
        self.outro_template = self.env.get_template("story_outro.html")
    
    def render_intro(self, packet: Dict[str, Any], out_path: Path) -> Path:
        """Render intro slide with title and subtitle."""
        title = packet.get("title_human") or packet.get("title_raw", "Untitled")
        
        # Create subtitle from repo and PR info
        subtitle_parts = []
        if packet.get("repo"):
            subtitle_parts.append(packet["repo"])
        if packet.get("pr_number"):
            subtitle_parts.append(f"PR #{packet['pr_number']}")
        if packet.get("date"):
            subtitle_parts.append(packet["date"])
        
        subtitle = " • ".join(subtitle_parts) if subtitle_parts else None
        
        # Clamp title length and validate quality
        title = clamp_text_length(title, 200, 10)
        if not validate_text_quality(title, 5):
            title = "Untitled Story"
        
        # Render HTML
        config = get_renderer_config()
        html = self.intro_template.render(
            title=title, 
            subtitle=subtitle,
            theme=config["theme"]
        )
        render_html_to_png(html, out_path)
        
        return out_path
    
    def render_why(self, packet: Dict[str, Any], out_path: Path) -> Path:
        """Render why slide with explanation."""
        why = packet.get("why", "")
        if not why:
            raise ValueError("No 'why' content found in packet")
        
        # Clamp why text length and validate quality
        why = clamp_text_length(why, 300, 20)
        if not validate_text_quality(why, 10):
            raise ValueError("Why text is too short or invalid")
        
        # Render HTML
        config = get_renderer_config()
        html = self.why_template.render(
            why=why,
            theme=config["theme"]
        )
        render_html_to_png(html, out_path)
        
        return out_path
    
    def render_highlights(self, packet: Dict[str, Any], out_dir: Path, story_id: str) -> List[Path]:
        """Render highlight slides (up to 3 slides with 2-3 bullets each)."""
        highlights = packet.get("highlights", [])
        if not highlights:
            return []
        
        # Process highlights with quality validation
        processed_highlights = []
        for highlight in highlights:
            if validate_text_quality(highlight, 5):
                processed_highlight = clamp_text_length(highlight, 180, 10)
                processed_highlights.append(processed_highlight)
        
        # Ensure we have at least one valid highlight
        if not processed_highlights:
            processed_highlights = ["Key improvements and updates"]
        
        # Group highlights into slides (2-3 per slide)
        highlight_slides = []
        for i in range(0, len(processed_highlights), 3):
            slide_highlights = processed_highlights[i:i+3]
            highlight_slides.append(slide_highlights)
        
        # Limit to 3 slides max
        highlight_slides = highlight_slides[:3]
        
        rendered_paths = []
        for i, slide_highlights in enumerate(highlight_slides, start=1):
            out_path = out_dir / f"{story_id}_hl_{i:02d}.png"
            
            # Render HTML
            config = get_renderer_config()
            html = self.highlight_template.render(
                highlights=slide_highlights,
                theme=config["theme"]
            )
            render_html_to_png(html, out_path)
            
            rendered_paths.append(out_path)
        
        return rendered_paths
    
    def render_outro(self, packet: Dict[str, Any], out_path: Path) -> Path:
        """Render outro slide with CTA."""
        # Render HTML
        config = get_renderer_config()
        html = self.outro_template.render(
            theme=config["theme"]
        )
        render_html_to_png(html, out_path)
        
        return out_path


class VideoComposer:
    """Composes MP4 videos from PNG slides using FFmpeg."""
    
    def stitch(self, slide_paths: List[Path], out_path: Path, fps: int = None, crf: int = None, slide_duration: int = None) -> None:
        """Stitch PNG slides into MP4 video using FFmpeg."""
        if not slide_paths:
            raise ValueError("No slides provided for stitching")
        
        # Get configuration
        config = get_renderer_config()
        fps = fps or config["fps"]
        crf = crf or config["crf"]
        slide_duration = slide_duration or config["slide_duration"]
        
        # Build input list for FFmpeg
        inputs = []
        for img in slide_paths:
            inputs.extend(["-loop", "1", "-t", str(slide_duration), "-i", str(img)])
        
        # Build filter complex for scaling and concatenation
        scale_filters = []
        for i in range(len(slide_paths)):
            scale_filters.append(f"[{i}:v]scale={config['viewport_width']}:-2,setsar=1[v{i}]")
        
        # Concatenation filter
        concat_inputs = "".join([f"[v{i}]" for i in range(len(slide_paths))])
        concat_filter = f"{concat_inputs}concat=n={len(slide_paths)}:v=1:a=0,format=yuv420p[v]"
        
        # Combine all filters
        filter_complex = ";".join(scale_filters + [concat_filter])
        
        cmd = [
            "ffmpeg",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-r", str(fps),
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "medium",
            "-y",  # Overwrite output
            str(out_path)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            logger.info(f"Created video: {out_path}")
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"ffmpeg timed out after 300 seconds while creating video") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg failed creating video: {e.stderr}") from e
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")


def render_for_packet(packet: Dict[str, Any], out_dir: Path) -> str:
    """Render video for a single story packet using HTML→PNG renderer."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Validate and provide fallbacks for packet content
    validated_packet = validate_packet_content(packet)
    
    # Extract packet data
    story_id = sanitize_story_id(validated_packet.get("id", "unknown"))
    out_mp4 = out_dir / f"{story_id}.mp4"
    
    # Check idempotency - skip if video exists and force is not enabled
    config = get_renderer_config()
    if out_mp4.exists() and not config["force"]:
        logger.info(f"Skipping render for {story_id} - video already exists")
        return str(out_mp4)
    
    # Initialize renderer and composer
    renderer = HtmlSlideRenderer()
    composer = VideoComposer()
    
    # Generate image sequence
    images = []
    
    # 1. Intro card with title
    intro = out_dir / f"{story_id}_01_intro.png"
    renderer.render_intro(validated_packet, intro)
    images.append(intro)
    
    # 2. Why card (if available)
    if validated_packet.get("why"):
        why_card = out_dir / f"{story_id}_02_why.png"
        renderer.render_why(validated_packet, why_card)
        images.append(why_card)
    
    # 3. Highlights cards (up to 3 slides)
    highlight_images = renderer.render_highlights(validated_packet, out_dir, story_id)
    images.extend(highlight_images)
    
    # 4. Outro card
    outro = out_dir / f"{story_id}_99_outro.png"
    renderer.render_outro(validated_packet, outro)
    images.append(outro)
    
    # Create final video
    composer.stitch(images, out_mp4)
    
    return str(out_mp4)


def get_video_duration(video_path: Path) -> float:
    """Get video duration using ffprobe."""
    duration = probe_duration(str(video_path))
    return round(duration, 2) if duration else 0.0


def render_from_digest(digest_path: Path, out_dir: Path) -> bool:
    """Render videos for all story packets in a digest."""
    start_time = time.time()
    
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
    config = get_renderer_config()
    rendered_count = 0
    failed_count = 0
    skipped_count = 0
    
    logger.info(f"Processing {len(story_packets)} story packets for rendering")
    
    for packet in story_packets:
        story_id = packet.get("id", "unknown")
        
        # Check if packet needs rendering based on explainer status or video status
        explainer_status = packet.get("explainer", {}).get("status")
        video_status = packet.get("video", {}).get("status")
        
        needs_rendering = (
            explainer_status in ["recorded", "recording"] or 
            video_status != "rendered"
        )
        
        if not needs_rendering:
            logger.info(f"Skipping {story_id} - no rendering needed")
            skipped_count += 1
            continue
        
        # Check if already rendered and file exists (idempotency)
        video_info = packet.get("video", {}) or {}
        if video_info.get("status") == "rendered":
            dst_path = video_info.get("path")
            if dst_path and file_exists(dst_path) and not config["force"]:
                logger.info(f"Skipping {story_id} - already rendered")
                skipped_count += 1
                # Probe duration if missing
                if not video_info.get("duration_s"):
                    duration = probe_duration(dst_path)
                    if duration:
                        video_info["duration_s"] = round(duration, 2)
                        changed = True
                continue
        
        # Render video
        try:
            packet_start_time = time.time()
            out_mp4 = render_for_packet(packet, out_dir)
            packet_render_time = (time.time() - packet_start_time) * 1000
            
            # Update packet with video info
            if "video" not in packet:
                packet["video"] = {}
            
            packet["video"]["status"] = "rendered"
            packet["video"]["path"] = out_mp4
            packet["video"]["canvas"] = f"{config['viewport_width']}x{config['viewport_height']}"
            
            # Get duration
            duration = get_video_duration(Path(out_mp4))
            if duration > 0:
                packet["video"]["duration_s"] = duration
            
            changed = True
            rendered_count += 1
            logger.info(f"Rendered video for {story_id}: {out_mp4} ({packet_render_time:.0f}ms)")
            
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to render video for {story_id}: {e}")
            # Mark as failed
            if "video" not in packet:
                packet["video"] = {}
            packet["video"]["status"] = "failed"
            packet["video"]["error"] = str(e)
            changed = True
    
    # Save updated digest if changed
    if changed:
        try:
            with open(digest_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Updated digest: {digest_path}")
        except Exception as e:
            logger.error(f"Failed to save updated digest: {e}")
    
    total_time = (time.time() - start_time) * 1000
    logger.info(f"Render summary: {rendered_count} rendered, {failed_count} failed, {skipped_count} skipped ({total_time:.0f}ms)")
    
    return changed


def main():
    """Main entry point for command line usage."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python -m tools.renderer_html YYYY-MM-DD")
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
    out_dir = Path(f"blogs/{date}")
    
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
