import click, os
from datetime import datetime, timezone
from pathlib import Path
from services.story_state import StoryState

def _today(date: datetime | None) -> datetime:
    if date is None:
        return datetime.now(timezone.utc)
    elif date.tzinfo is None:
        return date.replace(tzinfo=timezone.utc)
    else:
        return date.astimezone(timezone.utc)

@click.group()
def devlog():
    """Devlog utilities."""
    pass

@devlog.command("record")
@click.option("--story", "story_id", required=True)
@click.option("--action", type=click.Choice(["start", "stop"]), required=True)
@click.option("--date", type=click.DateTime(formats=["%Y-%m-%d"]), required=False)
def record(story_id: str, action: str, date: datetime | None):
    """Start/stop OBS recording and persist story state."""
    date = _today(date)
    
    # Initialize OBSController with error handling
    try:
        from services.obs_controller import OBSController
        obs = OBSController()
    except Exception as e:
        click.echo(f"[ERR] OBS initialization failed: {e}")
        raise SystemExit(1) from e
    
    state = StoryState()

    if action == "start":
        res = obs.start_recording()
        if not res.ok:
            click.echo(f"[ERR] {res.error}")
            raise SystemExit(1)
        
        # Handle state.begin_recording errors with OBS cleanup
        try:
            state.begin_recording(date, story_id, assume_utc=True)
        except Exception as e:
            click.echo(f"[ERR] Failed to begin recording for story {story_id}: {e}")
            # Rollback: stop OBS recording to prevent orphaned recording
            try:
                cleanup_res = obs.stop_recording()
                if not cleanup_res.ok:
                    click.echo(f"[WARN] Failed to cleanup OBS recording: {cleanup_res.error}")
                else:
                    click.echo(f"[INFO] OBS recording stopped during cleanup")
            except Exception as cleanup_error:
                click.echo(f"[WARN] OBS cleanup failed: {cleanup_error}")
            raise SystemExit(1) from e
        
        click.echo(f"[OK] recording started for {story_id}")
    else:
        res = obs.stop_recording()
        if not res.ok:
            click.echo(f"[ERR] {res.error}")
            raise SystemExit(1)
        
        # Handle state.end_recording errors
        try:
            state.end_recording(date, story_id, assume_utc=True)
        except (FileNotFoundError, KeyError) as e:
            click.echo(f"[ERR] Failed to end recording for story {story_id}: {e}")
            raise SystemExit(1)
        
        click.echo(f"[OK] recording stopped for {story_id}")

