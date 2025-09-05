export default {
  async fetch(request, env, ctx) {
    try {
      const url = new URL(request.url);
      const path = url.pathname;
      const hostname = url.hostname;

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
        hostname,
        waitUntil: ctx.waitUntil
      };
      
      // Route based on domain
      if (hostname === 'media.paulchrisluke.com') {
        // Media domain - serve assets only
        return await handleMediaDomain(request, env, path);
      } else if (hostname === 'api.paulchrisluke.com' || hostname === 'quill-blog-api.paulchrisluke.workers.dev') {
        // API domain - serve all API endpoints
        return await handleApiDomain(request, env, path);
      } else {
        // Default to API domain behavior
        return await handleApiDomain(request, env, path);
      }
    } catch (error) {
      console.error('Worker error:', error);
      return createErrorResponse('Internal Server Error', 500);
    }
  }
};

/**
 * Handle media domain requests (media.paulchrisluke.com)
 */
async function handleMediaDomain(request, env, path) {
  // Media domain serves assets only
  if (path === '/health') {
    return new Response('OK', { 
      status: 200,
      headers: getCORSHeaders()
    });
  } else if (path.startsWith('/stories/') || path.startsWith('/assets/') || path === '/pcl-labs-logo.svg') {
    // Serve media assets directly from R2
    const assetKey = path.startsWith('/assets/') ? path.substring(8) : path.substring(1);
    return await serveR2Asset(env, assetKey, request);
  } else {
    return createErrorResponse('Not Found', 404, 'media');
  }
}

/**
 * Handle API domain requests (api.paulchrisluke.com and quill-blog-api.paulchrisluke.workers.dev)
 */
async function handleApiDomain(request, env, path) {
  // Route requests based on path
  if (path === '/' || path === '') {
    return await handleIndexPage(request, env);
  } else if (path === '/favicon.ico') {
    // Serve favicon directly from R2
    return await serveR2Asset(env, 'favicon.ico', request);
  } else if (path === '/pcl-labs-logo.svg') {
    // Serve logo directly from R2
    return await serveR2Asset(env, 'pcl-labs-logo.svg', request);
  } else if (path === '/blogs') {
    // Serve blogs index
    return await handleBlogsIndex(request, env);
  } else if (path === '/rss.xml') {
    // Serve RSS feed
    return await handleRSSFeed(request, env);
  } else if (path === '/sitemap.xml') {
    // Serve sitemap
    return await handleSitemap(request, env);
  } else if (path === '/blogs/index.json') {
    // Serve blogs index JSON
    return await handleBlogsIndex(request, env);
  } else if (path.startsWith('/blogs/')) {
    // Serve raw JSON files directly from R2
    // Handle both formats: /blogs/2025-08-29.json and /blogs/2025-08-29/2025-08-29_page.publish.json
    const blogPath = path.substring(1); // Remove leading slash
    console.log('Blog request - path:', path, 'blogPath:', blogPath);
    if (blogPath.endsWith('.json') && blogPath.startsWith('blogs/') && blogPath.split('/').length === 2) {
      // Format: blogs/2025-08-29.json -> blogs/2025-08-29/2025-08-29_page.publish.json
      const date = blogPath.replace('blogs/', '').replace('.json', '');
      const r2Key = `blogs/${date}/${date}_page.publish.json`;
      console.log('Transforming blog path - date:', date, 'r2Key:', r2Key);
      return await serveR2Asset(env, r2Key, request);
    } else {
      // Direct path format
      console.log('Using direct blog path:', blogPath);
      return await serveR2Asset(env, blogPath, request);
    }
  } else if (path.startsWith('/stories/')) {
    // Story media serving - serve directly from R2
    const assetKey = path.substring(1); // Remove leading '/' but keep 'stories/'
    console.log('Story asset request:', path, '-> R2 key:', assetKey);
    return await serveR2Asset(env, assetKey, request);
  } else if (path.startsWith('/assets/')) {
    // Asset serving - keep the full path including 'assets/' for R2
    const assetKey = path.substring(1); // Remove leading '/' but keep 'assets/'
    console.log('Asset request:', path, '-> R2 key:', assetKey);
    return await serveR2Asset(env, assetKey, request);
  } else if (path === '/health') {
    return new Response('OK', { 
      status: 200,
      headers: getCORSHeaders()
    });
  } else {
    return createErrorResponse('Not Found', 404);
  }
}

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
function createErrorResponse(message, status, cacheTag = null) {
  const headers = getCORSHeaders();
  if (cacheTag) {
    headers['Cache-Tag'] = cacheTag;
  }
  return new Response(message, { 
    status,
    headers
  });
}

