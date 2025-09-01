#!/usr/bin/env python3
"""
FastAPI webhook server for GitHub PR merge events.
"""

import os
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import hmac
import hashlib

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator, ConfigDict
from dotenv import load_dotenv

from story_schema import StoryPacket, make_story_packet, pair_with_clip
from services.utils import validate_story_id

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Story Pipeline Webhook Server", version="1.0.0")

# Configuration
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
ALLOW_INSECURE_WEBHOOKS = os.getenv("ALLOW_INSECURE_WEBHOOKS") == "1"
STORY_DIR = Path("./story_packets")
STORY_DIR.mkdir(parents=True, exist_ok=True)


def _validate_story_id(story_id: str) -> bool:
    """
    Validate and sanitize story_id.
    
    Args:
        story_id: The story ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Use shared validation function
    return validate_story_id(story_id)


def _run_record_command_direct(story_id: str, action: str, date: Optional[str] = None) -> bool:
    """
    Run the record command directly using Python functions instead of subprocess.
    
    Args:
        story_id: The validated story ID
        action: The action to perform ('start' or 'stop')
        date: Optional date string in YYYY-MM-DD format
        
    Returns:
        True if command executed successfully, False otherwise
    """
    if action not in ['start', 'stop']:
        logger.error(f"Invalid action: {action}")
        return False
    
    # Use current date if not provided
    if not date:
        date = datetime.now(timezone.utc).date().isoformat()
    
    try:
        # Import the required modules
        from services.obs_controller import OBSController
        from services.story_state import StoryState
        
        # Parse date
        if isinstance(date, str):
            parsed_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        elif isinstance(date, datetime):
            parsed_date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
        else:
            logger.error(f"Unsupported date type: {type(date)}")
            return False
        
        # Initialize OBSController with error handling
        try:
            obs = OBSController()
        except Exception:
            logger.exception("OBS initialization failed")
            return False
        
        state = StoryState()

        if action == "start":
            res = obs.start_recording()
            if not res.ok:
                logger.error(f"Failed to start recording: {res.error}")
                return False
            
            # Handle state.begin_recording errors
            try:
                state.begin_recording(parsed_date, story_id)
            except (FileNotFoundError, KeyError, ValueError):
                logger.exception("Failed to begin recording for story %s", story_id)
                return False
            
            logger.info(f"Recording started for {story_id}")
            return True
        else:
            res = obs.stop_recording()
            if not res.ok:
                logger.error(f"Failed to stop recording: {res.error}")
                return False
            
            # Handle state.end_recording errors
            try:
                state.end_recording(parsed_date, story_id)
            except (FileNotFoundError, KeyError, ValueError):
                logger.exception("Failed to end recording for story %s", story_id)
                return False
            
            logger.info(f"Recording stopped for {story_id}")
            return True
            
    except Exception:
        logger.exception("Exception in direct record command")
        return False


class GitHubWebhookPayload(BaseModel):
    """GitHub webhook payload model."""
    action: Optional[str] = None
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None


class RecordControlRequest(BaseModel):
    """Request model for record control endpoints."""
    story_id: str
    date: Optional[str] = None
    
    model_config = ConfigDict(extra="ignore")  # Allow extra fields but ignore them
    
    @field_validator('story_id')
    @classmethod
    def validate_story_id(cls, v):
        """Validate story_id format."""
        if not v or not isinstance(v, str):
            raise ValueError('story_id must be a non-empty string')
        
        # Use the shared validation function
        if not validate_story_id(v):
            raise ValueError('story_id must contain only alphanumeric characters, hyphens, and underscores')
        
        return v
    
    @field_validator('date')
    @classmethod
    def validate_date(cls, v):
        """Validate date format if provided."""
        if v is None:
            return v
        
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError('date must be in YYYY-MM-DD format')


async def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not WEBHOOK_SECRET:
        if ALLOW_INSECURE_WEBHOOKS:
            logger.warning("WEBHOOK_SECRET not configured but ALLOW_INSECURE_WEBHOOKS=1 - skipping verification for development only")
            return True
        else:
            logger.error("WEBHOOK_SECRET not configured and ALLOW_INSECURE_WEBHOOKS not set to '1' - rejecting webhook for security")
            return False
    
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


# Add authentication dependency
async def verify_control_auth(authorization: Optional[str] = Header(None)) -> None:
    """Verify authentication for control endpoints."""
    if not authorization:
        logger.warning("Control endpoint accessed without authorization header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    
    # Check for Bearer token
    if not authorization.startswith("Bearer "):
        logger.warning("Invalid authorization header format")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header format")
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    # Get expected token from environment
    expected_token = os.getenv("CONTROL_API_TOKEN")
    if not expected_token:
        logger.warning("Control endpoint accessed but CONTROL_API_TOKEN not configured")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token")
    
    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token, expected_token):
        logger.warning("Invalid control API token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/stories/{date}")
async def list_stories(date: str):
    """List story packets for a given date."""
    # Validate date format (YYYY-MM-DD)
    try:
        # Parse the date to ensure it's in the correct format
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
        # Reformat to ensure consistency and prevent any potential issues
        validated_date = parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        logger.warning(f"Invalid date format received: {date}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid date format. Use YYYY-MM-DD format."}
        )
    
    # Construct the path and verify it's within the allowed directory
    date_dir = STORY_DIR / validated_date
    resolved_path = date_dir.resolve()
    story_dir_resolved = STORY_DIR.resolve()
    
    # Verify the path is within the allowed directory to prevent path traversal
    if not resolved_path.is_relative_to(story_dir_resolved):
        logger.warning(f"Path traversal attempt detected: {date} -> {resolved_path}")
        return JSONResponse(status_code=400, content={"error": "Invalid date parameter."})
    
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


@app.post("/control/record/start")
async def control_record_start(
    payload: RecordControlRequest, 
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_control_auth)
):
    """Start recording for a story."""
    
    try:
        # Add task to background tasks with proper error handling
        try:
            background_tasks.add_task(_run_record_command_direct, payload.story_id, "start", payload.date)
        except Exception as e:
            logger.error(f"Failed to schedule recording start task: {e}")
            raise HTTPException(status_code=500, detail="Failed to schedule recording task")
        
        return {"ok": True, "story_id": payload.story_id, "action": "start"}
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error starting recording for story {payload.story_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start recording")


@app.post("/control/record/stop")
async def control_record_stop(
    payload: RecordControlRequest, 
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_control_auth)
):
    """Stop recording for a story."""
    
    try:
        # Add task to background tasks with proper error handling
        try:
            background_tasks.add_task(_run_record_command_direct, payload.story_id, "stop", payload.date)
        except Exception as e:
            logger.error(f"Failed to schedule recording stop task: {e}")
            raise HTTPException(status_code=500, detail="Failed to schedule recording task")
        
        return {"ok": True, "story_id": payload.story_id, "action": "stop"}
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error stopping recording for story {payload.story_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop recording")


if __name__ == "__main__":
    import uvicorn
    
    # Generate a secure webhook secret if not provided
    if not WEBHOOK_SECRET:
        import secrets
        webhook_secret = secrets.token_urlsafe(32)
        logger.warning(f"No webhook secret found. Generated one: {webhook_secret}")
        logger.warning("Add this to your .env file as GITHUB_WEBHOOK_SECRET")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
