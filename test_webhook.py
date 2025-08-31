#!/usr/bin/env python3
"""
Simple test script for webhook endpoints
"""

import httpx
import json
import time
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from webhook_server import app, _run_record_command_direct

# Shared timeout for all HTTP calls
TIMEOUT = 5

def test_webhook_endpoints():
    base_url = "http://localhost:8000"
    
    # Test health endpoint
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{base_url}/health")
            print(f"Health check: {response.status_code} - {response.json()}")
    except httpx.ConnectError:
        print("❌ Webhook server not running. Start it with: python webhook_server.py")
        return False
    except httpx.TimeoutException:
        print("❌ Health check timed out")
        return False
    except httpx.RequestError as e:
        print(f"❌ Health check failed: {e}")
        return False
    
    # Test record start endpoint
    payload = {
        "story_id": "story_20250827_pr34",
        "date": "2025-08-27"
    }
    
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                f"{base_url}/control/record/start",
                headers={"Content-Type": "application/json"},
                json=payload
            )
        
        if not (200 <= response.status_code < 300):
            try:
                error_body = response.json()
            except (json.JSONDecodeError, ValueError):
                error_body = response.text
            print(f"❌ Record start failed with status {response.status_code}: {error_body}")
            return False
        
        try:
            response_body = response.json()
        except (json.JSONDecodeError, ValueError):
            response_body = response.text
        print(f"Record start: {response.status_code} - {response_body}")
    except httpx.RequestError as e:
        print(f"❌ Record start failed: {e}")
        return False
    
    # Test record stop endpoint
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                f"{base_url}/control/record/stop",
                headers={"Content-Type": "application/json"},
                json=payload
            )
        
        if not (200 <= response.status_code < 300):
            try:
                error_body = response.json()
            except (json.JSONDecodeError, ValueError):
                error_body = response.text
            print(f"❌ Record stop failed with status {response.status_code}: {error_body}")
            return False
        
        try:
            response_body = response.json()
        except (json.JSONDecodeError, ValueError):
            response_body = response.text
        print(f"Record stop: {response.status_code} - {response_body}")
    except httpx.RequestError as e:
        print(f"❌ Record stop failed: {e}")
        return False
    
    print("✅ All webhook endpoints working!")
    return True


# Unit tests for security improvements
client = TestClient(app)


class TestControlEndpointSecurity:
    """Test security improvements for control endpoints."""
    
    def setup_method(self):
        """Set up test environment."""
        # Save the original CONTROL_API_TOKEN value
        self.original_control_api_token = os.environ.get("CONTROL_API_TOKEN")
        # Clear any existing environment variables
        if "CONTROL_API_TOKEN" in os.environ:
            del os.environ["CONTROL_API_TOKEN"]
    
    def teardown_method(self):
        """Clean up test environment."""
        # Restore the original CONTROL_API_TOKEN value
        if self.original_control_api_token is not None:
            os.environ["CONTROL_API_TOKEN"] = self.original_control_api_token
        elif "CONTROL_API_TOKEN" in os.environ:
            del os.environ["CONTROL_API_TOKEN"]
    
    def test_control_start_no_auth(self):
        """Test that control start endpoint requires authentication."""
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        response = client.post("/control/record/start", json=payload)
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["detail"]
    
    def test_control_stop_no_auth(self):
        """Test that control stop endpoint requires authentication."""
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        response = client.post("/control/record/stop", json=payload)
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["detail"]
    
    def test_control_start_invalid_auth_format(self):
        """Test that invalid auth format is rejected."""
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        headers = {"Authorization": "InvalidFormat token123"}
        response = client.post("/control/record/start", json=payload, headers=headers)
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["detail"]
    
    def test_control_start_no_token_configured(self):
        """Test that missing token configuration is handled."""
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        headers = {"Authorization": "Bearer token123"}
        response = client.post("/control/record/start", json=payload, headers=headers)
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["detail"]
    
    def test_control_start_invalid_token(self):
        """Test that invalid token is rejected."""
        os.environ["CONTROL_API_TOKEN"] = "correct_token"
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        headers = {"Authorization": "Bearer wrong_token"}
        response = client.post("/control/record/start", json=payload, headers=headers)
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["detail"]
    
    def test_control_start_valid_auth(self):
        """Test that valid authentication works."""
        os.environ["CONTROL_API_TOKEN"] = "correct_token"
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        headers = {"Authorization": "Bearer correct_token"}
        
        with patch('webhook_server._run_record_command_direct') as mock_run:
            mock_run.return_value = True
            response = client.post("/control/record/start", json=payload, headers=headers)
            assert response.status_code == 200
            assert response.json()["ok"] is True
    
    def test_control_start_invalid_story_id(self):
        """Test that invalid story_id is rejected by Pydantic validation."""
        os.environ["CONTROL_API_TOKEN"] = "correct_token"
        payload = {"story_id": "invalid@story", "date": "2025-01-01"}
        headers = {"Authorization": "Bearer correct_token"}
        response = client.post("/control/record/start", json=payload, headers=headers)
        assert response.status_code == 422  # Pydantic validation error
        # Check that the error message contains validation info
        error_detail = response.json()["detail"]
        assert any("story_id" in str(error) for error in error_detail)
    
    def test_control_start_invalid_date(self):
        """Test that invalid date is rejected by Pydantic validation."""
        os.environ["CONTROL_API_TOKEN"] = "correct_token"
        payload = {"story_id": "test_story", "date": "invalid-date"}
        headers = {"Authorization": "Bearer correct_token"}
        response = client.post("/control/record/start", json=payload, headers=headers)
        assert response.status_code == 422  # Pydantic validation error
        # Check that the error message contains validation info
        error_detail = response.json()["detail"]
        assert any("date" in str(error) for error in error_detail)
    
    def test_control_start_empty_story_id(self):
        """Test that empty story_id is rejected by Pydantic validation."""
        os.environ["CONTROL_API_TOKEN"] = "correct_token"
        payload = {"story_id": "", "date": "2025-01-01"}
        headers = {"Authorization": "Bearer correct_token"}
        response = client.post("/control/record/start", json=payload, headers=headers)
        assert response.status_code == 422  # Pydantic validation error
        # Check that the error message contains validation info
        error_detail = response.json()["detail"]
        assert any("story_id" in str(error) for error in error_detail)
    
    def test_control_stop_valid_auth(self):
        """Test that valid authentication works for stop endpoint."""
        os.environ["CONTROL_API_TOKEN"] = "correct_token"
        payload = {"story_id": "test_story", "date": "2025-01-01"}
        headers = {"Authorization": "Bearer correct_token"}
        
        with patch('webhook_server._run_record_command_direct') as mock_run:
            mock_run.return_value = True
            response = client.post("/control/record/stop", json=payload, headers=headers)
            assert response.status_code == 200
            assert response.json()["ok"] is True


