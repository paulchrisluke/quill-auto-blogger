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
      } else if (path.startsWith('/api/blog/')) {
        return await handleBlogAPI(request, env, requestCtx, path);
      } else if (path.startsWith('/assets/')) {
        // Simple asset serving - just remove /assets/ prefix and serve from R2
        const assetKey = path.substring(8); // Remove '/assets/' prefix
        return await serveR2Asset(env, assetKey);
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
  
  try {
    // Try to get blog content directly from R2 bucket
    const blogKey = `blogs/${date}/FINAL-BLOG-${date}.md`;
    const digestKey = `blogs/${date}/PRE-CLEANED-${date}_digest.json`;
    
    let blogContent = null;
    let digestData = null;
    
    // Try to get the final blog first
    try {
      const blogObject = await env.BLOG_BUCKET.get(blogKey);
      if (blogObject) {
        blogContent = await blogObject.text();
      }
    } catch (error) {
      console.log('Blog fetch failed', { 
        date, 
        blogKey, 
        error: error.message 
      });
    }
    
    // If we have blog content, return it
    if (blogContent) {
      const response = new Response(blogContent, {
        status: 200,
        headers: {
          'Content-Type': 'text/markdown',
          'Cache-Control': 'public, max-age=300, s-maxage=1800',
          'CDN-Cache-Control': 'public, max-age=1800',
          'Vary': 'Accept-Encoding',
          ...getCORSHeaders()
        }
      });
      
      return response;
    }
    
    // If no blog, try to get digest data
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
    
    // If we have digest data, return it
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
    
    // If neither found, return 404
    return createErrorResponse('Blog not found', 404);
    
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
    
    // Preserve query string from original request
    const searchString = ctx.url.search;
    const targetUrl = searchString ? `${apiUrl}${path}${searchString}` : `${apiUrl}${path}`;
    
    const response = await fetch(targetUrl, {
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



/**
 * Handle index page requests
 */
async function handleIndexPage(request, env) {
  try {
    // Read the index.html file
    const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quill Auto Blogger API</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #1a1a1a;
            background: #ffffff;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 60px;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 40px;
        }

        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 16px;
            color: #111827;
            font-weight: 700;
        }

        .header p {
            font-size: 1.125rem;
            color: #6b7280;
            max-width: 600px;
            margin: 0 auto;
        }

        .endpoint-section {
            margin-bottom: 60px;
        }

        .section-title {
            font-size: 1.5rem;
            font-weight: 600;
            color: #111827;
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 2px solid #f3f4f6;
        }

        .endpoint-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin-bottom: 32px;
            overflow: hidden;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        }

        .endpoint-header {
            background: #f9fafb;
            padding: 20px;
            border-bottom: 1px solid #e5e7eb;
        }

        .endpoint-title {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
        }

        .method {
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.875rem;
            margin-right: 16px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .method.get { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .method.post { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
        .method.put { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
        .method.delete { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }

        .endpoint-path {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            font-size: 1.125rem;
            color: #111827;
            font-weight: 500;
        }

        .endpoint-description {
            color: #6b7280;
            font-size: 0.875rem;
            margin-top: 8px;
        }

        .endpoint-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            padding: 24px;
        }

        .left-column {
            border-right: 1px solid #e5e7eb;
            padding-right: 24px;
        }

        .right-column {
            padding-left: 24px;
        }

        .content-section {
            margin-bottom: 24px;
        }

        .content-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: #374151;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 12px;
        }

        .content-item {
            margin-bottom: 16px;
        }

        .content-label {
            font-size: 0.875rem;
            font-weight: 500;
            color: #111827;
            margin-bottom: 4px;
        }

        .content-value {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            background: #f9fafb;
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid #e5e7eb;
            font-size: 0.875rem;
            color: #1f2937;
            word-break: break-all;
        }

        .code-block {
            background: #1f2937;
            color: #f9fafb;
            padding: 16px;
            border-radius: 6px;
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            font-size: 0.875rem;
            overflow-x: auto;
            margin-top: 8px;
        }

        .code-header {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            font-size: 0.875rem;
            font-weight: 500;
            color: #9ca3af;
        }

        .code-icon {
            margin-right: 8px;
            font-size: 1rem;
        }

        .auth-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
            margin-left: 12px;
        }

        .auth-public { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .auth-protected { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }

        .available-blogs {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 24px;
            margin-top: 24px;
        }

        .blog-card {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 20px;
        }

        .blog-title {
            font-weight: 600;
            color: #111827;
            margin-bottom: 8px;
        }

        .blog-description {
            color: #6b7280;
            font-size: 0.875rem;
            margin-bottom: 16px;
        }

        .blog-try {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            background: #ffffff;
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid #d1d5db;
            font-size: 0.875rem;
            color: #374151;
        }

        @media (max-width: 768px) {
            .endpoint-content {
                grid-template-columns: 1fr;
                gap: 24px;
            }
            
            .left-column {
                border-right: none;
                border-bottom: 1px solid #e5e7eb;
                padding-right: 0;
                padding-bottom: 24px;
            }
            
            .right-column {
                padding-left: 0;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .container {
                padding: 20px 16px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Quill Auto Blogger API</h1>
            <p>Automated blog generation from Twitch clips and GitHub activity. Access your finalized blogs through our RESTful API endpoints.</p>
        </div>

        <div class="endpoint-section">
            <h2 class="section-title">Blog Content Endpoints</h2>
            
            <!-- Get Complete Blog Data -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method get">GET</span>
                        <span class="endpoint-path">/api/blog/{date}</span>
                        <span class="auth-badge auth-public">Public</span>
                    </div>
                    <div class="endpoint-description">
                        Retrieve complete blog data including story packets, metadata, and assets
                    </div>
                </div>
                <div class="endpoint-content">
                    <div class="left-column">
                        <div class="content-section">
                            <div class="content-title">Path Parameters</div>
                            <div class="content-item">
                                <div class="content-label">date</div>
                                <div class="content-value">string (YYYY-MM-DD format)</div>
                            </div>
                        </div>
                        <div class="content-section">
                            <div class="content-title">Example</div>
                            <div class="content-item">
                                <div class="content-value">/api/blog/2025-08-29</div>
                            </div>
                        </div>
                    </div>
                    <div class="right-column">
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">💻</span>
                                cURL
                            </div>
                            <div class="code-block">curl "https://quill-blog-api.paulchrisluke.workers.dev/api/blog/2025-08-29"</div>
                        </div>
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">📄</span>
                                200 Example
                            </div>
                            <div class="code-block">{
  "date": "2025-08-29",
  "stories": [
    {
      "id": "story_20250829_pr43",
      "title": "Story Title",
      "content": "Story content...",
      "assets": {
        "video": "https://media.paulchrisluke.com/stories/2025/08/29/story_20250829_pr43.mp4",
        "images": ["..."],
        "highlights": ["..."]
      }
    }
  ]
}</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Get Blog Markdown -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method get">GET</span>
                        <span class="endpoint-path">/api/blog/{date}/markdown</span>
                        <span class="auth-badge auth-public">Public</span>
                    </div>
                    <div class="endpoint-description">
                        Retrieve just the markdown content for the blog post
                    </div>
                </div>
                <div class="endpoint-content">
                    <div class="left-column">
                        <div class="content-section">
                            <div class="content-title">Path Parameters</div>
                            <div class="content-item">
                                <div class="content-label">date</div>
                                <div class="content-value">string (YYYY-MM-DD format)</div>
                            </div>
                        </div>
                        <div class="content-section">
                            <div class="content-title">Example</div>
                            <div class="content-item">
                                <div class="content-value">/api/blog/2025-08-29/markdown</div>
                            </div>
                        </div>
                    </div>
                    <div class="right-column">
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">💻</span>
                                cURL
                            </div>
                            <div class="code-block">curl "https://quill-blog-api.paulchrisluke.workers.dev/api/blog/2025-08-29/markdown"</div>
                        </div>
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">📄</span>
                                200 Example
                            </div>
                            <div class="code-block"># Blog Post Title

This is the markdown content of the blog post...

## Story 1
Content for the first story...

## Story 2  
Content for the second story...</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Get Blog Digest -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method get">GET</span>
                        <span class="endpoint-path">/api/blog/{date}/digest</span>
                        <span class="auth-badge auth-public">Public</span>
                    </div>
                    <div class="endpoint-description">
                        Retrieve digest data with story packets and metadata
                    </div>
                </div>
                <div class="endpoint-content">
                    <div class="left-column">
                        <div class="content-section">
                            <div class="content-title">Path Parameters</div>
                            <div class="content-item">
                                <div class="content-label">date</div>
                                <div class="content-value">string (YYYY-MM-DD format)</div>
                            </div>
                        </div>
                        <div class="content-section">
                            <div class="content-title">Example</div>
                            <div class="content-item">
                                <div class="content-value">/api/blog/2025-08-29/digest</div>
                            </div>
                        </div>
                    </div>
                    <div class="right-column">
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">💻</span>
                                cURL
                            </div>
                            <div class="code-block">curl "https://quill-blog-api.paulchrisluke.workers.dev/api/blog/2025-08-29/digest"</div>
                        </div>
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">📄</span>
                                200 Example
                            </div>
                            <div class="code-block">{
  "date": "2025-08-29",
  "stories": [
    {
      "id": "story_20250829_pr43",
      "title": "Story Title",
      "summary": "Story summary...",
      "metadata": {
        "created_at": "2025-08-29T10:00:00Z",
        "tags": ["github", "twitch"]
      }
    }
  ]
}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="endpoint-section">
            <h2 class="section-title">Asset Endpoints</h2>
            
            <!-- Get All Blog Assets -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method get">GET</span>
                        <span class="endpoint-path">/api/assets/blog/{date}</span>
                        <span class="auth-badge auth-public">Public</span>
                    </div>
                    <div class="endpoint-description">
                        Retrieve all assets (images, videos, highlights) for a blog post
                    </div>
                </div>
                <div class="endpoint-content">
                    <div class="left-column">
                        <div class="content-section">
                            <div class="content-title">Path Parameters</div>
                            <div class="content-item">
                                <div class="content-label">date</div>
                                <div class="content-value">string (YYYY-MM-DD format)</div>
                            </div>
                        </div>
                        <div class="content-section">
                            <div class="content-title">Response Structure</div>
                            <div class="content-item">
                                <div class="content-value">{"video": "...", "images": [...], "highlights": [...]}</div>
                            </div>
                        </div>
                    </div>
                    <div class="right-column">
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">💻</span>
                                cURL
                            </div>
                            <div class="code-block">curl "https://quill-blog-api.paulchrisluke.workers.dev/api/assets/blog/2025-08-29"</div>
                        </div>
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">📄</span>
                                200 Example
                            </div>
                            <div class="code-block">{
  "video": "https://media.paulchrisluke.com/stories/2025/08/29/story_20250829_pr43.mp4",
  "images": [
    "https://media.paulchrisluke.com/stories/2025/08/29/story_20250829_pr43_intro.png"
  ],
  "highlights": [
    "https://media.paulchrisluke.com/stories/2025/08/29/story_20250829_pr43_hl_001.png"
  ]
}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="endpoint-section">
            <h2 class="section-title">Control Endpoints (Protected)</h2>
            
            <!-- Start Recording -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method post">POST</span>
                        <span class="endpoint-path">/control/record/start</span>
                        <span class="auth-badge auth-protected">Protected</span>
                    </div>
                    <div class="endpoint-description">
                        Start recording for a story (with optional bounded mode)
                    </div>
                </div>
                <div class="endpoint-content">
                    <div class="left-column">
                        <div class="content-section">
                            <div class="content-title">Headers</div>
                            <div class="content-item">
                                <div class="content-label">Authorization</div>
                                <div class="content-value">Bearer &lt;CONTROL_API_TOKEN&gt;</div>
                            </div>
                        </div>
                        <div class="content-section">
                            <div class="content-title">Request Body</div>
                            <div class="content-item">
                                <div class="content-label">story_id</div>
                                <div class="content-value">string</div>
                            </div>
                            <div class="content-item">
                                <div class="content-label">date</div>
                                <div class="content-value">string (YYYY-MM-DD, optional)</div>
                            </div>
                            <div class="content-item">
                                <div class="content-label">bounded</div>
                                <div class="content-value">boolean (default: false)</div>
                            </div>
                        </div>
                    </div>
                    <div class="right-column">
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">💻</span>
                                cURL
                            </div>
                            <div class="code-block">curl -X POST "https://quill-blog-api.paulchrisluke.workers.dev/control/record/start" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"story_id": "test_story", "bounded": false}'</div>
                        </div>
                        <div class="content-section">
                            <div class="code-header">
                                <span class="code-icon">📄</span>
                                200 Example
                            </div>
                            <div class="code-block">{
  "status": "started",
  "mode": "bounded",
  "story_id": "test_story",
  "prep_delay": 5,
  "duration": 15
}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="endpoint-section">
            <h2 class="section-title">Available Blogs</h2>
            <div class="available-blogs">
                <div class="blog-card">
                    <div class="blog-title">2025-08-27</div>
                    <div class="blog-description">Blog from August 27, 2025</div>
                    <div class="blog-try">/api/blog/2025-08-27</div>
                </div>
                <div class="blog-card">
                    <div class="blog-title">2025-08-29</div>
                    <div class="blog-description">Blog from August 29, 2025</div>
                    <div class="blog-try">/api/blog/2025-08-29</div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>`;

    return new Response(htmlContent, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'public, max-age=3600, s-maxage=86400', // 1 hour browser, 24 hours edge
        'CDN-Cache-Control': 'public, max-age=86400', // 24 hours edge
        'Vary': 'Accept-Encoding'
      }
    });

  } catch (error) {
    console.error('Index page error:', error);
    return createErrorResponse('Failed to serve index page', 500);
  }
}
