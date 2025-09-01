from __future__ import annotations
import os
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from services.auth import AuthService

load_dotenv()

try:
    from obsws_python import ReqClient  # type: ignore
except Exception:  # pragma: no cover
    ReqClient = None

@dataclass
class ObsResult:
    ok: bool
    info: Dict[str, Any] | None = None
    error: str | None = None
    started_by_us: Optional[bool] = None
    story_id: Optional[str] = None

class OBSController:
    def __init__(self) -> None:
        self.auth_service = AuthService()
        self.credentials = self.auth_service.get_obs_credentials()
        
        if self.credentials is None:
            raise ValueError("OBS credentials not available. Please check your environment configuration.")
        
        self.host = self.credentials.host
        self.port = self.credentials.port
        self.password = self.credentials.password.get_secret_value()
        self.target_scene = self.credentials.scene
        self.dry_run = self.credentials.dry_run
        self.ws = None

    def _connect(self) -> ObsResult:
        if self.dry_run:
            return ObsResult(ok=True, info={"dry_run": True, "started_by_us": True})
        if ReqClient is None:
            return ObsResult(ok=False, error="obsws-python library not installed")
        try:
            self.ws = ReqClient(host=self.host, port=self.port, password=self.password)
            return ObsResult(ok=True)
        except Exception as e:
            return ObsResult(ok=False, error=f"OBS connect failed: {e}")

    def _disconnect(self) -> None:
        if self.ws:
            try:
                self.ws.disconnect()
            except Exception:
                pass
            self.ws = None

    def start_recording(self) -> ObsResult:
        """Start recording only. Never stop streaming, never close OBS."""
        conn = self._connect()
        if not conn.ok:
            return conn
        try:
            if not self.dry_run:
                # Try to get recording status, but don't fail if it doesn't work
                try:
                    rec_status = self.ws.get_record_status()
                    # Check if recording is already active (v5 API uses outputActive)
                    if hasattr(rec_status, 'outputActive') and rec_status.outputActive:
                        return ObsResult(ok=True, info={"noop": "already_recording", "started_by_us": False})
                except Exception:
                    # Recording status check failed, continue anyway
                    pass
                
                # optional scene switch
                if self.target_scene:
                    try:
                        self.ws.set_current_program_scene(self.target_scene)
                    except Exception:
                        # scene may not exist; ignore
                        pass
                
                # Start recording
                self.ws.start_record()
                return ObsResult(ok=True, info={"started_by_us": True})
            return ObsResult(ok=True)
        except Exception as e:
            return ObsResult(ok=False, error=f"StartRecord failed: {e}")
        finally:
            self._disconnect()

    def stop_recording(self) -> ObsResult:
        conn = self._connect()
        if not conn.ok:
            return conn
        try:
            if not self.dry_run:
                # Try to get recording status, but don't fail if it doesn't work
                try:
                    rec_status = self.ws.get_record_status()
                    # Check if recording is not active (v5 API uses outputActive)
                    if hasattr(rec_status, 'outputActive') and not rec_status.outputActive:
                        return ObsResult(ok=True, info={"noop": "not_recording"})
                except Exception:
                    # Recording status check failed, continue anyway
                    pass
                
                # Stop recording
                self.ws.stop_record()
                return ObsResult(ok=True)
            return ObsResult(ok=True)
        except Exception as e:
            return ObsResult(ok=False, error=f"StopRecord failed: {e}")
        finally:
            self._disconnect()

    async def record_bounded(self, story_id: str, prep_delay: int, duration: int) -> ObsResult:
        """
        Record for a bounded duration with prep delay.
        
        Args:
            story_id: Identifier for the story being recorded
            prep_delay: Seconds to wait before starting recording
            duration: Seconds to record
            
        Returns:
            ObsResult from the start or stop recording operation
        """
        # Validate parameters (allow int or float, non-negative)
        if not isinstance(prep_delay, (int, float)) or prep_delay < 0:
            return ObsResult(ok=False, error=f"prep_delay must be a non-negative number, got {prep_delay}")
        if not isinstance(duration, (int, float)) or duration <= 0:
            return ObsResult(ok=False, error=f"duration must be a positive number, got {duration}")
        
        started_by_us = False
        try:
            # Wait for prep delay
            await asyncio.sleep(prep_delay)
            
            # Start recording using asyncio.to_thread to avoid blocking
            start = await asyncio.to_thread(self.start_recording)
            
            if not start.ok:
                # If start failed, we definitely didn't start recording
                return ObsResult(ok=False, error=start.error, info=start.info, started_by_us=False, story_id=story_id)
            
            # Derive whether we started recording based on start result (only when start.ok is True)
            if isinstance(start.info, dict) and "started_by_us" in start.info:
                started_by_us = bool(start.info["started_by_us"])
            else:
                # Fallback: if noop already_recording present, we did not start it
                started_by_us = not (isinstance(start.info, dict) and start.info.get("noop") == "already_recording")

            if not start.ok:
                return ObsResult(ok=False, error=start.error, info=start.info, started_by_us=started_by_us, story_id=story_id)
            
            # Wait for duration
            await asyncio.sleep(duration)
            
            # Stop recording using asyncio.to_thread to avoid blocking only if we started it
            if started_by_us:
                stop = await asyncio.to_thread(self.stop_recording)
                return ObsResult(ok=stop.ok, info=stop.info, error=stop.error, started_by_us=True, story_id=story_id)
            else:
                # We didn't start it; don't stop someone else's recording
                return ObsResult(ok=True, info={"noop": "already_recording;did_not_stop"}, started_by_us=False, story_id=story_id)
            
        except asyncio.CancelledError:
            # If cancelled, stop recording if we started it
            if started_by_us:
                try:
                    await asyncio.to_thread(self.stop_recording)
                except Exception:
                    # Ignore errors during cleanup
                    pass
            # Re-raise CancelledError after cleanup
            raise
        except Exception as e:
            # If any other error occurs, stop recording if we started it
            if started_by_us:
                try:
                    await asyncio.to_thread(self.stop_recording)
                except Exception:
                    # Ignore errors during cleanup
                    pass
            # Return error result
            return ObsResult(ok=False, error=f"Recording failed: {e}", started_by_us=started_by_us, story_id=story_id)
