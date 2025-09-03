/// <reference types="@cloudflare/workers-types" />

/**
 * Main Cloudflare Worker for M6 Distribution & Discovery
 * Routes requests to appropriate handlers with edge caching and conditional GET support
 */

import { handleBlogRequest, handleCanonicalRedirect } from './routes/blog';
import { handleControlRequest } from './routes/control';
import { handleSitemapRequest } from './routes/sitemap';
import { handleFeedRequest } from './routes/feeds';
import { handleIndexRequest } from './routes/index';
import { handleRobotsRequest } from './routes/robots';
import { setContentTypeCacheHeaders } from './lib/cache';
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    try {
      const url = new URL(request.url);
      const path = url.pathname;

      // Handle CORS preflight
      if (request.method === 'OPTIONS') {
        return handleCORS();
      }

      // Route requests based on path
      
      // Canonical redirects (must come first)
      const canonicalRedirect = handleCanonicalRedirect(path);
      if (canonicalRedirect) {
        return canonicalRedirect;
      }
      
      // Main routes
      if (path === '/' || path === '') {
        return await handleIndexPage(request, env);
      } else if (path.startsWith('/blog/')) {
        return await handleBlogRequest(request, env, path);
      } else if (path.startsWith('/blogs')) {
        return await handleIndexRequest(request, env, path);
      } else if (path.startsWith('/control/')) {
        return await handleControlRequest(request, env, path);
      } else if (path.startsWith('/sitemap') || path === '/sitemap.xml') {
        return await handleSitemapRequest(request, env, path);
      } else if (path.startsWith('/feed.')) {
        return await handleFeedRequest(request, env, path);
      } else if (path === '/robots.txt') {
        return await handleRobotsRequest(request, env, path);
      } else if (path.startsWith('/assets/')) {
        // Secure asset serving with path traversal protection
        const assetKey = validateAssetKey(path);
        if (assetKey) {
          return await serveR2Asset(env, assetKey);
        } else {
          return createErrorResponse('Invalid asset path', 400);
        }
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
function handleCORS(): Response {
  return new Response(null, {
    status: 200,
    headers: getCORSHeaders()
  });
}

/**
 * Get standard CORS headers
 */
function getCORSHeaders(): Record<string, string> {
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
function createErrorResponse(message: string, status: number): Response {
  return new Response(message, { 
    status,
    headers: getCORSHeaders()
  });
}

/**
 * Validate and normalize asset key to prevent path traversal attacks
 */
function validateAssetKey(path: string): string | null {
  try {
    // Decode the URL-encoded path
    const decodedPath = decodeURIComponent(path);
    
    // Remove '/assets/' prefix
    if (!decodedPath.startsWith('/assets/')) {
      return null;
    }
    
    let assetKey = decodedPath.substring(8); // Remove '/assets/' prefix
    
    // Handle empty keys
    if (!assetKey || assetKey === '') {
      assetKey = 'index.html';
    }
    
    // Normalize the path using POSIX-style normalization
    // Split by '/' and filter out empty segments and '..' segments
    const segments = assetKey.split('/').filter(segment => 
      segment !== '' && segment !== '.' && segment !== '..'
    );
    
    // Reject if the normalized path contains any '..' segments
    if (assetKey.includes('..')) {
      return null;
    }
    
    // Reject if the path starts with '/' or contains null bytes
    if (assetKey.startsWith('/') || assetKey.includes('\0')) {
      return null;
    }
    
    // Reject if the path resolves outside the expected assets root
    if (segments.length === 0) {
      assetKey = 'index.html';
    } else {
      assetKey = segments.join('/');
    }
    
    // Optional: Enforce allowlist for permitted characters
    // Only allow alphanumeric, hyphens, underscores, dots, and forward slashes
    if (!/^[a-zA-Z0-9\-_.\/]+$/.test(assetKey)) {
      return null;
    }
    
    return assetKey;
    
  } catch (error) {
    console.error('Asset key validation error:', error);
    return null;
  }
}

/**
 * Serve static assets directly from R2 with proper caching
 */
async function serveR2Asset(env: Env, key: string): Promise<Response> {
  try {
    const object = await env.BLOG_BUCKET.get(key);
    
    if (!object) {
      return createErrorResponse('Asset not found', 404);
    }
    
    const headers = new Headers();
    
    // Set content type based on file extension
    const ext = key.split('.').pop()?.toLowerCase();
    let contentType = 'application/octet-stream';
    
    if (ext === 'mp4') {
      contentType = 'video/mp4';
    } else if (['png', 'jpg', 'jpeg', 'gif'].includes(ext || '')) {
      contentType = `image/${ext === 'jpg' ? 'jpeg' : ext}`;
    } else if (ext === 'css') {
      contentType = 'text/css';
    } else if (ext === 'js') {
      contentType = 'application/javascript';
    } else if (ext === 'html') {
      contentType = 'text/html';
    }
    
    headers.set('Content-Type', contentType);
    
    // Add CORS headers
    Object.entries(getCORSHeaders()).forEach(([key, value]) => {
      headers.set(key, value);
    });
    
    const response = new Response(object.body, {
      headers,
      status: 200
    });
    
    // Set appropriate cache headers based on content type
    setContentTypeCacheHeaders(response, contentType);
    
    return response;
    
  } catch (error) {
    console.error('R2 asset error:', error);
    return createErrorResponse('Failed to serve asset', 500);
  }
}

/**
 * Handle index page requests - serve the existing index.html file
 */
async function handleIndexPage(request: Request, env: Env): Promise<Response> {
  try {
    // Serve the existing index.html file from the project
    const htmlContent = await env.BLOG_BUCKET.get('index.html');
    
    if (!htmlContent) {
      // Fallback to a simple response if file not found
      return new Response('Quill Auto Blogger API', {
        status: 200,
        headers: {
          'Content-Type': 'text/plain',
          ...getCORSHeaders()
        }
      });
    }
    
    const response = new Response(htmlContent.body, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Vary': 'Accept-Encoding',
        ...getCORSHeaders()
      }
    });
    
    // Set appropriate cache headers for HTML
    setContentTypeCacheHeaders(response, 'text/html');
    
    return response;

  } catch (error) {
    console.error('Index page error:', error);
    return createErrorResponse('Failed to serve index page', 500);
  }
}
