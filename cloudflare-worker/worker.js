/**
 * Cloudflare Worker for Quill Auto Blogger
 * Serves blog posts and assets from R2 storage with edge caching
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return handleCORS();
    }
    
    try {
      // Route requests based on path
      if (path.startsWith('/api/blog/')) {
        return await handleBlogAPI(request, env, path);
      } else if (path.startsWith('/api/assets/')) {
        return await handleAssetsAPI(request, env, path);
      } else if (path === '/health') {
        return new Response('OK', { status: 200 });
      } else {
        return new Response('Not Found', { status: 404 });
      }
    } catch (error) {
      console.error('Worker error:', error);
      return new Response('Internal Server Error', { status: 500 });
    }
  }
};

/**
 * Handle CORS preflight requests
 */
function handleCORS() {
  return new Response(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
    }
  });
}

/**
 * Add CORS headers to responses
 */
function addCORSHeaders(response) {
  const newResponse = new Response(response.body, response);
  newResponse.headers.set('Access-Control-Allow-Origin', '*');
  newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  newResponse.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  return newResponse;
}

/**
 * Handle blog API requests
 */
async function handleBlogAPI(request, env, path) {
  const segments = path.split('/');
  const date = segments[3];
  
  if (!date || segments.length < 4) {
    return new Response('Invalid blog path', { status: 400 });
  }
  
  // Validate date format (YYYY-MM-DD)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return new Response('Invalid date format. Use YYYY-MM-DD', { status: 400 });
  }
  
  try {
    // Forward request to your local API server
    const apiUrl = env.LOCAL_API_URL || 'http://localhost:8000';
    const response = await fetch(`${apiUrl}${path}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${env.WORKER_BEARER_TOKEN}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      return new Response(`API Error: ${response.statusText}`, { 
        status: response.status 
      });
    }
    
    const data = await response.json();
    
    // Cache the response at the edge
    const cacheResponse = new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300, s-maxage=3600', // 5 min browser, 1 hour edge
        'CDN-Cache-Control': 'public, max-age=3600', // 1 hour edge
        'Vary': 'Accept-Encoding'
      }
    });
    
    return addCORSHeaders(cacheResponse);
    
  } catch (error) {
    console.error('Blog API error:', error);
    return new Response('Failed to fetch blog data', { status: 500 });
  }
}

/**
 * Handle assets API requests
 */
async function handleAssetsAPI(request, env, path) {
  const segments = path.split('/');
  
  if (segments.length < 4) {
    return new Response('Invalid assets path', { status: 400 });
  }
  
  try {
    // Forward request to your local API server
    const apiUrl = env.LOCAL_API_URL || 'http://localhost:8000';
    const response = await fetch(`${apiUrl}${path}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${env.WORKER_BEARER_TOKEN}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      return new Response(`API Error: ${response.statusText}`, { 
        status: response.status 
      });
    }
    
    const data = await response.json();
    
    // Cache the response at the edge
    const cacheResponse = new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300, s-maxage=1800', // 5 min browser, 30 min edge
        'CDN-Cache-Control': 'public, max-age=1800', // 30 min edge
        'Vary': 'Accept-Encoding'
      }
    });
    
    return addCORSHeaders(cacheResponse);
    
  } catch (error) {
    console.error('Assets API error:', error);
    return new Response('Failed to fetch assets data', { status: 500 });
  }
}

/**
 * Serve static assets directly from R2 (for future use)
 */
async function serveR2Asset(env, key) {
  try {
    const object = await env.BLOG_BUCKET.get(key);
    
    if (!object) {
      return new Response('Asset not found', { status: 404 });
    }
    
    const headers = new Headers();
    headers.set('Cache-Control', 'public, max-age=86400, s-maxage=86400'); // 24 hours
    headers.set('CDN-Cache-Control', 'public, max-age=86400'); // 24 hours edge
    
    // Set content type based on file extension
    const ext = key.split('.').pop().toLowerCase();
    if (ext === 'mp4') {
      headers.set('Content-Type', 'video/mp4');
    } else if (['png', 'jpg', 'jpeg', 'gif'].includes(ext)) {
      headers.set('Content-Type', `image/${ext === 'jpg' ? 'jpeg' : ext}`);
    }
    
    return new Response(object.body, {
      headers,
      status: 200
    });
    
  } catch (error) {
    console.error('R2 asset error:', error);
    return new Response('Failed to serve asset', { status: 500 });
  }
}
