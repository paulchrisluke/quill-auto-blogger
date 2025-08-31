"""
Tests for transcription service.
"""

import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from services.transcribe import TranscriptionService


class TestTranscriptionService:
    """Test cases for TranscriptionService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch.dict('os.environ', {
            'CLOUDFLARE_ACCOUNT_ID': 'test_account_id',
            'CLOUDFLARE_API_TOKEN': 'test_api_token'
        }):
            self.transcribe_service = TranscriptionService()
    
    def test_init_missing_credentials(self):
        """Test initialization with missing credentials."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Cloudflare credentials not configured"):
                TranscriptionService()
    
    @patch('subprocess.run')
    def test_extract_audio_success(self, mock_run):
        """Test successful audio extraction."""
        mock_run.return_value = MagicMock(returncode=0)
        
        # Use temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "video.mp4"
            output_path = Path(temp_dir) / "output.wav"
            
            # Create dummy video file with bytes to avoid encoding issues
            video_path.write_bytes(b"fake video data")
            
            result = self.transcribe_service.extract_audio(video_path, output_path)
            
            assert result == output_path
            mock_run.assert_called_once()
            
            # Extract subprocess invocation robustly from mock_run
            call_args = mock_run.call_args
            if call_args[0]:  # positional arguments
                cmd_args = call_args[0][0]
            else:  # keyword arguments
                cmd_args = call_args[1]['args']
            
            # Convert Path objects to normalized absolute strings for comparison
            video_path_abs = str(video_path.absolute())
            output_path_abs = str(output_path.absolute())
            cmd_str = ' '.join(str(arg) for arg in cmd_args)
            
            # Assert ffmpeg executable and important kwargs
            assert Path(cmd_args[0]).name == "ffmpeg"
            assert video_path_abs in cmd_str
            assert output_path_abs in cmd_str
            kwargs = call_args[1]
            assert kwargs.get("check") is True
            assert kwargs.get("capture_output") is True
            assert kwargs.get("text") is True
            # Ensure last argument is the output path
            assert str(cmd_args[-1]) == output_path_abs
    
    @patch('subprocess.run')
    def test_extract_audio_ffmpeg_error(self, mock_run):
        """Test audio extraction with ffmpeg error."""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'ffmpeg', stderr="Error")
        
        video_path = Path("/path/to/video.mp4")
        
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            self.transcribe_service.extract_audio(video_path)
    
    @patch('subprocess.run')
    def test_extract_audio_ffmpeg_not_found(self, mock_run):
        """Test audio extraction when ffmpeg is not found."""
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")
        
        video_path = Path("/path/to/video.mp4")
        
        with pytest.raises(RuntimeError, match="ffmpeg not found"):
            self.transcribe_service.extract_audio(video_path)
    
    @patch('httpx.Client')
    def test_transcribe_audio_success(self, mock_client):
        """Test successful audio transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200  # Set status_code for the new error handling
        mock_response.json.return_value = {
            "success": True,
            "result": {"text": "This is a test transcript"}
        }
        mock_response.raise_for_status.return_value = None
        
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        # Create temporary audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b"fake audio data")
            audio_path = Path(f.name)
        
        try:
            result = self.transcribe_service.transcribe_audio(audio_path)
            assert result == "This is a test transcript"
            
            # Check API call
            mock_client_instance.post.assert_called_once()
            call_args = mock_client_instance.post.call_args
            
            # Check URL
            expected_url = "https://api.cloudflare.com/client/v4/accounts/test_account_id/ai/run/@cf/openai/whisper"
            assert call_args[0][0] == expected_url
            
            # Check headers
            headers = call_args[1]['headers']
            assert headers["Authorization"] == "Bearer test_api_token"
            assert headers["Content-Type"] == "application/octet-stream"
            
        finally:
            audio_path.unlink()
    
    @patch('httpx.Client')
    def test_transcribe_audio_api_error(self, mock_client):
        """Test audio transcription with API error."""
        mock_response = MagicMock()
        mock_response.status_code = 200  # Set status_code for the new error handling
        mock_response.json.return_value = {
            "success": False,
            "error": "Transcription failed"
        }
        mock_response.raise_for_status.return_value = None
        
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        # Create temporary audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b"fake audio data")
            audio_path = Path(f.name)
        
        try:
            with pytest.raises(RuntimeError, match="Transcription error"):
                self.transcribe_service.transcribe_audio(audio_path)
        finally:
            audio_path.unlink()
    
    @patch('httpx.Client')
    def test_transcribe_audio_http_error(self, mock_client):
        """Test audio transcription with HTTP error."""
        from httpx import HTTPStatusError
        
        mock_response = MagicMock()
        mock_response.text = "HTTP Error"
        
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = HTTPStatusError("400", request=None, response=mock_response)
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        # Create temporary audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b"fake audio data")
            audio_path = Path(f.name)
        
        try:
            with pytest.raises(RuntimeError, match="HTTP error during transcription"):
                self.transcribe_service.transcribe_audio(audio_path)
        finally:
            audio_path.unlink()
    
    @patch('httpx.Client')
    def test_transcribe_audio_rate_limit_error(self, mock_client):
        """Test audio transcription with rate limit error (429)."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.raise_for_status.side_effect = Exception("Rate limit error")
        
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        # Create temporary audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b"fake audio data")
            audio_path = Path(f.name)
        
        try:
            with pytest.raises(Exception, match="Rate limit error"):
                self.transcribe_service.transcribe_audio(audio_path)
        finally:
            audio_path.unlink()
    
    def test_transcribe_audio_file_not_found(self):
        """Test audio transcription with non-existent file."""
        audio_path = Path("/nonexistent/audio.wav")
        
        with pytest.raises(FileNotFoundError):
            self.transcribe_service.transcribe_audio(audio_path)
    
    @patch.object(TranscriptionService, 'extract_audio')
    @patch.object(TranscriptionService, 'transcribe_audio')
    def test_transcribe_video(self, mock_transcribe, mock_extract):
        """Test video transcription workflow."""
        video_path = Path("/path/to/video.mp4")
        audio_path = Path("/tmp/audio_temp.wav")
        
        mock_extract.return_value = audio_path
        mock_transcribe.return_value = "Test transcript"
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.unlink'):
                transcript, extracted_audio_path = self.transcribe_service.transcribe_video(video_path)
        
        assert transcript == "Test transcript"
        assert extracted_audio_path == audio_path
        
        mock_extract.assert_called_once_with(video_path)
        mock_transcribe.assert_called_once_with(audio_path)
    
    @patch.object(TranscriptionService, '_download_video')
    @patch.object(TranscriptionService, 'extract_audio')
    @patch.object(TranscriptionService, 'transcribe_audio')
    def test_download_and_transcribe(self, mock_transcribe, mock_extract, mock_download, tmp_path):
        """Test download and transcribe workflow."""
        video_url = "https://example.com/video.mp4"
        clip_id = "test_clip_123"
        
        # Use pytest tmp_path fixture for isolated testing
        video_path = tmp_path / f"video_{clip_id}.mp4"
        audio_path = tmp_path / f"audio_{clip_id}.wav"
        
        mock_download.return_value = None
        mock_extract.return_value = audio_path
        mock_transcribe.return_value = "Test transcript"
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.unlink'):
                with patch('tempfile.gettempdir', return_value=str(tmp_path)):
                    transcript, result_video_path, result_audio_path = self.transcribe_service.download_and_transcribe(
                        video_url, clip_id
                    )
        
        assert transcript == "Test transcript"
        assert result_video_path == video_path
        assert result_audio_path == audio_path
        
        mock_download.assert_called_once_with(video_url, video_path)
        mock_extract.assert_called_once_with(video_path)
        mock_transcribe.assert_called_once_with(audio_path)
    
    @patch('httpx.Client')
    def test_download_video_success(self, mock_client):
        """Test successful video download."""
        mock_response = MagicMock()
        mock_response.status_code = 200  # Set status_code for the new error handling
        mock_response.raise_for_status.return_value = None
        mock_response.iter_bytes.return_value = [b"chunk1", b"chunk2"]
        
        mock_client_instance = MagicMock()
        mock_client_instance.stream.return_value.__enter__.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        video_url = "https://example.com/video.mp4"
        output_path = Path("/tmp/video.mp4")
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('os.replace') as mock_replace:  # Explicitly capture the mock
                self.transcribe_service._download_video(video_url, output_path)
                
                # Check that file was opened for writing
                mock_file.assert_called()
                
                # Check that chunks were written
                file_handle = mock_file.return_value.__enter__.return_value
                assert file_handle.write.call_count == 2
                
                # Verify that os.replace was called for atomic move with correct destination
                mock_replace.assert_called_once()
                src, dst = mock_replace.call_args[0]
                assert Path(dst) == output_path
                # Ensure file was opened in binary write mode
                open_args, _ = mock_file.call_args
                assert open_args[1] == "wb"
    
    @patch('httpx.Client')
    def test_download_video_error(self, mock_client):
        """Test video download with error."""
        mock_client_instance = MagicMock()
        mock_client_instance.stream.side_effect = Exception("Download failed")
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        video_url = "https://example.com/video.mp4"
        output_path = Path("/tmp/video.mp4")
        
        with patch('builtins.open', mock_open()) as mock_file, patch('os.replace') as mock_replace:
            with pytest.raises(RuntimeError, match="Unexpected error during download"):
                self.transcribe_service._download_video(video_url, output_path)
            # Assert that no atomic move and no writes occurred
            mock_replace.assert_not_called()
            mock_file.assert_not_called()
    
    def test_cleanup_temp_files(self):
        """Test cleanup of temporary files."""
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            temp_file1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            temp_file2 = Path(f2.name)
        
        # Create a non-existent file
        non_existent = Path("/nonexistent/file.txt")
        
        try:
            # Clean up files
            self.transcribe_service.cleanup_temp_files(temp_file1, temp_file2, non_existent)
            
            # Check that files were deleted
            assert not temp_file1.exists()
            assert not temp_file2.exists()
            
        except Exception:
            # Clean up manually if test fails
            if temp_file1.exists():
                temp_file1.unlink()
            if temp_file2.exists():
                temp_file2.unlink()
            raise