class TestDirectRecordCommand:
    """Test the direct record command function."""
    
    def test_run_record_command_direct_start_success(self):
        """Test successful start recording."""
        with patch('services.obs_controller.OBSController') as mock_obs_class, \
             patch('services.story_state.StoryState') as mock_state_class:
            
            # Mock OBS controller
            mock_obs = MagicMock()
            mock_obs.start_recording.return_value.ok = True
            mock_obs_class.return_value = mock_obs
            
            # Mock story state
            mock_state = MagicMock()
            mock_state_class.return_value = mock_state
            
            result = _run_record_command_direct("test_story", "start", "2025-01-01")
            assert result is True
            mock_obs.start_recording.assert_called_once()
            mock_state.begin_recording.assert_called_once()
    
    def test_run_record_command_direct_stop_success(self):
        """Test successful stop recording."""
        with patch('services.obs_controller.OBSController') as mock_obs_class, \
             patch('services.story_state.StoryState') as mock_state_class:
            
            # Mock OBS controller
            mock_obs = MagicMock()
            mock_obs.stop_recording.return_value.ok = True
            mock_obs_class.return_value = mock_obs
            
            # Mock story state
            mock_state = MagicMock()
            mock_state_class.return_value = mock_state
            
            result = _run_record_command_direct("test_story", "stop", "2025-01-01")
            assert result is True
            mock_obs.stop_recording.assert_called_once()
            mock_state.end_recording.assert_called_once()
    
    def test_run_record_command_direct_invalid_action(self):
        """Test invalid action handling."""
        result = _run_record_command_direct("test_story", "invalid", "2025-01-01")
        assert result is False
    
    def test_run_record_command_direct_obs_failure(self):
        """Test OBS controller failure handling."""
        with patch('services.obs_controller.OBSController') as mock_obs_class:
            mock_obs_class.side_effect = Exception("OBS connection failed")
            
            result = _run_record_command_direct("test_story", "start", "2025-01-01")
            assert result is False
    
    def test_run_record_command_direct_recording_failure(self):
        """Test recording operation failure handling."""
        with patch('services.obs_controller.OBSController') as mock_obs_class, \
             patch('services.story_state.StoryState') as mock_state_class:
            
            # Mock OBS controller with failure
            mock_obs = MagicMock()
            mock_obs.start_recording.return_value.ok = False
            mock_obs.start_recording.return_value.error = "Recording failed"
            mock_obs_class.return_value = mock_obs
            
            # Mock story state
            mock_state = MagicMock()
            mock_state_class.return_value = mock_state
            
            result = _run_record_command_direct("test_story", "start", "2025-01-01")
            assert result is False


if __name__ == "__main__":
    test_webhook_endpoints()
