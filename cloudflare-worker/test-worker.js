/**
 * Test script for Cloudflare Worker
 * Tests the worker endpoints and functionality
 */

// Test configuration
const TEST_CONFIG = {
  baseUrl: 'http://localhost:8787', // Local worker dev server
  apiUrl: 'http://localhost:8000',  // Local API server
  testDate: '2025-08-27'
};

// Test functions
async function testHealthEndpoint() {
  console.log('🧪 Testing health endpoint...');
  try {
    const response = await fetch(`${TEST_CONFIG.baseUrl}/health`);
    const result = await response.text();
    console.log(`✅ Health endpoint: ${result}`);
    return true;
  } catch (error) {
    console.log(`❌ Health endpoint failed: ${error.message}`);
    return false;
  }
}

async function testBlogAPI() {
  console.log('🧪 Testing blog API endpoint...');
  try {
    const response = await fetch(`${TEST_CONFIG.baseUrl}/api/blog/${TEST_CONFIG.testDate}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    console.log(`✅ Blog API: Found ${data.digest?.story_packets?.length || 0} stories`);
    return true;
  } catch (error) {
    console.log(`❌ Blog API failed: ${error.message}`);
    return false;
  }
}

async function testAssetsAPI() {
  console.log('🧪 Testing assets API endpoint...');
  try {
    const response = await fetch(`${TEST_CONFIG.baseUrl}/api/assets/stories/${TEST_CONFIG.testDate}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    console.log(`✅ Assets API: Found ${data.assets?.images?.length || 0} images, ${data.assets?.videos?.length || 0} videos`);
    return true;
  } catch (error) {
    console.log(`❌ Assets API failed: ${error.message}`);
    return false;
  }
}

async function testMarkdownAPI() {
  console.log('🧪 Testing markdown API endpoint...');
  try {
    const response = await fetch(`${TEST_CONFIG.baseUrl}/api/blog/${TEST_CONFIG.testDate}/markdown`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    console.log(`✅ Markdown API: Content length ${data.markdown?.length || 0} characters`);
    return true;
  } catch (error) {
    console.log(`❌ Markdown API failed: ${error.message}`);
    return false;
  }
}

async function testCORS() {
  console.log('🧪 Testing CORS headers...');
  try {
    const response = await fetch(`${TEST_CONFIG.baseUrl}/api/blog/${TEST_CONFIG.testDate}`, {
      method: 'OPTIONS'
    });
    const corsHeaders = response.headers.get('Access-Control-Allow-Origin');
    console.log(`✅ CORS headers: ${corsHeaders}`);
    return true;
  } catch (error) {
    console.log(`❌ CORS test failed: ${error.message}`);
    return false;
  }
}

async function testCacheHeaders() {
  console.log('🧪 Testing cache headers...');
  try {
    const response = await fetch(`${TEST_CONFIG.baseUrl}/api/blog/${TEST_CONFIG.testDate}`);
    const cacheControl = response.headers.get('Cache-Control');
    const cdnCacheControl = response.headers.get('CDN-Cache-Control');
    console.log(`✅ Cache headers: ${cacheControl}`);
    console.log(`✅ CDN Cache headers: ${cdnCacheControl}`);
    return true;
  } catch (error) {
    console.log(`❌ Cache headers test failed: ${error.message}`);
    return false;
  }
}

// Main test runner
async function runTests() {
  console.log('🚀 Starting Cloudflare Worker tests...\n');
  
  const tests = [
    testHealthEndpoint,
    testBlogAPI,
    testAssetsAPI,
    testMarkdownAPI,
    testCORS,
    testCacheHeaders
  ];
  
  let passed = 0;
  let total = tests.length;
  
  for (const test of tests) {
    const result = await test();
    if (result) passed++;
    console.log(''); // Empty line for readability
  }
  
  console.log('📊 Test Results:');
  console.log(`✅ Passed: ${passed}/${total}`);
  console.log(`❌ Failed: ${total - passed}/${total}`);
  
  if (passed === total) {
    console.log('🎉 All tests passed! Worker is ready for deployment.');
  } else {
    console.log('⚠️  Some tests failed. Please check the configuration.');
  }
}

// Run tests if this script is executed directly
if (typeof window === 'undefined') {
  // Node.js environment
  const fetch = require('node-fetch');
  runTests().catch(console.error);
} else {
  // Browser environment
  runTests().catch(console.error);
}
