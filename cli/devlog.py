import click, os
from datetime import datetime, timezone
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
    
    # Run the bounded recording
    try:
        import asyncio
        result = asyncio.run(obs.record_bounded(story_id, prep_delay, duration))
        if not result.ok:
            click.echo(f"[ERR] Bounded recording failed: {result.error}")
            raise SystemExit(1)
    except Exception as e:
        click.echo(f"[ERR] Bounded recording failed: {e}")
        raise SystemExit(1) from e
    
    # Complete the bounded recording state
    try:
        state.complete_bounded_recording(date, story_id, duration, assume_utc=True)
        click.echo(f"[OK] Bounded recording completed for {story_id} ({duration}s)")
    except Exception as e:
        click.echo(f"[ERR] Failed to complete bounded recording for story {story_id}: {e}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    devlog()
