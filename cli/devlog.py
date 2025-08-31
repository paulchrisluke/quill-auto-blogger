import click, os
from datetime import datetime, timezone
from services.obs_controller import OBSController
from services.story_state import StoryState

def _today(date: datetime | None) -> datetime:
    return date or datetime.now(timezone.utc)

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
        obs = OBSController()
    except Exception as e:
        click.echo(f"[ERR] OBS initialization failed: {e}")
        raise SystemExit(1)
    
    state = StoryState()

    if action == "start":
        res = obs.start_recording()
        if not res.ok:
            click.echo(f"[ERR] {res.error}")
            raise SystemExit(1)
        
        # Handle state.begin_recording errors
        try:
            state.begin_recording(date, story_id)
        except (FileNotFoundError, KeyError) as e:
            click.echo(f"[ERR] Failed to begin recording for story {story_id}: {e}")
            raise SystemExit(1)
        
        click.echo(f"[OK] recording started for {story_id}")
    else:
        res = obs.stop_recording()
        if not res.ok:
            click.echo(f"[ERR] {res.error}")
            raise SystemExit(1)
        
        # Handle state.end_recording errors
        try:
            state.end_recording(date, story_id)
        except (FileNotFoundError, KeyError) as e:
            click.echo(f"[ERR] Failed to end recording for story {story_id}: {e}")
            raise SystemExit(1)
        
        click.echo(f"[OK] recording stopped for {story_id}")

if __name__ == "__main__":
    devlog()
