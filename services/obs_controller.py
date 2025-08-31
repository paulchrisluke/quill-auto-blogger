from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
from dotenv import load_dotenv

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
        self.host = os.getenv("OBS_HOST", "127.0.0.1")
        self.port = int(os.getenv("OBS_PORT", "4455"))
        self.password = os.getenv("OBS_PASSWORD", "")
        self.target_scene = os.getenv("OBS_SCENE", "").strip()
        self.dry_run = os.getenv("OBS_DRY_RUN", "false").lower() == "true"
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
                rec_status = self.ws.call(requests.GetRecordingStatus())
                if rec_status.getRecording():
                    return ObsResult(ok=True, info={"noop": "already_recording"})
                # optional scene switch
                if self.target_scene:
                    try:
                        self.ws.call(requests.SetCurrentProgramScene(self.target_scene))
                    except Exception:
                        # scene may not exist; ignore
                        pass
                self.ws.call(requests.StartRecord())
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
                rec_status = self.ws.call(requests.GetRecordingStatus())
                if not rec_status.getRecording():
                    return ObsResult(ok=True, info={"noop": "not_recording"})
                self.ws.call(requests.StopRecord())
            return ObsResult(ok=True)
        except Exception as e:
            return ObsResult(ok=False, error=f"StopRecord failed: {e}")
        finally:
            self._disconnect()
