#!/usr/bin/env python3
"""
FastAPI webhook server for GitHub PR merge events.
"""

import os
import json
import logging
import re
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import hmac
import hashlib

from fastapi import FastAPI, Request, HTTPException, Query, BackgroundTasks, Depends, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator, ConfigDict
from dotenv import load_dotenv
import nacl.signing
import nacl.encoding
import json

from story_schema import StoryPacket, make_story_packet, pair_with_clip
from services.utils import validate_story_id
from services.blog import BlogDigestBuilder
from services.notify import notify_blog_published

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Story Pipeline Webhook Server", version="1.0.0")

# Configuration
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
ALLOW_INSECURE_WEBHOOKS = os.getenv("ALLOW_INSECURE_WEBHOOKS") == "1"
DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
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





class RecordControlRequest(BaseModel):
    """Request model for record control endpoints."""
    story_id: str
    date: Optional[str] = None
    bounded: bool = False
    
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














async def run_bounded_recording(obs, state, date, story_id, prep_delay, duration):
    """Run bounded recording in background."""
    try:
        # Wait for prep delay
        await asyncio.sleep(prep_delay)
        
        # Start recording
        start_result = obs.start_recording()
        if not start_result.ok:
            logger.error(f"Failed to start recording in bounded mode: {start_result.error}")
            return
        
        # Wait for duration
        await asyncio.sleep(duration)
        
        # Stop recording
        stop_result = obs.stop_recording()
        if not stop_result.ok:
            logger.error(f"Failed to stop recording in bounded mode: {stop_result.error}")
            return
        
        # Complete bounded recording state
        state.complete_bounded_recording(date, story_id, duration, assume_utc=True)
        logger.info(f"Bounded recording completed for {story_id} ({duration}s)")
        
    except Exception as e:
        logger.error(f"Bounded recording failed: {e}")


