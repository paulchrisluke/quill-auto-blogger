import os, asyncio, sys
from typing import Optional
import discord
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime
from services.story_state import StoryState
from services.outline import generate_outline
import subprocess
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
CONTROL_CHANNEL_ID = int(os.getenv("DISCORD_CONTROL_CHANNEL_ID", "0") or "0")
ROLE_ID = int(os.getenv("DISCORD_CONTROL_ROLE_ID", "0") or "0")

# Use DISCORD_BOT_TOKEN with fallback to legacy DISCORD_TOKEN
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        import warnings
        warnings.warn(
            "DISCORD_TOKEN is deprecated and will be removed in a future version. "
            "Please use DISCORD_BOT_TOKEN instead.",
            DeprecationWarning,
            stacklevel=2
        )

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def _guard_role(interaction: discord.Interaction) -> bool:
    if ROLE_ID == 0:
        return True
    return any(getattr(r, "id", None) == ROLE_ID for r in interaction.user.roles)  # type: ignore[attr-defined]

def _run_cli_command(args: list[str], timeout: int = 30) -> None:
    """
    Run a CLI command with hardened subprocess settings.
    
    Args:
        args: List of command arguments (excluding the Python interpreter)
        timeout: Timeout in seconds for the subprocess
    
    Raises:
        subprocess.CalledProcessError: If the command fails
        subprocess.TimeoutExpired: If the command times out
    """
    # Use sys.executable to get the current Python interpreter path
    cmd = [sys.executable, "-m"] + args
    
    # Create minimal sanitized environment
    env = {
        'PATH': os.environ.get('PATH', ''),
        'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
        'HOME': os.environ.get('HOME', ''),
        'USER': os.environ.get('USER', ''),
    }
    
    try:
        logger.info(f"Running CLI command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            timeout=timeout,
            shell=False,  # Explicitly avoid shell=True
            close_fds=True,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"CLI command completed successfully: {' '.join(cmd)}")
        if result.stdout:
            logger.debug(f"Command stdout: {result.stdout}")
        if result.stderr:
            logger.debug(f"Command stderr: {result.stderr}")
            
    except subprocess.TimeoutExpired as e:
        logger.error(f"CLI command timed out after {timeout}s: {' '.join(cmd)}")
        # Attempt to terminate the process if it's still running
        if hasattr(e, 'process') and e.process:
            try:
                e.process.terminate()
                e.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate gracefully, killing it")
                e.process.kill()
                e.process.wait()
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"CLI command failed with return code {e.returncode}: {' '.join(cmd)}")
        if e.stdout:
            logger.error(f"Command stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Command stderr: {e.stderr}")
        raise

@tree.command(name="story_list", description="List story packets for today (by id/title/status)")
async def story_list(interaction: discord.Interaction, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return
    date = date or _today()
    try:
        state = StoryState()
        digest = state._load_digest(date)
        rows = []
        for p in digest.get("story_packets", []):
            status = p.get("explainer", {}).get("status", "missing")
            rows.append(f"- `{p['id']}` • **{p.get('title_human', p.get('title_raw'))}** • {status}")
        msg = "\n".join(rows) or "No stories."
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@tree.command(name="record_start", description="Start recording for a story id")
async def record_start(interaction: discord.Interaction, story_id: str, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return
    date = date or _today()
    await interaction.response.defer(ephemeral=True)
    try:
        # call CLI (keeps logic centralized)
        _run_cli_command(["cli.devlog", "record", "--story", story_id, "--action", "start", "--date", date])
        await interaction.followup.send(f"Recording started for `{story_id}`.", ephemeral=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_msg = f"Start failed: {type(e).__name__}"
        if isinstance(e, subprocess.CalledProcessError):
            error_msg += f" (exit code: {e.returncode})"
        elif isinstance(e, subprocess.TimeoutExpired):
            error_msg += " (timeout)"
        logger.error(f"Record start failed for story {story_id}: {e}")
        await interaction.followup.send(error_msg, ephemeral=True)

@tree.command(name="record_stop", description="Stop recording for a story id")
async def record_stop(interaction: discord.Interaction, story_id: str, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return
    date = date or _today()
    await interaction.response.defer(ephemeral=True)
    try:
        _run_cli_command(["cli.devlog", "record", "--story", story_id, "--action", "stop", "--date", date])
        await interaction.followup.send(f"Recording stopped for `{story_id}`.", ephemeral=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_msg = f"Stop failed: {type(e).__name__}"
        if isinstance(e, subprocess.CalledProcessError):
            error_msg += f" (exit code: {e.returncode})"
        elif isinstance(e, subprocess.TimeoutExpired):
            error_msg += " (timeout)"
        logger.error(f"Record stop failed for story {story_id}: {e}")
        await interaction.followup.send(error_msg, ephemeral=True)

@tree.command(name="story_outline", description="Generate quick outline for story id")
async def story_outline(interaction: discord.Interaction, story_id: str, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return
    date = date or _today()
    try:
        state = StoryState()
        digest = state._load_digest(date)
        pkt = [p for p in digest.get("story_packets", []) if p.get("id")==story_id]
        if not pkt:
            await interaction.response.send_message("Story not found.", ephemeral=True)
            return
        outline = generate_outline(pkt[0])
        await interaction.response.send_message(f"```markdown\n{outline}\n```", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@client.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
    if guild:
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    print(f"Bot logged in as {client.user} (synced)")

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN (or legacy DISCORD_TOKEN) missing")
    client.run(TOKEN)
