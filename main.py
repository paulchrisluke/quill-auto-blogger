#!/usr/bin/env python3
"""
Main CLI entrypoint for the activity fetcher.
"""

import click
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from services.twitch import TwitchService
from services.github import GitHubService
from services.auth import AuthService
from services.utils import CacheManager
from services.blog import BlogDigestBuilder

# Load environment variables
load_dotenv()

@click.group()
def cli():
    """Activity Fetcher - Fetch and transcribe Twitch clips and GitHub activity."""
    pass

@cli.command()
@click.option('--broadcaster', default=None, help='Twitch broadcaster username or ID')
@click.option('--broadcaster-id', default=None, help='Twitch broadcaster ID (numeric)')
def fetch_twitch(broadcaster, broadcaster_id):
    """Fetch and transcribe recent Twitch clips."""
    click.echo("Fetching Twitch clips...")
    
    # Get broadcaster from env or parameters
    broadcaster = broadcaster or broadcaster_id or os.getenv('TWITCH_BROADCASTER_ID')
    if not broadcaster:
        click.echo("Error: No broadcaster specified. Set TWITCH_BROADCASTER_ID in .env or use --broadcaster or --broadcaster-id")
        return
    
    try:
        twitch_service = TwitchService()
        
        # If it looks like a numeric ID, use it directly
        if broadcaster.isdigit():
            clips = twitch_service.fetch_clips_by_broadcaster_id(broadcaster)
        else:
            # Otherwise treat as username
            clips = twitch_service.fetch_clips_by_username(broadcaster)
        
        click.echo(f"Fetched {len(clips)} clips")
        
        for clip in clips:
            click.echo(f"Processing clip: {clip.title}")
            twitch_service.process_clip(clip)
            
    except Exception as e:
        click.echo(f"Error fetching Twitch clips: {e}")

@cli.command()
@click.option('--user', default=None, help='GitHub username')
@click.option('--repo', default=None, help='GitHub repository (owner/repo)')
def fetch_github(user, repo):
    """Fetch recent GitHub activity."""
    click.echo("Fetching GitHub activity...")
    
    # Get user/repo from env or parameters
    user = user or os.getenv('GITHUB_USER')
    repo = repo or os.getenv('GITHUB_REPO')
    
    if not user and not repo:
        click.echo("Error: No user or repo specified. Set GITHUB_USER or GITHUB_REPO in .env or use --user/--repo")
        return
    
    try:
        github_service = GitHubService()
        
        if user:
            events = github_service.fetch_user_activity(user)
            click.echo(f"Fetched {len(events)} events for user {user}")
        else:
            events = github_service.fetch_repo_activity(repo)
            click.echo(f"Fetched {len(events)} events for repo {repo}")
            
        for event in events:
            click.echo(f"Processing event: {event.type} in {event.repo}")
            github_service.save_event(event)
            
    except Exception as e:
        click.echo(f"Error fetching GitHub activity: {e}")

@cli.command()
@click.option('--broadcaster', default=None, help='Twitch broadcaster username or ID')
@click.option('--broadcaster-id', default=None, help='Twitch broadcaster ID (numeric)')
@click.option('--user', default=None, help='GitHub username')
@click.option('--repo', default=None, help='GitHub repository (owner/repo)')
def sync_all(broadcaster, broadcaster_id, user, repo):
    """Run both Twitch and GitHub fetchers."""
    click.echo("Running full sync...")
    
    # Run Twitch fetch
    fetch_twitch.callback(broadcaster, broadcaster_id)
    
    # Run GitHub fetch
    fetch_github.callback(user, repo)
    
    click.echo("Sync completed!")

@cli.command()
def validate_auth():
    """Validate Twitch and GitHub authentication."""
    click.echo("Validating authentication...")
    
    try:
        auth_service = AuthService()
        
        # Validate Twitch
        twitch_valid = auth_service.validate_twitch_auth()
        if twitch_valid:
            click.echo("✅ Twitch authentication valid")
        else:
            click.echo("❌ Twitch authentication failed")
        
        # Validate GitHub
        github_valid = auth_service.validate_github_auth()
        if github_valid:
            click.echo("✅ GitHub authentication valid")
        else:
            click.echo("❌ GitHub authentication failed")
            
    except Exception as e:
        click.echo(f"Error validating auth: {e}")

@cli.command()
def setup_github_token():
    """Initialize GitHub token from environment variable."""
    click.echo("Setting up GitHub token...")
    
    try:
        auth_service = AuthService()
        
        if not auth_service.github_token:
            click.echo("❌ No GitHub token found in environment variables")
            return
        
        success = auth_service.initialize_github_token_from_env()
        if success:
            click.echo("✅ GitHub token initialized successfully")
            click.echo("⚠️  Note: Fine-grained tokens expire. Update your token when needed.")
        else:
            click.echo("❌ Failed to initialize GitHub token")
            
    except Exception as e:
        click.echo(f"Error setting up GitHub token: {e}")

@cli.command()
@click.argument('username')
def get_broadcaster_id(username):
    """Get Twitch broadcaster ID from username."""
    click.echo(f"Looking up broadcaster ID for: {username}")
    
    try:
        twitch_service = TwitchService()
        broadcaster_id = twitch_service.get_user_id(username)
        
        if broadcaster_id:
            click.echo(f"✅ Broadcaster ID: {broadcaster_id}")
            click.echo(f"Add to your .env file: TWITCH_BROADCASTER_ID={broadcaster_id}")
        else:
            click.echo(f"❌ Could not find broadcaster ID for username: {username}")
            
    except Exception as e:
        click.echo(f"Error looking up broadcaster ID: {e}")

@cli.command()
def clear_cache():
    """Clear local cache and seen IDs."""
    click.echo("Clearing cache...")
    
    try:
        cache_manager = CacheManager()
        cache_manager.clear_cache()
        click.echo("Cache cleared successfully!")
    except Exception as e:
        click.echo(f"Error clearing cache: {e}")

@cli.command()
@click.option('--date', default=None, help='Date in YYYY-MM-DD format (defaults to latest)')
def build_digest(date):
    """Build a digest for a specific date or the latest available date."""
    click.echo("Building digest...")
    
    try:
        builder = BlogDigestBuilder()
        
        if date:
            digest = builder.build_digest(date)
            click.echo(f"Building digest for {date}")
        else:
            digest = builder.build_latest_digest()
            click.echo(f"Building digest for latest date: {digest['date']}")
        
        # Generate markdown content
        markdown_content = builder.generate_markdown(digest)
        
        # Save files
        md_path = builder.save_digest(digest, markdown_content)
        
        click.echo(f"✅ Digest built successfully!")
        click.echo(f"📄 Markdown saved to: {md_path}")
        click.echo(f"📊 Summary: {digest['metadata']['total_clips']} clips, {digest['metadata']['total_events']} events")
        
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
    except Exception as e:
        click.echo(f"Error building digest: {e}")

@cli.command()
@click.argument('date', required=True)
def build_digest_for_date(date):
    """Build a digest for a specific date."""
    build_digest.callback(date)

@cli.command()
def build_latest_digest():
    """Build digest for the most recent date with data."""
    build_digest.callback(None)

if __name__ == '__main__':
    cli()
