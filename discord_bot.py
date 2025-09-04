import os, asyncio, sys
from typing import Optional
import discord
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timezone
from services.story_state import StoryState
from services.outline import generate_outline
from services.utils import validate_story_id
from services.blog import BlogDigestBuilder
from services.notify import notify_blog_published
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

def _today() -> datetime:
    return datetime.now(timezone.utc)

def _parse_date_str(date: Optional[str]) -> datetime:
    if date:
        return datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return _today()

def _guard_role(interaction: discord.Interaction) -> bool:
    if ROLE_ID == 0:
        return True
    
    # Check if we're in a guild context and user has roles
    if not interaction.guild or not hasattr(interaction.user, 'roles'):
        return False
    
    return any(getattr(r, "id", None) == ROLE_ID for r in interaction.user.roles)

def _guard_channel(interaction: discord.Interaction) -> bool:
    if CONTROL_CHANNEL_ID == 0:
        return True
    return getattr(interaction.channel, "id", None) == CONTROL_CHANNEL_ID

def _validate_story_id(story_id: str) -> bool:
    """
    Validate story_id to prevent path traversal and CLI misuse.
    
    Args:
        story_id: The story ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Use shared validation function
    return validate_story_id(story_id)

def _run_cli_command(args: list[str], timeout: int = 30) -> None:
    """
    Run a CLI command with hardened subprocess settings.
    
    Args:
        args: List of command arguments (excluding the Python interpreter)
        timeout: Timeout in seconds for the subprocess
    
    Raises:
        subprocess.CalledProcessError: If the command fails
        subprocess.TimeoutExpired: If the command times out
        ValueError: If args contains invalid types or nested iterables
    """
    # Validate args is a sequence and not empty
    if not isinstance(args, (list, tuple)) or not args:
        raise ValueError("args must be a non-empty sequence")
    
    # Validate and flatten args to ensure no nested iterables
    try:
        # Convert all args to strings and ensure they're flat
        flat_args = []
        for arg in args:
            # Check if arg is a string or simple type that can be safely converted
            if isinstance(arg, (str, int, float, bool)):
                flat_args.append(str(arg))
            elif isinstance(arg, (list, tuple, dict, set)):
                raise ValueError(f"Nested iterables are not allowed: {type(arg).__name__} = {arg}")
            else:
                # For other types, try to convert but be cautious
                flat_args.append(str(arg))
    except (TypeError, ValueError) as e:
        raise ValueError(f"All arguments must be convertible to strings: {e}")
    
    # Validate module name (first argument should be a valid module)
    if flat_args and not flat_args[0].startswith("cli."):
        raise ValueError(f"Invalid module name: {flat_args[0]}. Only 'cli.*' modules are allowed.")
    
    # Construct command safely
    cmd = [sys.executable, "-m"] + flat_args
    
    # Create environment that preserves required variables for CLI
    env = dict(os.environ)  # Start with full process environment
    
    # Preserve all OBS_*, R2_*, and DISCORD_* variables
    # The CLI (cli.devlog/AuthService) needs these runtime variables
    
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
        logger.error(f"CLI command timed out after {timeout}s: {' '.join(cmd)}", exc_info=True)
        # subprocess.run already handles process termination on timeout
        # No need to manually terminate - just re-raise the exception
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"CLI command failed with return code {e.returncode}: {' '.join(cmd)}")
        if e.stdout:
            logger.error(f"Command stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Command stderr: {e.stderr}")
        raise

async def _run_cli_command_async(args: list[str], timeout: int = 30) -> None:
    """
    Async wrapper for _run_cli_command that runs the blocking operation off the event loop.
    
    Args:
        args: List of command arguments (excluding the Python interpreter)
        timeout: Timeout in seconds for the subprocess
    
    Raises:
        subprocess.CalledProcessError: If the command fails
        subprocess.TimeoutExpired: If the command times out
        ValueError: If args contains invalid types or nested iterables
    """
    return await asyncio.to_thread(_run_cli_command, args, timeout)

@tree.command(name="story_list", description="List story packets for today (by id/title/status)")
async def story_list(interaction: discord.Interaction, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return

    if not _guard_channel(interaction):
        await interaction.response.send_message("Wrong channel for controls.", ephemeral=True)
        return
    
    # Validate and parse date before any processing
    try:
        date_obj = _parse_date_str(date)
    except ValueError as e:
        await interaction.response.send_message(f"Invalid date format. Use YYYY-MM-DD: {e}", ephemeral=True)
        return
    
    try:
        state = StoryState()
        digest, _ = state.load_digest(date_obj)
        rows = []
        for p in digest.get("story_packets", []):
            status = p.get("explainer", {}).get("status", "missing")
            rows.append(f"- `{p['id']}` • **{p.get('title_human', p.get('title_raw'))}** • {status}")
        msg = "\n".join(rows) or "No stories."
        await interaction.response.send_message(msg, ephemeral=True)
    except FileNotFoundError:
        await interaction.response.send_message(f"No digest found for {date_obj.strftime('%Y-%m-%d')}.", ephemeral=True)
    except (KeyError, ValueError) as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)
    except Exception:
        logger.exception("Unexpected error in story_list")
        await interaction.response.send_message("Unexpected error.", ephemeral=True)

@tree.command(name="record_start", description="Start recording for a story id")
async def record_start(interaction: discord.Interaction, story_id: str, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return

    if not _guard_channel(interaction):
        await interaction.response.send_message("Wrong channel for controls.", ephemeral=True)
        return
    
    # Validate story_id before any processing
    if not _validate_story_id(story_id):
        await interaction.response.send_message("Invalid story ID. Use only letters, numbers, hyphens, and underscores (max 50 chars).", ephemeral=True)
        return
    
    # Validate and parse date before deferring
    try:
        date_obj = _parse_date_str(date)
    except ValueError as e:
        await interaction.response.send_message(f"Invalid date format. Use YYYY-MM-DD: {e}", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    try:
        # call CLI (keeps logic centralized) - now async
        await _run_cli_command_async(["cli.devlog", "record", "--story", story_id, "--action", "start", "--date", date_obj.strftime("%Y-%m-%d")])
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

    if not _guard_channel(interaction):
        await interaction.response.send_message("Wrong channel for controls.", ephemeral=True)
        return
    
    # Validate story_id before any processing
    if not _validate_story_id(story_id):
        await interaction.response.send_message("Invalid story ID. Use only letters, numbers, hyphens, and underscores (max 50 chars).", ephemeral=True)
        return
    
    # Validate and parse date before deferring
    try:
        date_obj = _parse_date_str(date)
    except ValueError as e:
        await interaction.response.send_message(f"Invalid date format. Use YYYY-MM-DD: {e}", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    try:
        # call CLI (keeps logic centralized) - now async
        await _run_cli_command_async(["cli.devlog", "record", "--story", story_id, "--action", "stop", "--date", date_obj.strftime("%Y-%m-%d")])
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

    if not _guard_channel(interaction):
        await interaction.response.send_message("Wrong channel for controls.", ephemeral=True)
        return
    
    # Validate story_id before any processing
    if not _validate_story_id(story_id):
        await interaction.response.send_message("Invalid story ID. Use only letters, numbers, hyphens, and underscores (max 50 chars).", ephemeral=True)
        return
    
    # Validate and parse date before any processing
    try:
        date_obj = _parse_date_str(date)
    except ValueError as e:
        await interaction.response.send_message(f"Invalid date format. Use YYYY-MM-DD: {e}", ephemeral=True)
        return
    
    try:
        state = StoryState()
        digest, _ = state.load_digest(date_obj)
        pkt = [p for p in digest.get("story_packets", []) if p.get("id")==story_id]
        if not pkt:
            await interaction.response.send_message("Story not found.", ephemeral=True)
            return
        outline = generate_outline(pkt[0])
        
        # Wrap outline in markdown code block and handle Discord's character limit
        outline_text = f"```markdown\n{outline}\n```"
        
        # Discord has a 2000 character limit, use 1990 for safety
        if len(outline_text) > 1990:
            # Truncate to ~1900 chars and add truncation marker
            max_outline_length = 1900 - len("```markdown\n\n… [truncated]\n```")
            truncated_outline = outline[:max_outline_length] + "\n\n… [truncated]"
            outline_text = f"```markdown\n{truncated_outline}\n```"
        
        await interaction.response.send_message(outline_text, ephemeral=True)
    except FileNotFoundError:
        await interaction.response.send_message(f"No digest found for {date_obj.strftime('%Y-%m-%d')}.", ephemeral=True)
    except (KeyError, ValueError) as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)
    except Exception as e:
        logger.exception("Unexpected error in story_outline")
        await interaction.response.send_message("Unexpected error.", ephemeral=True)

@client.event
async def on_interaction(interaction: discord.Interaction):
    """Handle button interactions for blog approval workflow."""
    if not interaction.type == discord.InteractionType.component:
        return
    
    if not _guard_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    
    custom_id = interaction.data.get("custom_id", "")
    
    try:
        if custom_id.startswith("approve_blog_"):
            # Handle blog approval
            date = custom_id.replace("approve_blog_", "")
            await _handle_blog_approval(interaction, date)
            
        elif custom_id.startswith("edit_blog_"):
            # Handle blog edit request
            date = custom_id.replace("edit_blog_", "")
            await _handle_blog_edit_request(interaction, date)
            
    except Exception as e:
        logger.error(f"Error handling button interaction {custom_id}: {e}")
        await interaction.response.send_message(f"❌ Error processing request: {str(e)}", ephemeral=True)


async def _handle_blog_approval(interaction: discord.Interaction, date: str):
    """Handle blog approval button click."""
    try:
        # Show "processing" message
        await interaction.response.send_message(f"⏳ Processing blog approval for {date}...", ephemeral=True)
        
        # Create FINAL digest using BlogDigestBuilder
        builder = BlogDigestBuilder()
        final_digest = builder.create_final_digest(date)
        
        if final_digest:
            # Send published notification
            if notify_blog_published(date):
                await interaction.followup.send(f"✅ **Blog Approved & Published** — {date}\n\nBlog has been approved and published successfully!", ephemeral=False)
            else:
                await interaction.followup.send(f"✅ **Blog Approved** — {date}\n\nBlog approved but failed to send published notification.", ephemeral=False)
        else:
            await interaction.followup.send(f"❌ **Approval Failed** — {date}\n\nFailed to create FINAL digest. Check logs for details.", ephemeral=False)
            
    except Exception as e:
        logger.error(f"Error approving blog {date}: {e}")
        await interaction.followup.send(f"❌ **Approval Error** — {date}\n\nError: {str(e)}", ephemeral=False)


async def _handle_blog_edit_request(interaction: discord.Interaction, date: str):
    """Handle blog edit request button click."""
    try:
        await interaction.response.send_message(
            f"📝 **Blog Edit Request** — {date}\n\n"
            f"Blog marked as needing edits. You can:\n"
            f"• Edit the PRE-CLEANED digest directly\n"
            f"• Regenerate content using the blog CLI\n"
            f"• Request another review when ready\n\n"
            f"Use: `python tools/blog_cli.py request-approval {date}` when ready for review again.",
            ephemeral=False
        )
    except Exception as e:
        logger.error(f"Error handling edit request for {date}: {e}")
        await interaction.followup.send(f"❌ **Edit Request Error** — {date}\n\nError: {str(e)}", ephemeral=False)


@client.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
    if guild:
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    logger.info("Bot logged in as %s (synced)", client.user)

if __name__ == "__main__":
    if not TOKEN:
        logger.critical("DISCORD_BOT_TOKEN (or legacy DISCORD_TOKEN) missing")
        raise SystemExit(1)
    client.run(TOKEN)
