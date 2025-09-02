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
      // Build context object with shared state
      const requestCtx = {
        request,
        env,
        path,
        url,
        waitUntil: ctx.waitUntil
      };
      
      // Route requests based on path
      if (path.startsWith('/api/blog/')) {
        return await handleBlogAPI(request, env, requestCtx, path);
      } else if (path.startsWith('/api/assets/')) {
        return await handleAssetsAPI(request, env, requestCtx, path);
      } else if (path === '/health') {
        return new Response('OK', { status: 200 });
      } else {
        return createErrorResponse('Not Found', 404);
      }
    } catch (error) {
      console.error('Worker error:', error);
      return createErrorResponse('Internal Server Error', 500);
    }
  }
};

/**
 * Handle CORS preflight requests
 */
function handleCORS() {
  return new Response(null, {
    status: 200,
    headers: getCORSHeaders()
  });
}

/**
 * Get standard CORS headers
 */
function getCORSHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}

/**
 * Create error response with CORS headers
 */
function createErrorResponse(message, status) {
  return new Response(message, { 
    status,
    headers: getCORSHeaders()
  });
}

/**
 * Add CORS headers to responses
 */
function addCORSHeaders(response) {
  const newResponse = new Response(response.body, response);
  Object.entries(getCORSHeaders()).forEach(([key, value]) => {
    newResponse.headers.set(key, value);
  });
  return newResponse;
}

/**
 * Handle blog API requests with edge caching
 */
async function handleBlogAPI(request, env, ctx, path) {
  const segments = path.split('/');
  const date = segments[3];
  
  if (!date || segments.length < 4) {
    return createErrorResponse('Invalid blog path', 400);
  }
  
  // Validate date format (YYYY-MM-DD)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return createErrorResponse('Invalid date format. Use YYYY-MM-DD', 400);
  }
  
  // Check cache first
  const cache = caches.default;
  const cacheKey = new Request(request.url);
  const cachedResponse = await cache.match(cacheKey);
  
  if (cachedResponse) {
    return addCORSHeaders(cachedResponse);
  }
  
  try {
    // Forward request to your local API server
    const apiUrl = env.LOCAL_API_URL || 'http://localhost:8000';
    
    // Build headers conditionally
    const headers = {
      'Content-Type': 'application/json'
    };
    
    // Only add Authorization header if token is defined and non-empty
    if (env.WORKER_BEARER_TOKEN && env.WORKER_BEARER_TOKEN.trim() !== '') {
      headers['Authorization'] = `Bearer ${env.WORKER_BEARER_TOKEN}`;
    }
    
    const response = await fetch(`${apiUrl}${path}`, {
      method: 'GET',
      headers
    });
    
    if (!response.ok) {
      return createErrorResponse(`API Error: ${response.statusText}`, response.status);
    }
    
    const data = await response.json();
    
    // Create response with caching headers
    const cacheResponse = new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300, s-maxage=3600', // 5 min browser, 1 hour edge
        'CDN-Cache-Control': 'public, max-age=3600', // 1 hour edge
        'Vary': 'Accept-Encoding',
        ...getCORSHeaders()
      }
    });
    
    // Store in cache
    ctx.waitUntil(cache.put(cacheKey, cacheResponse.clone()));
    
    return cacheResponse;
    
  } catch (error) {
    console.error('Blog API error:', error);
    return createErrorResponse('Failed to fetch blog data', 500);
  }
}

/**
 * Handle assets API requests with edge caching
 */
async function handleAssetsAPI(request, env, ctx, path) {
  const segments = path.split('/');
  
  if (segments.length < 4) {
    return createErrorResponse('Invalid assets path', 400);
  }
  
  // Check cache first
  const cache = caches.default;
  const cacheKey = new Request(request.url);
  const cachedResponse = await cache.match(cacheKey);
  
  if (cachedResponse) {
    return addCORSHeaders(cachedResponse);
  }
  
  try {
    // Forward request to your local API server
    const apiUrl = env.LOCAL_API_URL || 'http://localhost:8000';
    
    // Build headers conditionally
    const headers = {
      'Content-Type': 'application/json'
    };
    
    // Only add Authorization header if token is defined and non-empty
    if (env.WORKER_BEARER_TOKEN && env.WORKER_BEARER_TOKEN.trim() !== '') {
      headers['Authorization'] = `Bearer ${env.WORKER_BEARER_TOKEN}`;
    }
    
    const response = await fetch(`${apiUrl}${path}`, {
      method: 'GET',
      headers
    });
    
    if (!response.ok) {
      return createErrorResponse(`API Error: ${response.statusText}`, response.status);
    }
    
    const data = await response.json();
    
    // Create response with caching headers
    const cacheResponse = new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300, s-maxage=1800', // 5 min browser, 30 min edge
        'CDN-Cache-Control': 'public, max-age=1800', // 30 min edge
        'Vary': 'Accept-Encoding',
        ...getCORSHeaders()
      }
    });
    
    // Store in cache
    ctx.waitUntil(cache.put(cacheKey, cacheResponse.clone()));
    
    return cacheResponse;
    
  } catch (error) {
    console.error('Assets API error:', error);
    return createErrorResponse('Failed to fetch assets data', 500);
  }
}

/**
 * Serve static assets directly from R2 (for future use)
 */
async function serveR2Asset(env, key) {
  try {
    const object = await env.BLOG_BUCKET.get(key);
    
    if (!object) {
      return createErrorResponse('Asset not found', 404);
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
    
    // Add CORS headers
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    return new Response(object.body, {
      headers,
      status: 200
    });
    
  } catch (error) {
    console.error('R2 asset error:', error);
    return createErrorResponse('Failed to serve asset', 500);
  }
}
