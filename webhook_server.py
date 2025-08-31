#!/usr/bin/env python3
"""
FastAPI webhook server for GitHub PR merge events.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import hmac
import hashlib

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from services.blog import BlogDigestBuilder
from story_schema import StoryPacket, make_story_packet, pair_with_clip

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Story Pipeline Webhook Server", version="1.0.0")

# Configuration
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
STORY_DIR = Path("./story_packets")
STORY_DIR.mkdir(parents=True, exist_ok=True)


class GitHubWebhookPayload(BaseModel):
    """GitHub webhook payload model."""
    action: Optional[str] = None
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None


async def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not WEBHOOK_SECRET:
        logger.warning("No webhook secret configured, skipping verification")
        return True
    
    if not signature:
        logger.error("No signature header found")
        return False
    
    # Calculate expected signature
    expected_signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


@app.post("/webhook/github")
async def github_webhook(request: Request):
    """Handle GitHub webhook events."""
    
    # Get raw body for signature verification
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    
    # Verify signature
    if not await verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse the JSON payload
    try:
        payload_data = json.loads(raw_body.decode('utf-8'))
        payload = GitHubWebhookPayload(**payload_data)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Check if this is a PR merge event
    if (payload.action == "closed" and 
        payload.pull_request and 
        payload.pull_request.get("merged") is True):
        
        logger.info(f"PR #{payload.pull_request['number']} merged")
        
        try:
            # Generate story packet immediately
            story_packet = await generate_story_packet_from_pr(payload)
            
            # Save story packet
            await save_story_packet(story_packet)
            
            logger.info(f"Story packet generated: {story_packet.id}")
            
            return JSONResponse({
                "status": "success",
                "message": "Story packet generated",
                "story_id": story_packet.id,
                "pr_number": story_packet.pr_number
            })
            
        except Exception as e:
            logger.error(f"Error generating story packet: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return JSONResponse({"status": "ignored", "message": "Not a PR merge event"})


async def generate_story_packet_from_pr(payload: GitHubWebhookPayload) -> StoryPacket:
    """Generate a story packet from a merged PR webhook."""
    
    pr = payload.pull_request
    repo = payload.repository
    
    # Create PR event structure similar to what we get from GitHub API
    pr_event = {
        "id": str(pr["id"]),
        "type": "PullRequestEvent",
        "repo": repo["full_name"],
        "actor": payload.sender["login"],
        "created_at": pr["merged_at"],
        "details": {
            "action": "closed",
            "number": pr["number"],
            "state": "closed",
            "merged": True
        },
        "url": pr["html_url"],
        "title": pr["title"],
        "body": pr.get("body", "")
    }
    
    # For now, we don't have clips available in webhook context
    # In a real implementation, you'd fetch recent clips here
    clips = []
    
    # Pair with clips (will return needs_broll=True since no clips)
    pairing = pair_with_clip(pr_event, clips)
    
    # Create story packet
    story_packet = make_story_packet(pr_event, pairing, clips)
    
    return story_packet


async def save_story_packet(story_packet: StoryPacket):
    """Save a story packet to disk."""
    
    # Create date directory
    # Fix: merged_at is a string, need to parse it to datetime first
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(story_packet.merged_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")
    date_dir = STORY_DIR / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    
    # Save individual story packet
    packet_file = date_dir / f"{story_packet.id}.json"
    with open(packet_file, 'w') as f:
        json.dump(story_packet.model_dump(), f, indent=2, default=str)
    
    logger.info(f"Story packet saved to {packet_file}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/stories/{date}")
async def list_stories(date: str):
    """List story packets for a given date."""
    # Validate date format (YYYY-MM-DD)
    try:
        # Parse the date to ensure it's in the correct format
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
        # Reformat to ensure consistency and prevent any potential issues
        validated_date = parsed_date.strftime("%Y-%m-%d")
    except ValueError as e:
        logger.warning(f"Invalid date format received: {date}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid date format. Use YYYY-MM-DD format."}
        )
    
    # Sanitize the date string to ensure it only contains valid characters
    if not all(c.isdigit() or c == '-' for c in validated_date):
        logger.warning(f"Invalid characters in date parameter: {date}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid date format. Use YYYY-MM-DD format."}
        )
    
    # Construct the path and verify it's within the allowed directory
    date_dir = STORY_DIR / validated_date
    resolved_path = date_dir.resolve()
    story_dir_resolved = STORY_DIR.resolve()
    
    # Verify the path is within the allowed directory to prevent path traversal
    try:
        if not resolved_path.is_relative_to(story_dir_resolved):
            logger.warning(f"Path traversal attempt detected: {date} -> {resolved_path}")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid date parameter."}
            )
    except ValueError:
        # is_relative_to raises ValueError if paths are not related
        logger.warning(f"Path traversal attempt detected: {date} -> {resolved_path}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid date parameter."}
        )
    
    if not date_dir.exists():
        return JSONResponse({"stories": []})
    
    stories = []
    for packet_file in date_dir.glob("*.json"):
        try:
            with open(packet_file, 'r') as f:
                story_data = json.load(f)
                stories.append(story_data)
        except Exception as e:
            logger.error(f"Error reading {packet_file}: {e}")
    
    return JSONResponse({"stories": stories})


if __name__ == "__main__":
    import uvicorn
    
    # Generate a secure webhook secret if not provided
    if not WEBHOOK_SECRET:
        import secrets
        webhook_secret = secrets.token_urlsafe(32)
        logger.warning(f"No webhook secret found. Generated one: {webhook_secret}")
        logger.warning("Add this to your .env file as GITHUB_WEBHOOK_SECRET")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
