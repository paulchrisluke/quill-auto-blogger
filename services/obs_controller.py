from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from services.auth import AuthService

load_dotenv()

try:
    import obswebsocket
    from obswebsocket import obsws, requests  # type: ignore
except Exception:  # pragma: no cover
    obsws = None
    requests = None

@dataclass
class ObsResult:
    ok: bool
    info: Dict[str, Any] | None = None
    error: str | None = None

class OBSController:
    def __init__(self) -> None:
        self.auth_service = AuthService()
        self.credentials = self.auth_service.get_obs_credentials()
        
        if self.credentials is None:
            raise ValueError("OBS credentials not available. Please check your environment configuration.")
        
        self.host = self.credentials.host
        self.port = self.credentials.port
        self.password = self.credentials.password
        self.target_scene = self.credentials.scene
        self.dry_run = self.credentials.dry_run
        self.ws = None

    def _connect(self) -> ObsResult:
        if self.dry_run:
            return ObsResult(ok=True, info={"dry_run": True})
        if obsws is None:
            return ObsResult(ok=False, error="obswebsocket library not installed")
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
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
                    rec_status = self.ws.call(requests.GetRecordingStatus())
                    if hasattr(rec_status, 'getRecording') and rec_status.getRecording():
                        return ObsResult(ok=True, info={"noop": "already_recording"})
                except Exception:
                    # Recording status check failed, continue anyway
                    pass
                
                # optional scene switch
                if self.target_scene:
                    try:
                        self.ws.call(requests.SetCurrentProgramScene(self.target_scene))
                    except Exception:
                        # scene may not exist; ignore
                        pass
                
                # Start recording
                start_result = self.ws.call(requests.StartRecord())
                if hasattr(start_result, 'status') and start_result.status == 'error':
                    return ObsResult(ok=False, error=f"StartRecord failed: {start_result}")
                return ObsResult(ok=True)
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
                    rec_status = self.ws.call(requests.GetRecordingStatus())
                    if hasattr(rec_status, 'getRecording') and not rec_status.getRecording():
                        return ObsResult(ok=True, info={"noop": "not_recording"})
                except Exception:
                    # Recording status check failed, continue anyway
                    pass
                
                # Stop recording
                stop_result = self.ws.call(requests.StopRecord())
                if hasattr(stop_result, 'status') and stop_result.status == 'error':
                    return ObsResult(ok=False, error=f"StopRecord failed: {stop_result}")
                return ObsResult(ok=True)
            return ObsResult(ok=True)
        except Exception as e:
            return ObsResult(ok=False, error=f"StopRecord failed: {e}")
        finally:
            self._disconnect()