@devlog.command("bounded")
@click.option("--id", "story_id", required=True, help="Story ID to record")
@click.option("--date", type=click.DateTime(formats=["%Y-%m-%d"]), required=False, help="Date for the story")
def record_bounded(story_id: str, date: datetime | None):
    """Record for a bounded duration with auto-stop."""
    date = _today(date)
    
    # Get environment variables for timing
    try:
        prep_delay = int(os.getenv("RECORDING_PREP_DELAY", "5"))
        duration = int(os.getenv("RECORDING_DURATION", "15"))
    except ValueError as e:
        click.echo(f"[ERR] Invalid RECORDING_PREP_DELAY or RECORDING_DURATION: {e}")
        raise SystemExit(1) from e
    if prep_delay < 0 or duration <= 0:
        click.echo("[ERR] prep_delay must be >= 0 and duration must be > 0")
        raise SystemExit(1)
    
    click.echo(f"[INFO] Starting bounded recording for {story_id}")
    click.echo(f"[INFO] Prep delay: {prep_delay}s, Duration: {duration}s")
    
    # Initialize OBSController with error handling
    try:
        from services.obs_controller import OBSController
        obs = OBSController()
    except Exception as e:
        click.echo(f"[ERR] OBS initialization failed: {e}")
        raise SystemExit(1) from e
    
    state = StoryState()
    
    # Begin recording state
    try:
        state.begin_recording(date, story_id, assume_utc=True)
    except Exception as e:
        click.echo(f"[ERR] Failed to begin recording for story {story_id}: {e}")
        raise SystemExit(1) from e
    
    # Run the bounded recording; cleanup is guarded by started_by_us, and state mutations happen based on success/failure
    try:
        import asyncio
        result = asyncio.run(obs.record_bounded(story_id, prep_delay, duration))
    except Exception as e:
        # On unexpected exception, try to fail the story without altering OBS state here
        click.echo(f"[ERR] Bounded recording failed: {e}")
        try:
            state.fail_recording(date, story_id, reason=str(e), assume_utc=True)
        except Exception as fail_err:
            click.echo(f"[WARN] Failed to mark recording as failed: {fail_err}")
        raise SystemExit(1) from e

    # Decide actions based on result
    started_by_us = bool(getattr(result, 'started_by_us', False))
    if not result.ok:
        click.echo(f"[ERR] Bounded recording failed: {result.error}")
        # Stop OBS only if we started it
        if started_by_us:
            try:
                stop_res = obs.stop_recording()
                if not stop_res.ok:
                    click.echo(f"[WARN] OBS stop during failure cleanup: {stop_res.error}")
            except Exception as cleanup_error:
                click.echo(f"[WARN] OBS stop recording failed during cleanup: {cleanup_error}")
        # Mark story failure; avoid calling end_recording here
        try:
            state.fail_recording(date, story_id, reason=result.error or "unknown error", assume_utc=True)
        except Exception as fail_err:
            click.echo(f"[WARN] Failed to mark recording as failed: {fail_err}")
        raise SystemExit(1)
    
    # Success path: only finalize if we started the recording
    if started_by_us:
        try:
            state.complete_bounded_recording(date, story_id, duration, assume_utc=True)
            click.echo(f"[OK] Bounded recording completed for {story_id} ({duration}s)")
        except Exception as e:
            click.echo(f"[ERR] Failed to complete bounded recording for story {story_id}: {e}")
            # Mark as failed instead of recorded when completion fails
            try:
                state.fail_recording(date, story_id, reason=f"State finalization failed: {e}", assume_utc=True)
                click.echo(f"[INFO] Recording marked as failed for {story_id}")
            except Exception as cleanup_error:
                click.echo(f"[WARN] Failed to mark recording as failed: {cleanup_error}")
            raise SystemExit(1) from e
    else:
        click.echo(f"[INFO] Bounded recording succeeded but did not finalize state for {story_id} (recording was already active)")


@devlog.group()
def blog():
    """Blog generation commands."""
    pass


@blog.command("generate")
@click.option("--date", "target_date", help="Date in YYYY-MM-DD format (defaults to latest)")
@click.option("--no-ai", is_flag=True, help="Skip AI-assisted content generation")
@click.option("--force-ai", is_flag=True, help="Ignore cache and force AI regeneration")
@click.option("--no-related", is_flag=True, help="Skip related posts block")
@click.option("--no-jsonld", is_flag=True, help="Skip JSON-LD injection")
def blog_generate(target_date: str, no_ai: bool, force_ai: bool, no_related: bool, no_jsonld: bool):
    """Generate markdown blog post for a specific date."""
    try:
        from services.blog import BlogDigestBuilder
        
        # Initialize blog builder
        builder = BlogDigestBuilder()
        
        # Determine target date
        if target_date:
            # Validate date format
            try:
                datetime.strptime(target_date, "%Y-%m-%d")
            except ValueError:
                click.echo(f"[ERR] Invalid date format: {target_date}. Use YYYY-MM-DD")
                raise SystemExit(1)
        else:
            # Use latest date
            digest = builder.build_latest_digest()
            target_date = digest["date"]
            click.echo(f"[INFO] Using latest date: {target_date}")
        
        # Build digest and generate markdown
        digest = builder.build_digest(target_date)
        

        
        # Save PRE-CLEANED digest (raw, no AI enhancements)
        digest_path = builder.save_digest(digest)
        click.echo(f"[OK] Saved PRE-CLEANED digest: {digest_path}")
        
        # Create FINAL digest with AI enhancements for API consumption
        final_digest = builder.create_final_digest(target_date)
        if final_digest:
            click.echo(f"[OK] Created FINAL digest with AI enhancements")
        else:
            click.echo(f"[ERROR] Failed to create FINAL digest")
        
        # Generate markdown with M5 options (for human readability)
        ai_options = {
            "ai_enabled": not no_ai,
            "force_ai": force_ai,
            "related_enabled": not no_related,
            "jsonld_enabled": not no_jsonld
        }
        
        markdown = builder.generate_markdown(digest, **ai_options)
        
        # Save to drafts
        file_path = builder.save_markdown(target_date, markdown)
        
        click.echo(f"[OK] Generated blog post: {file_path}")
        click.echo(f"[INFO] Title: {digest['frontmatter']['title']}")
        click.echo(f"[INFO] Stories: {len(digest.get('story_packets', []))}")
        click.echo(f"[INFO] Schema data included in digest for API consumption")
        
    except Exception as e:
        click.echo(f"[ERR] Failed to generate blog post: {e}")
        raise SystemExit(1)





