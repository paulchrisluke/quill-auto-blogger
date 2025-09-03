export default {
  async fetch(request, env, ctx) {
    try {
      const url = new URL(request.url);
      const path = url.pathname;

      // Handle CORS preflight
      if (request.method === 'OPTIONS') {
        return handleCORS();
      }

      // Build context object with shared state
      const requestCtx = {
        request,
        env,
        path,
        url,
        waitUntil: ctx.waitUntil
      };
      
      // Route requests based on path
      if (path === '/' || path === '') {
        return await handleIndexPage(request, env);
      } else if (path.startsWith('/blog/')) {
        return await handleBlogAPI(request, env, requestCtx, path);
      } else if (path.startsWith('/assets/')) {
        // Simple asset serving - just remove /assets/ prefix and serve from R2
        const assetKey = path.substring(8); // Remove '/assets/' prefix
        return await serveR2Asset(env, assetKey);
      } else if (path === '/health') {
        return new Response('OK', { 
          status: 200,
          headers: getCORSHeaders()
        });
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
 * Handle blog API requests with edge caching
 * 
 * Pure JSON approach: Serves digest data directly as JSON.
 * Frontend handles rendering and HTML generation.
 * JSON-LD schema data is included in the digest frontmatter.
 */
async function handleBlogAPI(request, env, ctx, path) {
  const segments = path.split('/');
  const date = segments[2]; // For /blog/2025-08-27, date is at index 2
  
  if (!date || segments.length < 3) {
    return createErrorResponse('Invalid blog path', 400);
  }
  
  // Validate date format (YYYY-MM-DD)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return createErrorResponse('Invalid date format. Use YYYY-MM-DD', 400);
  }
  
  try {
    // Get digest data from R2 bucket (primary data source)
    const digestKey = `blogs/${date}/FINAL-${date}_digest.json`;
    
    let digestData = null;
    
    // Try to get the digest data
    try {
      const digestObject = await env.BLOG_BUCKET.get(digestKey);
      if (digestObject) {
        digestData = await digestObject.json();
      }
    } catch (error) {
      console.log('Digest fetch failed', { 
        date, 
        digestKey, 
        error: error.message 
      });
    }
    
    // If we have digest data, return it as JSON
    if (digestData) {
      const response = new Response(JSON.stringify(digestData), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=300, s-maxage=1800',
          'CDN-Cache-Control': 'public, max-age=1800',
          'Vary': 'Accept-Encoding',
          ...getCORSHeaders()
        }
      });
      
      return response;
    }
    
    // If no digest found, return 404
    return createErrorResponse('Blog not found', 404);
    
  } catch (error) {
    console.error('Blog API error:', error);
    return createErrorResponse('Failed to fetch blog data', 500);
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

/**
 * Handle index page requests
 */
async function handleIndexPage(request, env) {
  try {
    // Serve the static index.html file
    const indexObject = await env.BLOG_BUCKET.get('index.html');
    
    if (!indexObject) {
      return createErrorResponse('Index page not found', 404);
    }
    
    const htmlContent = await indexObject.text();
    
    return new Response(htmlContent, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'public, max-age=3600, s-maxage=86400', // 1 hour browser, 24 hours edge
        'CDN-Cache-Control': 'public, max-age=86400', // 24 hours edge
        'Vary': 'Accept-Encoding',
        ...getCORSHeaders()
      }
    });

  } catch (error) {
    console.error('Index page error:', error);
    return createErrorResponse('Failed to serve index page', 500);
  }
}
