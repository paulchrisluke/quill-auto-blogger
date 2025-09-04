"""
Tests for the site CLI commands.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from click.testing import CliRunner

from cli.devlog import site


class TestSiteCLI:
    """Test cases for site CLI commands."""
    
    @pytest.fixture
    def runner(self):
        """Create Click CLI runner."""
        return CliRunner()
    
    def test_site_build_success(self, runner):
        """Test successful site build."""
        mock_builder = Mock()
        mock_builder.build.return_value = {
            'index.html': True
        }
        
        with patch('services.site_builder.SiteBuilder', return_value=mock_builder):
            result = runner.invoke(site, ['build'])
            
            assert result.exit_code == 0
            assert '✓ index.html' in result.output
            assert 'All site files built successfully' in result.output
    
    def test_site_build_partial_failure(self, runner):
        """Test site build with partial failure."""
        mock_builder = Mock()
        mock_builder.build.return_value = {
            'index.html': False
        }
        
        with patch('services.site_builder.SiteBuilder', return_value=mock_builder):
            result = runner.invoke(site, ['build'])
            
            assert result.exit_code == 1
            assert '✗ index.html' in result.output
            assert 'Some site files failed to build' in result.output
    
    def test_site_build_exception(self, runner):
        """Test site build with exception."""
        with patch('services.site_builder.SiteBuilder', side_effect=Exception("Test error")):
            result = runner.invoke(site, ['build'])
            
            assert result.exit_code == 1
            assert 'Site build failed: Test error' in result.output
    
    def test_site_publish_dry_run(self, runner):
        """Test site publish dry run."""
        site_dir = Path('out/site')
        site_files = [Path('out/site/index.html')]
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.glob', return_value=site_files):
                result = runner.invoke(site, ['publish', '--dry-run'])
                
                assert result.exit_code == 0
                assert 'DRY RUN - No files will be uploaded' in result.output
                assert 'index.html' in result.output
    
    def test_site_publish_site_dir_missing(self, runner):
        """Test site publish when site directory doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            result = runner.invoke(site, ['publish'])
            
            assert result.exit_code == 1
            assert 'Site directory not found' in result.output
            assert 'Run \'devlog site build\' first' in result.output
    
    def test_site_publish_no_html_files(self, runner):
        """Test site publish when no HTML files exist."""
        with patch('pathlib.Path.exists', side_effect=[True, True, False]):
            with patch('pathlib.Path.glob', return_value=[]):
                result = runner.invoke(site, ['publish'])
                
                assert result.exit_code == 1
                assert 'No HTML files found in out/site' in result.output
                assert 'Run \'devlog site build\' first' in result.output
    
    def test_site_publish_success(self, runner):
        """Test successful site publish."""
        site_dir = Path('out/site')
        site_files = [Path('out/site/index.html')]
        
        mock_publisher = Mock()
        mock_publisher.publish_site.return_value = {
            'index.html': True
        }
        mock_publisher.publish_blogs.return_value = {
            '2025-01-15/API-v3-2025-01-15_digest.json': True
        }
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.glob', return_value=site_files):
                with patch('services.publisher_r2.R2Publisher', return_value=mock_publisher):
                    result = runner.invoke(site, ['publish'])
                    
                    assert result.exit_code == 0
                    assert '✓ index.html' in result.output
                    assert 'All files published successfully' in result.output
    
    def test_site_publish_partial_failure(self, runner):
        """Test site publish with partial failure."""
        site_dir = Path('out/site')
        site_files = [Path('out/site/index.html')]
        
        mock_publisher = Mock()
        mock_publisher.publish_site.return_value = {
            'index.html': False
        }
        mock_publisher.publish_blogs.return_value = {}
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.glob', return_value=site_files):
                with patch('services.publisher_r2.R2Publisher', return_value=mock_publisher):
                    result = runner.invoke(site, ['publish'])
                    
                    assert result.exit_code == 1
                    assert 'Some files failed to publish' in result.output
                    assert 'Site publishing had failures' in result.output
    
    def test_site_publish_exception(self, runner):
        """Test site publish with exception."""
        site_dir = Path('out/site')
        site_files = [Path('out/site/index.html')]
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.glob', return_value=site_files):
                with patch('services.publisher_r2.R2Publisher', side_effect=Exception("Test error")):
                    result = runner.invoke(site, ['publish'])
                    
                    assert result.exit_code == 1
                    assert 'Site publishing failed: Test error' in result.output
    
    def test_site_publish_blogs_scan(self, runner):
        """Test site publish dry run with blogs scanning."""
        site_dir = Path('out/site')
        site_files = [Path('out/site/index.html')]
        blogs_dir = Path('blogs')
        api_v3_files = [
            Path('blogs/2025-01-15/API-v3-2025-01-15_digest.json'),
            Path('blogs/2025-01-16/API-v3-2025-01-16_digest.json')
        ]
        
        with patch('pathlib.Path.exists', side_effect=[True, True]):
            with patch('pathlib.Path.glob', return_value=site_files):
                with patch('pathlib.Path.rglob', return_value=api_v3_files):
                    result = runner.invoke(site, ['publish', '--dry-run'])
                    
                    assert result.exit_code == 0
                    assert 'API-v3 files to check: 2' in result.output
                    assert '2025-01-15/API-v3-2025-01-15_digest.json' in result.output
                    assert '2025-01-16/API-v3-2025-01-16_digest.json' in result.output
    
    def test_site_publish_blogs_no_directory(self, runner):
        """Test site publish dry run when blogs directory doesn't exist."""
        site_dir = Path('out/site')
        site_files = [Path('out/site/index.html')]
        
        with patch('pathlib.Path.exists', side_effect=[True, False]):
            with patch('pathlib.Path.glob', return_value=site_files):
                result = runner.invoke(site, ['publish', '--dry-run'])
                
                assert result.exit_code == 0
                assert 'No blogs directory found' in result.output
