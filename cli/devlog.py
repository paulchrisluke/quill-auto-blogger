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
    obs = OBSController()
    state = StoryState()

    if action == "start":
        res = obs.start_recording()
        if not res.ok:
            click.echo(f"[ERR] {res.error}")
            raise SystemExit(1)
        state.begin_recording(date, story_id)
        click.echo(f"[OK] recording started for {story_id}")
    else:
        res = obs.stop_recording()
        if not res.ok:
            click.echo(f"[ERR] {res.error}")
            raise SystemExit(1)
        # raw path capture is optional; OBS saves to its configured dir
        state.end_recording(date, story_id)
        click.echo(f"[OK] recording stopped for {story_id}")

if __name__ == "__main__":
    devlog()
