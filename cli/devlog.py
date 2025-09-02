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
    """Blog generation and publishing commands."""
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
        
        # Generate markdown with M5 options
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
        
    except Exception as e:
        click.echo(f"[ERR] Failed to generate blog post: {e}")
        raise SystemExit(1)


@blog.command("publish")
@click.option("--date", "target_date", required=True, help="Date in YYYY-MM-DD format")
@click.option("--branch", default="main", help="Target branch (default: main)")
@click.option("--pr", "create_pr", is_flag=True, help="Create pull request")
@click.option("--use-draft", is_flag=True, help="Use existing draft file instead of regenerating")
def blog_publish(target_date: str, branch: str, create_pr: bool, use_draft: bool):
    """Publish blog post to GitHub repository."""
    try:
        from services.blog import BlogDigestBuilder
        from services.github_publisher import publish_markdown
        
        # Get environment variables
        target_repo = os.getenv("BLOG_TARGET_REPO")
        if not target_repo:
            click.echo("[ERR] BLOG_TARGET_REPO environment variable is required")
            raise SystemExit(1)
        
        # Parse owner/repo from BLOG_TARGET_REPO
        if "/" not in target_repo:
            click.echo("[ERR] BLOG_TARGET_REPO must be in format 'owner/repo'")
            raise SystemExit(1)
        
        owner, repo = target_repo.split("/", 1)
        
        # Get author info
        author_name = os.getenv("BLOG_AUTHOR_NAME")
        author_email = os.getenv("BLOG_AUTHOR_EMAIL")
        
        # Initialize blog builder
        builder = BlogDigestBuilder()
        
        # Get markdown content
        if use_draft:
            # Use existing draft file
            draft_path = Path("drafts") / f"{target_date}.md"
            if not draft_path.exists():
                click.echo(f"[ERR] Draft file not found: {draft_path}")
                raise SystemExit(1)
            
            with open(draft_path, 'r', encoding='utf-8') as f:
                markdown = f.read()
            
            click.echo(f"[INFO] Using existing draft: {draft_path}")
        else:
            # Generate fresh markdown
            digest = builder.build_digest(target_date)
            markdown = builder.generate_markdown(digest)
            click.echo(f"[INFO] Generated fresh markdown for {target_date}")
        
        # Compute target path
        target_path = builder.compute_target_path(target_date)
        
        # Prepare commit message
        commit_message = f"Add daily devlog for {target_date}"
        
        # Prepare PR info if creating PR
        pr_title = None
        pr_body = None
        if create_pr:
            pr_title = f"Daily Devlog — {target_date}"
            pr_body = f"Automated blog post for {target_date}"
        
        # Collect assets for publishing if creating PR
        assets_info = None
        if create_pr:
            assets_info = builder.collect_assets_for_publishing(target_date)
            if assets_info:
                click.echo(f"[INFO] Found {len(assets_info)} assets to publish")
            else:
                click.echo("[INFO] No assets found for publishing")
        
        # Publish to GitHub
        result = publish_markdown(
            owner=owner,
            repo=repo,
            branch=branch,
            path=target_path,
            content_md=markdown,
            commit_message=commit_message,
            author_name=author_name,
            author_email=author_email,
            create_pr=create_pr,
            pr_title=pr_title,
            pr_body=pr_body,
            include_assets=create_pr,  # Include assets when creating PR
            assets_info=assets_info
        )
        
        # Display results
        action = result["action"]
        if action == "skipped":
            click.echo(f"[INFO] No changes needed - content is identical")
        else:
            click.echo(f"[OK] Blog {action}: {result['html_url']}")
            
            if result.get("pr_url"):
                click.echo(f"[OK] Pull request created: {result['pr_url']}")
        
        # Send Discord notification
        if action != "skipped":
            _send_discord_notification(target_date, action, result)
        
    except Exception as e:
        click.echo(f"[ERR] Failed to publish blog post: {e}")
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


def _send_discord_notification(target_date: str, action: str, result: dict):
    """Send Discord notification about blog publishing."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    
    try:
        import httpx
        
        # Prepare message
        if action == "created":
            title = "Blog published"
        elif action == "updated":
            title = "Blog updated"
        else:
            title = "Blog action completed"
        
        message = f"**{title}**\n"
        message += f"**Date:** {target_date}\n"
        message += f"**Action:** {action}\n"
        message += f"**Link:** {result['html_url']}"
        
        if result.get("pr_url"):
            message += f"\n**PR:** {result['pr_url']}"
        
        # Send webhook
        with httpx.Client(timeout=5) as client:
            client.post(
                webhook_url,
                json={
                    "content": message,
                    "allowed_mentions": {"parse": []}
                }
            )
        
        click.echo(f"[INFO] Discord notification sent")
        
    except Exception as e:
        click.echo(f"[WARN] Failed to send Discord notification: {e}")


if __name__ == "__main__":
    devlog()
