import os, asyncio
from typing import Optional
import discord
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime
from services.story_state import StoryState
from services.outline import generate_outline
import subprocess

load_dotenv()

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
CONTROL_CHANNEL_ID = int(os.getenv("DISCORD_CONTROL_CHANNEL_ID", "0") or "0")
ROLE_ID = int(os.getenv("DISCORD_CONTROL_ROLE_ID", "0") or "0")
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def _guard_role(interaction: discord.Interaction) -> bool:
    if ROLE_ID == 0:
        return True
    return any(getattr(r, "id", None) == ROLE_ID for r in interaction.user.roles)  # type: ignore[attr-defined]

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
        subprocess.check_call(["python", "-m", "cli.devlog", "record", "--story", story_id, "--action", "start", "--date", date])
        await interaction.followup.send(f"Recording started for `{story_id}`.", ephemeral=True)
    except subprocess.CalledProcessError as e:
        await interaction.followup.send(f"Start failed: {e}", ephemeral=True)

@tree.command(name="record_stop", description="Stop recording for a story id")
async def record_stop(interaction: discord.Interaction, story_id: str, date: Optional[str] = None):
    if not _guard_role(interaction):
        await interaction.response.send_message("Not authorized.", ephemeral=True)
        return
    date = date or _today()
    await interaction.response.defer(ephemeral=True)
    try:
        subprocess.check_call(["python", "-m", "cli.devlog", "record", "--story", story_id, "--action", "stop", "--date", date])
        await interaction.followup.send(f"Recording stopped for `{story_id}`.", ephemeral=True)
    except subprocess.CalledProcessError as e:
        await interaction.followup.send(f"Stop failed: {e}", ephemeral=True)

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
        raise SystemExit("DISCORD_BOT_TOKEN missing")
    client.run(TOKEN)