@blog.command("preview")
@click.option("--date", "target_date", required=True, help="Date in YYYY-MM-DD format")
def blog_preview(target_date: str):
    """Preview blog post content."""
    try:
        from services.blog import BlogDigestBuilder
        
        # Initialize blog builder
        builder = BlogDigestBuilder()
        
        # Build digest and generate markdown
        digest = builder.build_digest(target_date)
        markdown = builder.generate_markdown(digest)
        
        # Extract title from frontmatter
        title = digest['frontmatter']['title']
        
        # Get first ~10 lines of content (skip frontmatter)
        lines = markdown.split('\n')
        content_start = 0
        
        # Find first '---' marker
        first_dash = -1
        for i, line in enumerate(lines):
            if line.strip() == '---':
                first_dash = i
                break
        
        if first_dash != -1:
            # Find second '---' marker
            second_dash = -1
            for i in range(first_dash + 1, len(lines)):
                if lines[i].strip() == '---':
                    second_dash = i
                    break
            
            if second_dash != -1:
                # Set content_start to line after second '---'
                content_start = second_dash + 1
            else:
                # Only one '---' found, treat everything after first as content
                content_start = first_dash + 1
        # If no '---' found, treat whole markdown as body
        
        content_lines = lines[content_start:]
        # Find first non-empty line after frontmatter
        first_content_line = 0
        for i, line in enumerate(content_lines):
            if line.strip():
                first_content_line = i
                break
        
        # Get preview lines starting from first non-empty content line
        preview_lines = content_lines[first_content_line:first_content_line + 10]
        
        # Display preview
        click.echo(f"Title: {title}")
        click.echo(f"Date: {target_date}")
        click.echo(f"Tags: {', '.join(digest['frontmatter'].get('tags', []))}")
        click.echo()
        click.echo("Preview:")
        for line in preview_lines:
            if line.strip():
                click.echo(f"  {line}")
        
    except Exception as e:
        click.echo(f"[ERR] Failed to preview blog post: {e}")
        raise SystemExit(1)


@blog.command("regenerate-api")
@click.option("--date", "target_date", required=True, help="Date in YYYY-MM-DD format")
def blog_regenerate_api(target_date: str):
    """Regenerate API v3 content for a specific date."""
    try:
        from services.blog import BlogDigestBuilder
        
        # Initialize blog builder
        builder = BlogDigestBuilder()
        
        # Regenerate API v3 content
        api_data = builder.get_blog_api_data(target_date)
        
        click.echo(f"[OK] Regenerated API v3 content for {target_date}")
        click.echo(f"[INFO] Title: {api_data['frontmatter']['title']}")
        story_packets = api_data.get('story_packets', [])
        click.echo(f"[INFO] Stories: {len(story_packets)}")
        click.echo(f"[INFO] API v3 file saved to blogs/{target_date}/API-v3-{target_date}_digest.json")
        
    except Exception as e:
        click.echo(f"[ERR] Failed to regenerate API v3 content: {e}")
        raise SystemExit(1)


