"""
Tests for Pydantic models.
"""

import pytest
from datetime import datetime
from models import TwitchClip, GitHubEvent, TwitchToken, GitHubToken, SeenIds


class TestTwitchClip:
    """Test cases for TwitchClip model."""
    
    def test_twitch_clip_creation(self):
        """Test creating a TwitchClip with required fields."""
        clip = TwitchClip(
            id="test_id",
            title="Test Clip",
            url="https://clips.twitch.tv/test",
            broadcaster_name="test_broadcaster",
            created_at=datetime.now()
        )
        
        assert clip.id == "test_id"
        assert clip.title == "Test Clip"
        assert clip.url == "https://clips.twitch.tv/test"
        assert clip.broadcaster_name == "test_broadcaster"
        assert clip.transcript is None
        assert clip.video_path is None
        assert clip.audio_path is None
    
    def test_twitch_clip_with_optional_fields(self):
        """Test creating a TwitchClip with optional fields."""
        clip = TwitchClip(
            id="test_id",
            title="Test Clip",
            url="https://clips.twitch.tv/test",
            broadcaster_name="test_broadcaster",
            created_at=datetime.now(),
            transcript="This is a test transcript",
            video_path="/path/to/video.mp4",
            audio_path="/path/to/audio.wav",
            duration=30.5,
            view_count=1000,
            language="en"
        )
        
        assert clip.transcript == "This is a test transcript"
        assert clip.video_path == "/path/to/video.mp4"
        assert clip.audio_path == "/path/to/audio.wav"
        assert clip.duration == 30.5
        assert clip.view_count == 1000
        assert clip.language == "en"
    
    def test_twitch_clip_serialization(self):
        """Test TwitchClip serialization to dict."""
        clip = TwitchClip(
            id="test_id",
            title="Test Clip",
            url="https://clips.twitch.tv/test",
            broadcaster_name="test_broadcaster",
            created_at=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        data = clip.model_dump()
        assert data["id"] == "test_id"
        assert data["title"] == "Test Clip"
        assert "created_at" in data


class TestGitHubEvent:
    """Test cases for GitHubEvent model."""
    
    def test_github_event_creation(self):
        """Test creating a GitHubEvent with required fields."""
        event = GitHubEvent(
            id="test_id",
            type="PushEvent",
            repo="owner/repo",
            actor="test_user",
            created_at=datetime.now()
        )
        
        assert event.id == "test_id"
        assert event.type == "PushEvent"
        assert event.repo == "owner/repo"
        assert event.actor == "test_user"
        assert event.details == {}
        assert event.url is None
        assert event.title is None
        assert event.body is None
    
    def test_github_event_with_optional_fields(self):
        """Test creating a GitHubEvent with optional fields."""
        event = GitHubEvent(
            id="test_id",
            type="PullRequestEvent",
            repo="owner/repo",
            actor="test_user",
            created_at=datetime.now(),
            details={"action": "opened", "number": 123},
            url="https://github.com/owner/repo/pull/123",
            title="Test PR",
            body="This is a test PR"
        )
        
        assert event.details == {"action": "opened", "number": 123}
        assert event.url == "https://github.com/owner/repo/pull/123"
        assert event.title == "Test PR"
        assert event.body == "This is a test PR"
    
    def test_github_event_serialization(self):
        """Test GitHubEvent serialization to dict."""
        event = GitHubEvent(
            id="test_id",
            type="PushEvent",
            repo="owner/repo",
            actor="test_user",
            created_at=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        data = event.model_dump()
        assert data["id"] == "test_id"
        assert data["type"] == "PushEvent"
        assert "created_at" in data


class TestTwitchToken:
    """Test cases for TwitchToken model."""
    
    def test_twitch_token_creation(self):
        """Test creating a TwitchToken."""
        token = TwitchToken(
            access_token="test_token",
            expires_in=3600,
            token_type="bearer",
            expires_at=datetime.now()
        )
        
        assert token.access_token == "test_token"
        assert token.expires_in == 3600
        assert token.token_type == "bearer"
    
    def test_twitch_token_serialization(self):
        """Test TwitchToken serialization to dict."""
        token = TwitchToken(
            access_token="test_token",
            expires_in=3600,
            token_type="bearer",
            expires_at=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        data = token.model_dump()
        assert data["access_token"] == "test_token"
        assert data["expires_in"] == 3600
        assert "expires_at" in data


class TestGitHubToken:
    """Test cases for GitHubToken model."""
    
    def test_github_token_creation(self):
        """Test creating a GitHubToken."""
        token = GitHubToken(
            token="test_github_token",
            expires_at=datetime.now(),
            permissions={"contents": "read", "metadata": "read"}
        )
        
        assert token.token == "test_github_token"
        assert token.permissions == {"contents": "read", "metadata": "read"}
    
    def test_github_token_serialization(self):
        """Test GitHubToken serialization to dict."""
        token = GitHubToken(
            token="test_github_token",
            expires_at=datetime(2023, 1, 1, 12, 0, 0),
            permissions={"contents": "read"}
        )
        
        data = token.model_dump()
        assert data["token"] == "test_github_token"
        assert data["permissions"] == {"contents": "read"}
        assert "expires_at" in data


class TestSeenIds:
    """Test cases for SeenIds model."""
    
    def test_seen_ids_creation(self):
        """Test creating a SeenIds instance."""
        seen_ids = SeenIds()
        
        assert seen_ids.twitch_clips == []
        assert seen_ids.github_events == []
        assert seen_ids.last_updated is not None
    
    def test_seen_ids_with_data(self):
        """Test creating a SeenIds instance with data."""
        seen_ids = SeenIds(
            twitch_clips=["clip1", "clip2"],
            github_events=["event1"],
            last_updated=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        assert seen_ids.twitch_clips == ["clip1", "clip2"]
        assert seen_ids.github_events == ["event1"]
        assert seen_ids.last_updated == datetime(2023, 1, 1, 12, 0, 0)
    
    def test_seen_ids_serialization(self):
        """Test SeenIds serialization to dict."""
        seen_ids = SeenIds(
            twitch_clips=["clip1"],
            github_events=["event1"],
            last_updated=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        data = seen_ids.model_dump()
        assert data["twitch_clips"] == ["clip1"]
        assert data["github_events"] == ["event1"]
        assert "last_updated" in data
