"""
Tests for the R2 publisher service.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
from botocore.exceptions import ClientError

from services.publisher_r2 import R2Publisher


class TestR2Publisher:
    """Test cases for R2Publisher class."""
    
    @pytest.fixture
    def mock_auth_service(self):
        """Mock AuthService with R2 credentials."""
        with patch('services.publisher_r2.AuthService') as mock_auth:
            mock_credentials = Mock()
            mock_credentials.access_key_id = 'test_access_key'
            mock_credentials.secret_access_key = Mock()
            mock_credentials.secret_access_key.get_secret_value.return_value = 'test_secret'
            mock_credentials.endpoint = 'https://test.r2.cloudflarestorage.com'
            mock_credentials.bucket = 'test-bucket'
            mock_credentials.region = 'auto'
            
            mock_auth_instance = Mock()
            mock_auth_instance.get_r2_credentials.return_value = mock_credentials
            mock_auth.return_value = mock_auth_instance
            
            yield mock_auth_instance
    
    @pytest.fixture
    def mock_s3_client(self):
        """Mock boto3 S3 client."""
        with patch('services.publisher_r2.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            yield mock_client
    
    @pytest.fixture
    def publisher(self, mock_auth_service, mock_s3_client):
        """Create R2Publisher instance with mocked dependencies."""
        return R2Publisher()
    
    def test_init_success(self, mock_auth_service, mock_s3_client):
        """Test successful initialization."""
        publisher = R2Publisher()
        assert publisher.bucket == 'test-bucket'
        assert publisher.s3_client is not None
    
    def test_init_no_credentials(self):
        """Test initialization failure when no R2 credentials."""
        with patch('services.publisher_r2.AuthService') as mock_auth:
            mock_auth_instance = Mock()
            mock_auth_instance.get_r2_credentials.return_value = None
            mock_auth.return_value = mock_auth_instance
            
            with pytest.raises(ValueError, match="R2 credentials not found"):
                R2Publisher()
    
    def test_hash_md5(self, publisher):
        """Test MD5 hash calculation."""
        mock_file_content = b"test content"
        with patch('builtins.open', mock_open(read_data=mock_file_content)):
            with patch('pathlib.Path.exists', return_value=True):
                result = publisher._hash_md5(Path('test.txt'))
                assert result == '9473fdd0d880a43c21b7778d34872157'
    
    def test_should_skip_file_exists_identical(self, publisher):
        """Test skip logic when file exists with identical content."""
        mock_response = {'ETag': '"test_md5_hash"'}
        publisher.s3_client.head_object.return_value = mock_response
        
        result = publisher._should_skip('test_key', 'test_md5_hash')
        assert result is True
        publisher.s3_client.head_object.assert_called_once_with(
            Bucket='test-bucket', Key='test_key'
        )
    
    def test_should_skip_file_exists_different(self, publisher):
        """Test skip logic when file exists with different content."""
        mock_response = {'ETag': '"different_md5_hash"'}
        publisher.s3_client.head_object.return_value = mock_response
        
        result = publisher._should_skip('test_key', 'test_md5_hash')
        assert result is False
    
    def test_should_skip_file_not_found(self, publisher):
        """Test skip logic when file doesn't exist."""
        error_response = {'Error': {'Code': '404'}}
        publisher.s3_client.head_object.side_effect = ClientError(
            error_response, 'HeadObject'
        )
        
        result = publisher._should_skip('test_key', 'test_md5_hash')
        assert result is False
    
    def test_should_skip_other_error(self, publisher):
        """Test skip logic when other error occurs."""
        error_response = {'Error': {'Code': 'AccessDenied'}}
        publisher.s3_client.head_object.side_effect = ClientError(
            error_response, 'HeadObject'
        )
        
        result = publisher._should_skip('test_key', 'test_md5_hash')
        assert result is False
    
    def test_headers_for_html(self, publisher):
        """Test headers for HTML files."""
        headers = publisher._headers_for(Path('test.html'))
        assert headers['ContentType'] == 'text/html; charset=utf-8'
        assert headers['CacheControl'] == 'public, max-age=3600, s-maxage=86400'
    
    def test_headers_for_json(self, publisher):
        """Test headers for JSON files."""
        headers = publisher._headers_for(Path('test.json'))
        assert headers['ContentType'] == 'application/json'
        assert headers['CacheControl'] == 'public, max-age=300, s-maxage=1800'
    
    def test_headers_for_other(self, publisher):
        """Test headers for other file types."""
        headers = publisher._headers_for(Path('test.txt'))
        assert headers['ContentType'] == 'application/octet-stream'
        assert headers['CacheControl'] == 'public, max-age=300, s-maxage=1800'
    
    def test_publish_site_success(self, publisher):
        """Test successful site publishing."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=b"test content")):
                with patch.object(publisher, '_hash_md5', return_value='test_hash'):
                    with patch.object(publisher, '_should_skip', return_value=False):
                        results = publisher.publish_site(Path('out/site'))
                        
                        assert results['index.html'] is True
                        publisher.s3_client.put_object.assert_called()
    
    def test_publish_site_skip_identical(self, publisher):
        """Test site publishing with identical content skip."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=b"test content")):
                with patch.object(publisher, '_hash_md5', return_value='test_hash'):
                    with patch.object(publisher, '_should_skip', return_value=True):
                        results = publisher.publish_site(Path('out/site'))
                        
                        assert results['index.html'] is True
                        publisher.s3_client.put_object.assert_not_called()
    
    def test_publish_site_directory_not_found(self, publisher):
        """Test site publishing when directory doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            results = publisher.publish_site(Path('nonexistent'))
            assert results == {}
    
    def test_publish_blogs_success(self, publisher):
        """Test successful blog publishing."""
        mock_files = [
            Path('blogs/2025-01-15/API-v3-2025-01-15_digest.json'),
            Path('blogs/2025-01-16/API-v3-2025-01-16_digest.json')
        ]
        
        # Mock valid JSON data
        mock_json_data = '{"title": "Test Blog", "content": "Test content"}'
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.rglob', return_value=mock_files):
                with patch('builtins.open', mock_open(read_data=mock_json_data)):
                    with patch.object(publisher, '_hash_md5', return_value='test_hash'):
                        with patch.object(publisher, '_should_skip', return_value=False):
                            # Mock feed generation to avoid file system issues
                            with patch.object(publisher, '_generate_and_publish_feeds'):
                                results = publisher.publish_blogs(Path('blogs'))
                                
                                assert len(results) == 2
                                assert all(results.values())
                                # When feed generation is mocked, only blog uploads happen
                                assert publisher.s3_client.put_object.call_count == 2
    
    def test_publish_blogs_no_files(self, publisher):
        """Test blog publishing when no API-v3 files found."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.rglob', return_value=[]):
                results = publisher.publish_blogs(Path('blogs'))
                assert results == {}
    
    def test_publish_blogs_directory_not_found(self, publisher):
        """Test blog publishing when directory doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            results = publisher.publish_blogs(Path('nonexistent'))
            assert results == {}
    
    def test_enhance_with_related_posts(self, publisher):
        """Test related posts enhancement."""
        blog_data = {
            'frontmatter': {'tags': ['feat'], 'title': 'Test'},
            'date': '2025-08-27'
        }
        
        all_blogs = [blog_data]
        
        with patch.object(publisher.related_service, 'find_related_posts') as mock_find:
            mock_find.return_value = [{'title': 'Related Post', 'path': '/blog/2025-08-26', 'score': 0.8}]
            
            enhanced = publisher._enhance_with_related_posts(blog_data, all_blogs)
            
            assert 'related_posts' in enhanced
            assert len(enhanced['related_posts']) == 1
            assert enhanced['related_posts'][0]['title'] == 'Related Post'
    
    def test_enhance_with_thumbnails(self, publisher):
        """Test thumbnail enhancement."""
        blog_data = {
            'story_packets': [{
                'id': 'test_1',
                'video': {'status': 'rendered', 'path': 'test.mp4'}
            }]
        }
        
        with patch.object(publisher.video_processor, 'generate_story_thumbnails') as mock_gen:
            mock_gen.return_value = {'intro': 'thumb1.jpg', 'why': 'thumb2.jpg'}
            
            enhanced = publisher._enhance_with_thumbnails(blog_data, Path('blogs/2025-08-27'))
            
            assert 'thumbnails' in enhanced['story_packets'][0]['video']
            assert enhanced['story_packets'][0]['video']['thumbnails']['intro'] == 'thumb1.jpg'