# Add authentication dependency
async def verify_control_auth(authorization: Optional[str] = Header(None)) -> None:
    """Verify authentication for control endpoints."""
    if not authorization:
        logger.warning("Control endpoint accessed without authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check for Bearer token case-insensitively
    if not authorization.lower().startswith("bearer "):
        logger.warning("Invalid authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Extract token (case-insensitive Bearer scheme handling)
    token = authorization[7:]  # Remove "Bearer " prefix
    
    # Get expected token from environment
    expected_token = os.getenv("CONTROL_API_TOKEN")
    if not expected_token:
        logger.error("Control endpoint accessed but CONTROL_API_TOKEN not configured - server misconfiguration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Server authentication not properly configured"
        )
    
    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token, expected_token):
        logger.warning("Invalid control API token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid authorization token",
            headers={"WWW-Authenticate": "Bearer"}
        )


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
    """Start recording for a story, optionally with bounded mode."""
    
    try:
        if payload.bounded:
            # Handle bounded recording with direct function calls
            from services.obs_controller import OBSController
            from services.story_state import StoryState
            
            # Initialize OBS controller
            obs = OBSController()
            state = StoryState()
            
            # Parse date parameter or use current date
            if payload.date:
                try:
                    parsed_date = datetime.strptime(payload.date, "%Y-%m-%d")
                    date_obj = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            else:
                # Get current date
                now = datetime.now()
                date_obj = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Begin recording state
            state.begin_recording(date_obj, payload.story_id, assume_utc=True)
            
            # Get environment variables for timing
            prep_delay = int(os.getenv("RECORDING_PREP_DELAY", "5"))
            duration = int(os.getenv("RECORDING_DURATION", "15"))
            
            # Start bounded recording in background
            asyncio.create_task(run_bounded_recording(obs, state, date_obj, payload.story_id, prep_delay, duration))
            
            return {
                "status": "started",
                "mode": "bounded",
                "story_id": payload.story_id,
                "prep_delay": prep_delay,
                "duration": duration
            }
        else:
            # Handle regular recording with background tasks
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


# ============================================================================
# Blog API Endpoints for Cloudflare Integration
# ============================================================================

@app.get("/api/blog/{date}")
async def get_blog_post(date: str):
    """
    Get complete blog post data for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
        
    Returns:
        Complete blog data including digest, markdown, and assets
    """
    try:
        from services.blog import BlogDigestBuilder
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Get blog data
        builder = BlogDigestBuilder()
        blog_data = builder.get_blog_api_data(date)
        
        return blog_data
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No blog post found for date: {date}")
    except Exception as e:
        logger.error(f"Error getting blog post for {date}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/blog/{date}/markdown")
async def get_blog_markdown(date: str):
    """
    Get raw markdown content for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
        
    Returns:
        Raw markdown content
    """
    try:
        from services.blog import BlogDigestBuilder
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Get markdown
        builder = BlogDigestBuilder()
        markdown = builder.get_blog_markdown(date)
        
        return {"date": date, "markdown": markdown}
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No blog post found for date: {date}")
    except Exception as e:
        logger.error(f"Error getting blog markdown for {date}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/blog/{date}/digest")
async def get_blog_digest(date: str):
    """
    Get digest data for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
        
    Returns:
        Digest data
    """
    try:
        from services.blog import BlogDigestBuilder
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Get digest
        builder = BlogDigestBuilder()
        digest = builder.build_digest(date)
        
        return {"date": date, "digest": digest}
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No blog post found for date: {date}")
    except Exception as e:
        logger.error(f"Error getting blog digest for {date}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/assets/stories/{date}")
async def list_story_assets(date: str):
    """
    List all story assets for a date.
    
    Args:
        date: Date in YYYY-MM-DD format
        
    Returns:
        List of story assets for the date
    """
    try:
        from services.blog import BlogDigestBuilder
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Get assets
        builder = BlogDigestBuilder()
        assets = builder.get_blog_assets(date)
        
        return {"date": date, "assets": assets}
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No assets found for date: {date}")
    except Exception as e:
        logger.error(f"Error listing story assets for {date}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/assets/stories/{date}/{story_id}")
async def get_story_assets(date: str, story_id: str):
    """
    Get all assets for a specific story.
    
    Args:
        date: Date in YYYY-MM-DD format
        story_id: Story identifier
        
    Returns:
        All assets for the story
    """
    try:
        from services.publisher import Publisher
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Validate story ID
        if not _validate_story_id(story_id):
            raise HTTPException(status_code=400, detail="Invalid story ID")
        
        # Get story assets
        publisher = Publisher()
        assets = publisher.list_story_assets(date, story_id)
        
        return {"date": date, "story_id": story_id, "assets": assets}
        
    except Exception as e:
        logger.error(f"Error getting story assets for {date}/{story_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/assets/blog/{date}")
async def get_blog_assets(date: str):
    """
    Get all assets for a blog post.
    
    Args:
        date: Date in YYYY-MM-DD format
        
    Returns:
        All assets for the blog post
    """
    try:
        from services.blog import BlogDigestBuilder
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Get blog assets
        builder = BlogDigestBuilder()
        assets = builder.get_blog_assets(date)
        
        return {"date": date, "assets": assets}
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No blog post found for date: {date}")
    except Exception as e:
        logger.error(f"Error getting blog assets for {date}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _verify_discord_signature(request: Request, body: bytes) -> bool:
    """Verify Discord interaction signature."""
    if not DISCORD_PUBLIC_KEY:
        logger.warning("No Discord public key configured")
        return False
    
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    
    if not signature or not timestamp:
        return False
    
    try:
        # Create the message to verify
        message = timestamp.encode() + body
        
        # Verify the signature
        public_key_bytes = bytes.fromhex(DISCORD_PUBLIC_KEY)
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
        verify_key.verify(message, bytes.fromhex(signature))
        return True
    except Exception as e:
        logger.error(f"Discord signature verification failed: {e}")
        return False


@app.post("/discord/interactions")
async def handle_discord_interaction(request: Request):
    """Handle Discord button interactions for blog approval workflow."""
    try:
        # Get request body
        body = await request.body()
        
        # Verify Discord signature
        if not _verify_discord_signature(request, body):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse interaction data
        interaction_data = json.loads(body)
        interaction_type = interaction_data.get("type")
        
        # Handle PING (Discord verification)
        if interaction_type == 1:
            return {"type": 1}
        
        # Handle button interactions
        if interaction_type == 3:  # APPLICATION_COMMAND_INTERACTION
            custom_id = interaction_data.get("data", {}).get("custom_id", "")
            
            if custom_id.startswith("approve_blog_"):
                date = custom_id.replace("approve_blog_", "")
                return await _handle_blog_approval(interaction_data, date)
                
            elif custom_id.startswith("edit_blog_"):
                date = custom_id.replace("edit_blog_", "")
                return await _handle_blog_edit_request(interaction_data, date)
        
        # Unknown interaction type
        return {"type": 4, "data": {"content": "Unknown interaction type"}}
        
    except Exception as e:
        logger.error(f"Error handling Discord interaction: {e}")
        return {"type": 4, "data": {"content": f"Error: {str(e)}"}}


async def _handle_blog_approval(interaction_data: dict, date: str) -> dict:
    """Handle blog approval button click."""
    try:
        # Create FINAL digest using BlogDigestBuilder
        builder = BlogDigestBuilder()
        final_digest = builder.create_final_digest(date)
        
        if final_digest:
            # Send published notification
            if notify_blog_published(date):
                content = f"✅ **Blog Approved & Published** — {date}\n\nBlog has been approved and published successfully!"
            else:
                content = f"✅ **Blog Approved** — {date}\n\nBlog approved but failed to send published notification."
        else:
            content = f"❌ **Approval Failed** — {date}\n\nFailed to create FINAL digest. Check logs for details."
        
        return {
            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
            "data": {"content": content}
        }
        
    except Exception as e:
        logger.error(f"Error approving blog {date}: {e}")
        return {
            "type": 4,
            "data": {"content": f"❌ **Approval Error** — {date}\n\nError: {str(e)}"}
        }


async def _handle_blog_edit_request(interaction_data: dict, date: str) -> dict:
    """Handle blog edit request button click."""
    try:
        content = (
            f"📝 **Blog Edit Request** — {date}\n\n"
            f"Blog marked as needing edits. You can:\n"
            f"• Edit the PRE-CLEANED digest directly\n"
            f"• Regenerate content using the blog CLI\n"
            f"• Request another review when ready\n\n"
            f"Use: `python tools/blog_cli.py request-approval {date}` when ready for review again."
        )
        
        return {
            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
            "data": {"content": content}
        }
        
    except Exception as e:
        logger.error(f"Error handling edit request for {date}: {e}")
        return {
            "type": 4,
            "data": {"content": f"❌ **Edit Request Error** — {date}\n\nError: {str(e)}"}
        }


if __name__ == "__main__":
    import uvicorn
    
    # Generate a secure webhook secret if not provided
    if not WEBHOOK_SECRET:
        import secrets
        webhook_secret = secrets.token_urlsafe(32)
        logger.warning(f"No webhook secret found. Generated one: {webhook_secret}")
        logger.warning("Add this to your .env file as GITHUB_WEBHOOK_SECRET")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
