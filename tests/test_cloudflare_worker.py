#!/usr/bin/env python3
"""
Comprehensive tests for Cloudflare Worker functionality
Tests actual endpoints, caching, redirects, and M6 features
"""

import requests
import json
import time
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass
class TestResult:
    """Test result container"""
    name: str
    passed: bool
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    headers: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    etag: Optional[str] = None
    cache_control: Optional[str] = None


class CloudflareWorkerTester:
    """Test suite for Cloudflare Worker endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8787"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results: list[TestResult] = []
        
    def test_endpoint(self, path: str, expected_status: int = 200, 
                     method: str = "GET", **kwargs) -> TestResult:
        """Test a single endpoint"""
        url = urljoin(self.base_url, path)
        start_time = time.time()
        
        try:
            response = self.session.request(method, url, **kwargs)
            response_time = time.time() - start_time
            
            passed = response.status_code == expected_status
            result = TestResult(
                name=f"{method} {path}",
                passed=passed,
                status_code=response.status_code,
                response_time=response_time,
                headers=dict(response.headers),
                etag=response.headers.get('etag'),
                cache_control=response.headers.get('cache-control')
            )
            
            if not passed:
                result.error = f"Expected {expected_status}, got {response.status_code}"
                
        except Exception as e:
            result = TestResult(
                name=f"{method} {path}",
                passed=False,
                error=str(e)
            )
        
        self.test_results.append(result)
        return result
    
    def test_conditional_get(self, path: str) -> TestResult:
        """Test conditional GET with ETag"""
        # First request to get ETag
        first_response = self.test_endpoint(path)
        if not first_response.passed or not first_response.etag:
            return TestResult(
                name=f"Conditional GET {path}",
                passed=False,
                error="Failed to get initial response or ETag"
            )
        
        # Second request with If-None-Match
        second_response = self.test_endpoint(
            path, 
            expected_status=304,
            headers={'If-None-Match': first_response.etag}
        )
        
        if second_response.passed:
            return TestResult(
                name=f"Conditional GET {path}",
                passed=True,
                status_code=304,
                response_time=second_response.response_time
            )
        else:
            return TestResult(
                name=f"Conditional GET {path}",
                passed=False,
                error=f"Expected 304, got {second_response.status_code}"
            )
    
    def test_canonical_redirects(self) -> list[TestResult]:
        """Test canonical URL redirects"""
        redirect_tests = [
            ('/blogs/2025/08/27', 301),
            ('/blog/2025/08/27', 301),
        ]
        
        results = []
        for path, expected_status in redirect_tests:
            result = self.test_endpoint(path, expected_status)
            results.append(result)
            
            # Check if Location header points to canonical URL
            if result.passed and result.headers:
                location = result.headers.get('location')
                if location and '/blog/2025-08-27' in location:
                    result.passed = True
                else:
                    result.passed = False
                    result.error = f"Invalid redirect location: {location}"
        
        return results
    
    def test_cache_headers(self, path: str) -> TestResult:
        """Test cache headers are properly set"""
        result = self.test_endpoint(path)
        
        if not result.passed:
            return result
        
        # Check for required cache headers
        required_headers = ['cache-control', 'vary']
        missing_headers = []
        
        for header in required_headers:
            if not result.headers or header not in result.headers:
                missing_headers.append(header)
        
        if missing_headers:
            result.passed = False
            result.error = f"Missing cache headers: {missing_headers}"
        elif result.cache_control:
            # Validate cache control format
            if 'public' in result.cache_control and 'max-age' in result.cache_control:
                result.passed = True
            else:
                result.passed = False
                result.error = f"Invalid cache-control format: {result.cache_control}"
        
        return result
    
    def test_feed_validation(self, feed_path: str, content_type: str) -> TestResult:
        """Test feed generation and validation"""
        result = self.test_endpoint(feed_path)
        
        if not result.passed:
            return result
        
        # Check content type
        if result.headers and result.headers.get('content-type', '').startswith(content_type):
            result.passed = True
        else:
            result.passed = False
            result.error = f"Invalid content type for {feed_path}"
        
        return result
    
    def test_sitemap_validation(self, sitemap_path: str) -> TestResult:
        """Test sitemap generation and validation"""
        result = self.test_endpoint(sitemap_path)
        
        if not result.passed:
            return result
        
        # Check if it's valid XML
        if result.headers and 'xml' in result.headers.get('content-type', ''):
            result.passed = True
        else:
            result.passed = False
            result.error = f"Invalid content type for sitemap: {result.headers.get('content-type')}"
        
        return result
    
    def test_control_endpoint(self) -> TestResult:
        """Test control endpoint authentication"""
        # Test without auth (should fail)
        result = self.test_endpoint('/control/purge?date=2025-08-27', 401, method='POST')
        
        if not result.passed:
            return result
        
        # Test with invalid auth (should fail)
        result = self.test_endpoint(
            '/control/purge?date=2025-08-27', 
            403, 
            method='POST',
            headers={'Authorization': 'Bearer invalid-token'}
        )
        
        return result
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🧪 Running Cloudflare Worker Test Suite\n")
        
        # Basic endpoint tests
        print("📡 Testing Basic Endpoints...")
        basic_tests = [
            ('/', 200),
            ('/health', 200),
            ('/robots.txt', 200),
            ('/sitemap.xml', 200),
            ('/feed.xml', 200),
            ('/feed.atom', 200),
            ('/feed.json', 200),
            ('/blogs', 200),
            ('/blogs/index.json', 200),
        ]
        
        for path, expected_status in basic_tests:
            self.test_endpoint(path, expected_status)
        
        # Test blog endpoint (if it exists)
        print("📝 Testing Blog Endpoints...")
        blog_result = self.test_endpoint('/blog/2025-08-27', 200)
        if blog_result.passed:
            # Test conditional GET
            conditional_result = self.test_conditional_get('/blog/2025-08-27')
            self.test_results.append(conditional_result)
            
            # Test cache headers
            cache_result = self.test_cache_headers('/blog/2025-08-27')
            self.test_results.append(cache_result)
        
        # Test canonical redirects
        print("🔄 Testing Canonical Redirects...")
        redirect_results = self.test_canonical_redirects()
        self.test_results.extend(redirect_results)
        
        # Test feed validation
        print("📰 Testing Feed Generation...")
        feed_tests = [
            ('/feed.xml', 'application/rss+xml'),
            ('/feed.atom', 'application/atom+xml'),
            ('/feed.json', 'application/feed+json'),
        ]
        
        for feed_path, content_type in feed_tests:
            feed_result = self.test_feed_validation(feed_path, content_type)
            self.test_results.append(feed_result)
        
        # Test sitemap validation
        print("🗺️ Testing Sitemap Generation...")
        sitemap_result = self.test_sitemap_validation('/sitemap.xml')
        self.test_results.append(sitemap_result)
        
        # Test control endpoint
        print("🔐 Testing Control Endpoints...")
        control_result = self.test_control_endpoint()
        self.test_results.append(control_result)
        
        # Test cache headers for various endpoints
        print("💾 Testing Cache Headers...")
        cache_test_paths = ['/blogs', '/feed.xml', '/sitemap.xml']
        for path in cache_test_paths:
            cache_result = self.test_cache_headers(path)
            self.test_results.append(cache_result)
        
        return self.generate_report()
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.passed)
        failed_tests = total_tests - passed_tests
        
        # Group results by category
        categories = {
            'Basic Endpoints': [],
            'Blog & Content': [],
            'Canonical Redirects': [],
            'Feeds': [],
            'Sitemaps': [],
            'Cache & Performance': [],
            'Control & Security': [],
        }
        
        for result in self.test_results:
            if 'blog' in result.name.lower():
                categories['Blog & Content'].append(result)
            elif 'redirect' in result.name.lower() or 'canonical' in result.name.lower():
                categories['Canonical Redirects'].append(result)
            elif 'feed' in result.name.lower():
                categories['Feeds'].append(result)
            elif 'sitemap' in result.name.lower():
                categories['Sitemaps'].append(result)
            elif 'cache' in result.name.lower() or 'conditional' in result.name.lower():
                categories['Cache & Performance'].append(result)
            elif 'control' in result.name.lower():
                categories['Control & Security'].append(result)
            else:
                categories['Basic Endpoints'].append(result)
        
        report = {
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0
            },
            'categories': categories,
            'all_results': self.test_results
        }
        
        return report
    
    def print_report(self, report: Dict[str, Any]):
        """Print formatted test report"""
        summary = report['summary']
        
        print("\n" + "="*60)
        print("📊 CLOUDFLARE WORKER TEST REPORT")
        print("="*60)
        
        print(f"\n🎯 Overall Results:")
        print(f"   Total Tests: {summary['total_tests']}")
        print(f"   Passed: {summary['passed_tests']} ✅")
        print(f"   Failed: {summary['failed_tests']} ❌")
        print(f"   Success Rate: {summary['success_rate']:.1f}%")
        
        print(f"\n📋 Detailed Results by Category:")
        
        for category, results in report['categories'].items():
            if not results:
                continue
                
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            
            print(f"\n   {category}: {passed}/{total} passed")
            
            for result in results:
                status = "✅" if result.passed else "❌"
                print(f"     {status} {result.name}")
                
                if not result.passed and result.error:
                    print(f"        Error: {result.error}")
                
                if result.response_time:
                    print(f"        Response Time: {result.response_time:.3f}s")
                
                if result.etag:
                    print(f"        ETag: {result.etag[:20]}...")
                
                if result.cache_control:
                    print(f"        Cache-Control: {result.cache_control}")
        
        print("\n" + "="*60)
        
        if summary['failed_tests'] == 0:
            print("🎉 ALL TESTS PASSED! Cloudflare Worker is working perfectly!")
        else:
            print(f"⚠️  {summary['failed_tests']} tests failed. Check the details above.")
        
        print("="*60)


def main():
    """Main test runner"""
    import sys
    
    # Allow custom base URL
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
    
    print(f"🚀 Testing Cloudflare Worker at: {base_url}")
    print("Make sure the worker is running with: npm run dev")
    
    tester = CloudflareWorkerTester(base_url)
    
    try:
        report = tester.run_all_tests()
        tester.print_report(report)
        
        # Exit with error code if any tests failed
        if report['summary']['failed_tests'] > 0:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Testing failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