@devlog.group("site")
def site():
    """Static site building and publishing commands."""
    pass


@site.command("build")
def site_build():
    """Build out/site/{index.html, docs.html}."""
    try:
        from services.site_builder import SiteBuilder
        
        builder = SiteBuilder()
        results = builder.build()
        
        # Display results
        click.echo("[INFO] Site build completed:")
        for filename, success in results.items():
            status = "✓" if success else "✗"
            click.echo(f"  {status} {filename}")
        
        if all(results.values()):
            click.echo("[OK] All site files built successfully")
        else:
            click.echo("[WARN] Some site files failed to build")
            raise SystemExit(1)
            
    except Exception as e:
        click.echo(f"[ERR] Site build failed: {e}")
        raise SystemExit(1)


@site.command("publish")
@click.option("--dry-run", is_flag=True, help="List actions without uploading.")
def site_publish(dry_run):
    """Publish out/site/ files and blogs/*/API-v3-*_digest.json to R2 with idempotency."""
    try:
        from services.publisher_r2 import R2Publisher
        from pathlib import Path
        
        # Check if out/site/ exists
        site_dir = Path("out/site")
        if not site_dir.exists():
            click.echo("[ERR] Site directory not found. Run 'devlog site build' first.")
            raise SystemExit(1)
        
        # Check if site files exist
        site_files = list(site_dir.glob("*.html"))
        if not site_files:
            click.echo("[ERR] No HTML files found in out/site/. Run 'devlog site build' first.")
            raise SystemExit(1)
        
        if dry_run:
            click.echo("[INFO] DRY RUN - No files will be uploaded")
            click.echo(f"[INFO] Site files to check: {[f.name for f in site_files]}")
            
            # Check blogs directory
            blogs_dir = Path("blogs")
            if blogs_dir.exists():
                api_v3_files = list(blogs_dir.rglob("API-v3-*_digest.json"))
                click.echo(f"[INFO] API-v3 files to check: {len(api_v3_files)}")
                for f in api_v3_files[:5]:  # Show first 5
                    click.echo(f"  - {f}")
                if len(api_v3_files) > 5:
                    click.echo(f"  ... and {len(api_v3_files) - 5} more")
            else:
                click.echo("[INFO] No blogs directory found")
            
            return
        
        # Initialize publisher
        publisher = R2Publisher()
        
        # Publish site files
        click.echo("[INFO] Publishing site files...")
        site_results = publisher.publish_site(site_dir)
        
        # Publish blog JSON files
        click.echo("[INFO] Publishing blog JSON files...")
        blogs_dir = Path("blogs")
        blog_results = publisher.publish_blogs(blogs_dir)
        
        # Display results
        click.echo("\n[INFO] Site publishing results:")
        for filename, success in site_results.items():
            status = "✓" if success else "✗"
            click.echo(f"  {status} {filename}")
        
        click.echo("\n[INFO] Blog publishing results:")
        for filename, success in blog_results.items():
            status = "✓" if success else "✗"
            click.echo(f"  {status} {filename}")
        
        # Check overall success
        all_site_success = all(site_results.values()) if site_results else False
        all_blog_success = True if not blog_results else all(blog_results.values())
        
        if all_site_success and all_blog_success:
            click.echo("[OK] All files published successfully")
        else:
            click.echo("[WARN] Some files failed to publish")
            if not all_site_success:
                click.echo("[ERR] Site publishing had failures")
            if not all_blog_success:
                click.echo("[ERR] Blog publishing had failures")
            raise SystemExit(1)
            
    except Exception as e:
        click.echo(f"[ERR] Site publishing failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    devlog()