/**
 * Serve static assets directly from R2 (for future use)
 */
async function serveR2Asset(env, key, request) {
  try {
    console.log('serveR2Asset: Looking for key:', key);
    const object = await env.BLOG_BUCKET.get(key);
    
    if (!object) {
      console.log('serveR2Asset: Object not found for key:', key);
      return createErrorResponse('Asset not found', 404, 'assets');
    }
    
    console.log('serveR2Asset: Found object for key:', key);
    
    const headers = new Headers();
    
    // Enhanced cache headers for Milestone 7
    const ext = key.split('.').pop().toLowerCase();
    if (ext === 'mp4') {
      headers.set('Content-Type', 'video/mp4');
      headers.set('Cache-Control', 'public, max-age=86400, s-maxage=86400'); // 24 hours
      headers.set('CDN-Cache-Control', 'public, max-age=86400'); // 24 hours edge
      headers.set('Cache-Tag', 'video,assets');
    } else if (['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(ext)) {
      headers.set('Content-Type', ext === 'svg' ? 'image/svg+xml' : `image/${ext === 'jpg' ? 'jpeg' : ext}`);
      headers.set('Cache-Control', 'public, max-age=86400, s-maxage=86400'); // 24 hours
      headers.set('CDN-Cache-Control', 'public, max-age=86400'); // 24 hours edge
      headers.set('Cache-Tag', 'image,assets');
    } else if (ext === 'json') {
      headers.set('Content-Type', 'application/json');
      headers.set('Cache-Control', 'public, max-age=300, s-maxage=1800'); // 5 min browser, 30 min edge
      headers.set('CDN-Cache-Control', 'public, max-age=1800'); // 30 min edge
      headers.set('Cache-Tag', 'json,assets');
      
      // Add SEO headers for blog JSON files
      if (key.includes('_page.publish.json')) {
        // Set SEO headers without parsing JSON to avoid consuming the body
        headers.set('X-Robots-Tag', 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1');
        headers.set('X-Content-Type-Options', 'nosniff');
        headers.set('X-Frame-Options', 'SAMEORIGIN');
        headers.set('X-XSS-Protection', '1; mode=block');
        headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
      }
    } else if (ext === 'xml') {
      headers.set('Content-Type', 'application/xml');
      headers.set('Cache-Control', 'public, max-age=3600, s-maxage=86400'); // 1 hour browser, 24 hours edge
      headers.set('CDN-Cache-Control', 'public, max-age=86400'); // 24 hours edge
      headers.set('Cache-Tag', 'xml,assets');
    } else {
      headers.set('Content-Type', 'application/octet-stream');
      headers.set('Cache-Control', 'public, max-age=300, s-maxage=1800'); // 5 min browser, 30 min edge
      headers.set('CDN-Cache-Control', 'public, max-age=1800'); // 30 min edge
      headers.set('Cache-Tag', 'assets');
    }
    
    // Add CORS headers early, before any conditional checks
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    // Set standard validator headers using R2's metadata
    if (object.httpEtag) {
      headers.set('ETag', object.httpEtag);
    }
    if (object.uploaded) {
      headers.set('Last-Modified', new Date(object.uploaded).toUTCString());
    }
    
    // Check conditional requests to avoid egress
    const ifNoneMatch = request.headers.get('If-None-Match');
    const ifModifiedSince = request.headers.get('If-Modified-Since');
    
    if (ifNoneMatch && object.httpEtag && ifNoneMatch === object.httpEtag) {
      // ETag matches, return 304 Not Modified
      return new Response(null, {
        status: 304,
        headers: headers
      });
    }
    
    if (ifModifiedSince && object.uploaded) {
      const ifModifiedDate = new Date(ifModifiedSince);
      const uploadedDate = new Date(object.uploaded);
      if (uploadedDate <= ifModifiedDate) {
        // Object hasn't been modified, return 304 Not Modified
        return new Response(null, {
          status: 304,
          headers: headers
        });
      }
    }
    
    // Get the body stream - this can only be called once
    const body = await object.body;
    
    return new Response(body, {
      headers,
      status: 200
    });
    
  } catch (error) {
    console.error('R2 asset error:', error);
    return createErrorResponse('Failed to serve asset', 500, 'assets');
  }
}

/**
 * Handle blogs index requests
 */
async function handleBlogsIndex(request, env) {
  try {
    // Serve the blogs index JSON file
    const indexObject = await env.BLOG_BUCKET.get('blogs/index.json');
    
    if (!indexObject) {
      return createErrorResponse('Blogs index not found', 404, 'blogs-index');
    }
    
    const headers = new Headers({
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'public, max-age=300, s-maxage=1800', // 5 min browser, 30 min edge
      'CDN-Cache-Control': 'public, max-age=1800', // 30 min edge
      'Cache-Tag': 'blogs-index',
      'Vary': 'Accept-Encoding'
    });
    
    // Add CORS headers early, before any conditional checks
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    // Set standard validator headers using R2's metadata
    if (indexObject.httpEtag) {
      headers.set('ETag', indexObject.httpEtag);
    }
    if (indexObject.uploaded) {
      headers.set('Last-Modified', new Date(indexObject.uploaded).toUTCString());
    }
    
    // Check conditional requests to avoid egress
    const ifNoneMatch = request.headers.get('If-None-Match');
    const ifModifiedSince = request.headers.get('If-Modified-Since');
    
    if (ifNoneMatch && indexObject.httpEtag && ifNoneMatch === indexObject.httpEtag) {
      // ETag matches, return 304 Not Modified
      return new Response(null, {
        status: 304,
        headers: headers
      });
    }
    
    if (ifModifiedSince && indexObject.uploaded) {
      const ifModifiedDate = new Date(ifModifiedSince);
      const uploadedDate = new Date(indexObject.uploaded);
      if (uploadedDate <= ifModifiedDate) {
        // Object hasn't been modified, return 304 Not Modified
        return new Response(null, {
          status: 304,
          headers: headers
        });
      }
    }
    
    const jsonContent = await indexObject.text();
    
    return new Response(jsonContent, {
      status: 200,
      headers: headers
    });

  } catch (error) {
    console.error('Blogs index error:', error);
    return createErrorResponse('Failed to serve blogs index', 500, 'blogs-index');
  }
}

/**
 * Handle RSS feed requests
 */
async function handleRSSFeed(request, env) {
  try {
    // Serve the RSS feed XML file
    const rssObject = await env.BLOG_BUCKET.get('rss.xml');
    
    if (!rssObject) {
      return createErrorResponse('RSS feed not found', 404, 'rss,feeds');
    }
    
    const headers = new Headers({
      'Content-Type': 'application/rss+xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=86400', // 1 hour browser, 24 hours edge
      'CDN-Cache-Control': 'public, max-age=86400', // 24 hours edge
      'Cache-Tag': 'rss,feeds',
      'Vary': 'Accept-Encoding'
    });
    
    // Add CORS headers early, before any conditional checks
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    // Set standard validator headers using R2's metadata
    if (rssObject.httpEtag) {
      headers.set('ETag', rssObject.httpEtag);
    }
    if (rssObject.uploaded) {
      headers.set('Last-Modified', new Date(rssObject.uploaded).toUTCString());
    }
    
    // Check conditional requests to avoid egress
    const ifNoneMatch = request.headers.get('If-None-Match');
    const ifModifiedSince = request.headers.get('If-Modified-Since');
    
    if (ifNoneMatch && rssObject.httpEtag && ifNoneMatch === rssObject.httpEtag) {
      // ETag matches, return 304 Not Modified
      return new Response(null, {
        status: 304,
        headers: headers
      });
    }
    
    if (ifModifiedSince && rssObject.uploaded) {
      const ifModifiedDate = new Date(ifModifiedSince);
      const uploadedDate = new Date(rssObject.uploaded);
      if (uploadedDate <= ifModifiedDate) {
        // Object hasn't been modified, return 304 Not Modified
        return new Response(null, {
          status: 304,
          headers: headers
        });
      }
    }
    
    const xmlContent = await rssObject.text();
    
    return new Response(xmlContent, {
      status: 200,
      headers: headers
    });

  } catch (error) {
    console.error('RSS feed error:', error);
    return createErrorResponse('Failed to serve RSS feed', 500, 'rss,feeds');
  }
}

/**
 * Handle sitemap requests
 */
async function handleSitemap(request, env) {
  try {
    // Serve the sitemap XML file
    const sitemapObject = await env.BLOG_BUCKET.get('sitemap.xml');
    
    if (!sitemapObject) {
      return createErrorResponse('Sitemap not found', 404, 'sitemap,feeds');
    }
    
    const headers = new Headers({
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=86400', // 1 hour browser, 24 hours edge
      'CDN-Cache-Control': 'public, max-age=86400', // 24 hours edge
      'Cache-Tag': 'sitemap,feeds',
      'Vary': 'Accept-Encoding'
    });
    
    // Add CORS headers early, before any conditional checks
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    // Set standard validator headers using R2's metadata
    if (sitemapObject.httpEtag) {
      headers.set('ETag', sitemapObject.httpEtag);
    }
    if (sitemapObject.uploaded) {
      headers.set('Last-Modified', new Date(sitemapObject.uploaded).toUTCString());
    }
    
    // Check conditional requests to avoid egress
    const ifNoneMatch = request.headers.get('If-None-Match');
    const ifModifiedSince = request.headers.get('If-Modified-Since');
    
    if (ifNoneMatch && sitemapObject.httpEtag && ifNoneMatch === sitemapObject.httpEtag) {
      // ETag matches, return 304 Not Modified
      return new Response(null, {
        status: 304,
        headers: headers
      });
    }
    
    if (ifModifiedSince && sitemapObject.uploaded) {
      const ifModifiedDate = new Date(ifModifiedSince);
      const uploadedDate = new Date(sitemapObject.uploaded);
      if (uploadedDate <= ifModifiedDate) {
        // Object hasn't been modified, return 304 Not Modified
        return new Response(null, {
          status: 304,
          headers: headers
        });
      }
    }
    
    const xmlContent = await sitemapObject.text();
    
    return new Response(xmlContent, {
      status: 200,
      headers: headers
    });

  } catch (error) {
    console.error('Sitemap error:', error);
    return createErrorResponse('Failed to serve sitemap', 500, 'sitemap,feeds');
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
      return createErrorResponse('Index page not found', 404, 'index,html');
    }
    
    const headers = new Headers({
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=86400', // 1 hour browser, 24 hours edge
      'CDN-Cache-Control': 'public, max-age=86400', // 24 hours edge
      'Cache-Tag': 'index,html',
      'Vary': 'Accept-Encoding'
    });
    
    // Add CORS headers early, before any conditional checks
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    // Set standard validator headers using R2's metadata
    if (indexObject.httpEtag) {
      headers.set('ETag', indexObject.httpEtag);
    }
    if (indexObject.uploaded) {
      headers.set('Last-Modified', new Date(indexObject.uploaded).toUTCString());
    }
    
    // Check conditional requests to avoid egress
    const ifNoneMatch = request.headers.get('If-None-Match');
    const ifModifiedSince = request.headers.get('If-Modified-Since');
    
    if (ifNoneMatch && indexObject.httpEtag && ifNoneMatch === indexObject.httpEtag) {
      // ETag matches, return 304 Not Modified
      return new Response(null, {
        status: 304,
        headers: headers
      });
    }
    
    if (ifModifiedSince && indexObject.uploaded) {
      const ifModifiedDate = new Date(ifModifiedSince);
      const uploadedDate = new Date(indexObject.uploaded);
      if (uploadedDate <= ifModifiedDate) {
        // Object hasn't been modified, return 304 Not Modified
        return new Response(null, {
          status: 304,
          headers: headers
        });
      }
    }
    
    const htmlContent = await indexObject.text();
    
    return new Response(htmlContent, {
      status: 200,
      headers: headers
    });

  } catch (error) {
    console.error('Index page error:', error);
    return createErrorResponse('Failed to serve index page', 500, 'index,html');
  }
}


