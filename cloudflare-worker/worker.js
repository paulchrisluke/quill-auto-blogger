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
      if (path === '/' || path === '') {
        return await handleIndexPage(request, env);
      } else if (path.startsWith('/api/blog/')) {
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
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            color: white;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .api-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }

        .endpoint-card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .endpoint-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.15);
        }

        .endpoint-header {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }

        .method {
            padding: 6px 12px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 0.9rem;
            margin-right: 15px;
            text-transform: uppercase;
        }

        .method.get { background: #10b981; color: white; }
        .method.post { background: #3b82f6; color: white; }
        .method.put { background: #f59e0b; color: white; }
        .method.delete { background: #ef4444; color: white; }

        .endpoint-path {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 1.1rem;
            color: #374151;
            flex: 1;
        }

        .auth-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
        }

        .auth-public { background: #d1fae5; color: #065f46; }
        .auth-protected { background: #fef3c7; color: #92400e; }

        .endpoint-description {
            color: #6b7280;
            margin-bottom: 15px;
            font-size: 0.95rem;
        }

        .endpoint-details {
            background: #f9fafb;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }

        .detail-item {
            margin-bottom: 10px;
        }

        .detail-label {
            font-weight: 600;
            color: #374151;
            margin-bottom: 5px;
        }

        .detail-value {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            background: white;
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid #e5e7eb;
            font-size: 0.9rem;
            color: #1f2937;
            word-break: break-all;
        }

        .example-section {
            margin-top: 20px;
        }

        .example-title {
            font-weight: 600;
            color: #374151;
            margin-bottom: 10px;
        }

        .example-code {
            background: #1f2937;
            color: #f9fafb;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.9rem;
            overflow-x: auto;
            white-space: nowrap;
        }

        .section-title {
            color: white;
            font-size: 2rem;
            margin-bottom: 20px;
            text-align: center;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }

        .footer {
            text-align: center;
            color: white;
            opacity: 0.8;
            margin-top: 40px;
            padding: 20px;
        }

        @media (max-width: 768px) {
            .api-grid {
                grid-template-columns: 1fr;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .container {
                padding: 15px;
            }
        }

        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 8px;
        }

        .status-online { background: #10b981; }
        .status-offline { background: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Quill Auto Blogger API</h1>
            <p>Automated blog generation from Twitch clips and GitHub activity</p>
        </div>

        <h2 class="section-title">📚 Blog Content Endpoints</h2>
        <div class="api-grid">
            <!-- Get Complete Blog Data -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/api/blog/{date}</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Retrieve complete blog data including story packets, metadata, and assets
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Parameters:</div>
                        <div class="detail-value">date (YYYY-MM-DD format)</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Example:</div>
                        <div class="detail-value">/api/blog/2025-08-29</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/api/blog/2025-08-29"</div>
                </div>
            </div>

            <!-- Get Blog Markdown -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/api/blog/{date}/markdown</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Retrieve just the markdown content for the blog post
                </div>
                <div class="endpoint-details">
                    <div class="endpoint-details">
                        <div class="detail-item">
                            <div class="detail-label">Parameters:</div>
                            <div class="detail-value">date (YYYY-MM-DD format)</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Example:</div>
                            <div class="detail-value">/api/blog/2025-08-29/markdown</div>
                        </div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/api/blog/2025-08-29/markdown"</div>
                </div>
            </div>

            <!-- Get Blog Digest -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/api/blog/{date}/digest</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Retrieve digest data with story packets and metadata
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Parameters:</div>
                        <div class="detail-value">date (YYYY-MM-DD format)</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Example:</div>
                        <div class="detail-value">/api/blog/2025-08-29/digest</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/api/blog/2025-08-29/digest"</div>
                </div>
            </div>

            <!-- Health Check -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/health</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Simple health check endpoint to verify API status
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Response:</div>
                        <div class="detail-value">{"status": "healthy", "timestamp": "..."}</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/health"</div>
                </div>
            </div>
        </div>

        <h2 class="section-title">🎨 Asset Endpoints</h2>
        <div class="api-grid">
            <!-- Get All Blog Assets -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/api/assets/blog/{date}</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Retrieve all assets (images, videos, highlights) for a blog post
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Parameters:</div>
                        <div class="detail-value">date (YYYY-MM-DD format)</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Response:</div>
                        <div class="detail-value">{"video": "...", "images": [...], "highlights": [...]}</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/api/assets/blog/2025-08-29"</div>
                </div>
            </div>

            <!-- Get All Story Assets -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/api/assets/stories/{date}</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Retrieve all story assets for a specific date
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Parameters:</div>
                        <div class="detail-value">date (YYYY-MM-DD format)</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Example:</div>
                        <div class="detail-value">/api/assets/stories/2025-08-29</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/api/assets/stories/2025-08-29"</div>
                </div>
            </div>

            <!-- Get Specific Story Assets -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/api/assets/stories/{date}/{story_id}</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    Retrieve assets for a specific story
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Parameters:</div>
                        <div class="detail-value">date, story_id (e.g., story_20250829_pr43)</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Example:</div>
                        <div class="detail-value">/api/assets/stories/2025-08-29/story_20250829_pr43</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/api/assets/stories/2025-08-29/story_20250829_pr43"</div>
                </div>
            </div>

            <!-- List Stories -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/stories/{date}</span>
                    <span class="auth-badge auth-public">Public</span>
                </div>
                <div class="endpoint-description">
                    List all story packets for a given date
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Parameters:</div>
                        <div class="detail-value">date (YYYY-MM-DD format)</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Response:</div>
                        <div class="detail-value">{"stories": [...]}</div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl "https://your-worker.workers.dev/stories/2025-08-29"</div>
                </div>
            </div>
        </div>

        <h2 class="section-title">🎮 Control Endpoints (Protected)</h2>
        <div class="api-grid">
            <!-- Start Recording -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/control/record/start</span>
                    <span class="auth-badge auth-protected">Protected</span>
                </div>
                <div class="endpoint-description">
                    Start recording for a story (with optional bounded mode)
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Headers:</div>
                        <div class="detail-value">Authorization: Bearer &lt;CONTROL_API_TOKEN&gt;</div>
                    </div>
                    <div class="endpoint-details">
                        <div class="detail-item">
                            <div class="detail-label">Body:</div>
                            <div class="detail-value">{"story_id": "...", "date": "...", "bounded": false}</div>
                        </div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl -X POST "https://your-worker.workers.dev/control/record/start" \\<br>&nbsp;&nbsp;-H "Authorization: Bearer YOUR_TOKEN" \\<br>&nbsp;&nbsp;-H "Content-Type: application/json" \\<br>&nbsp;&nbsp;-d '{"story_id": "test_story", "bounded": false}'</div>
                </div>
            </div>

            <!-- Stop Recording -->
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/control/record/stop</span>
                    <span class="auth-badge auth-protected">Protected</span>
                </div>
                <div class="endpoint-description">
                    Stop recording for a story
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Headers:</div>
                        <div class="detail-value">Authorization: Bearer &lt;CONTROL_API_TOKEN&gt;</div>
                    </div>
                    <div class="endpoint-details">
                        <div class="detail-item">
                            <div class="detail-label">Body:</div>
                            <div class="detail-value">{"story_id": "...", "date": "..."}</div>
                        </div>
                    </div>
                </div>
                <div class="example-section">
                    <div class="example-title">cURL Example:</div>
                    <div class="example-code">curl -X POST "https://your-worker.workers.dev/control/record/stop" \\<br>&nbsp;&nbsp;-H "Authorization: Bearer YOUR_TOKEN" \\<br>&nbsp;&nbsp;-H "Content-Type: application/json" \\<br>&nbsp;&nbsp;-d '{"story_id": "test_story"}'</div>
                </div>
            </div>
        </div>

        <h2 class="section-title">📊 Available Blogs</h2>
        <div class="api-grid">
            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">2025-08-27</span>
                    <span class="status-indicator status-online"></span>
                </div>
                <div class="endpoint-description">
                    Blog from August 27, 2025
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Try it:</div>
                        <div class="detail-value">/api/blog/2025-08-27</div>
                    </div>
                </div>
            </div>

            <div class="endpoint-card">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">2025-08-29</span>
                    <span class="status-indicator status-online"></span>
                </div>
                <div class="endpoint-description">
                    Blog from August 27, 2025
                </div>
                <div class="endpoint-description">
                    Blog from August 29, 2025
                </div>
                <div class="endpoint-details">
                    <div class="detail-item">
                        <div class="detail-label">Try it:</div>
                        <div class="detail-value">/api/blog/2025-08-29</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>🚀 Quill Auto Blogger API - Automated blog generation from Twitch clips and GitHub activity</p>
            <p>Built with FastAPI and Cloudflare Workers</p>
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
