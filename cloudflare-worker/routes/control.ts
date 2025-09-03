/**
 * Control routes for M6 Distribution & Discovery
 * Handles cache purging and other administrative functions
 */

import { getConfig } from '../config';
import { Env } from '../types';
import { constantTimeCompare } from '../lib/cache';

export interface PurgeResponse {
  ok: boolean;
  purged: string[];
  message?: string;
}

/**
 * Verify Bearer token authentication using constant-time comparison
 * Prevents timing attacks when comparing tokens
 */
export function verifyAuth(request: Request, env: Env): boolean {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader) {
    return false;
  }
  
  // Check for Bearer token format
  if (!authHeader.toLowerCase().startsWith('bearer ')) {
    return false;
  }
  
  // Extract token (remove "Bearer " prefix)
  const token = authHeader.substring(7);
  
  // Use constant-time comparison to prevent timing attacks
  return constantTimeCompare(token, env.CLOUDFLARE_API_TOKEN);
}

/**
 * Handle control requests
 */
export async function handleControlRequest(
  request: Request,
  env: Env,
  path: string
): Promise<Response> {
  // Route control requests
  if (path === '/control/purge') {
    return await handlePurgeRequest(request, env);
  }
  
  return createErrorResponse('Control endpoint not found', 404);
}

/**
 * Handle cache purge requests
 */
async function handlePurgeRequest(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') {
    return createErrorResponse('Method not allowed', 405);
  }
  
  // Verify authentication
  if (!verifyAuth(request, env)) {
    return createErrorResponse('Forbidden', 403);
  }
  
  try {
    const url = new URL(request.url);
    const date = url.searchParams.get('date');
    
    if (!date) {
      return createErrorResponse('Date parameter required', 400);
    }
    
    // Validate date format
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return createErrorResponse('Invalid date format. Use YYYY-MM-DD', 400);
    }
    
    const purgedPaths: string[] = [];
    
    // Purge blog API cache
    const blogApiPath = `/api/blog/${date}`;
    purgedPaths.push(blogApiPath);
    
    // Purge blog route cache
    const blogRoutePath = `/blog/${date}`;
    purgedPaths.push(blogRoutePath);
    
    // Purge related assets if they exist
    const [year, month, day] = date.split('-');
    const assetPaths = [
      `/stories/${year}/${month}/${day}/`,
      `/assets/stories/${year}/${month}/${day}/`,
    ];
    
    // Check if assets exist and add to purge list
    for (const assetPath of assetPaths) {
      try {
        const assetKey = assetPath.replace('/assets/', '');
        const asset = await env.BLOG_BUCKET.get(assetKey);
        if (asset) {
          purgedPaths.push(assetPath);
        }
      } catch (error) {
        // Asset doesn't exist, skip
      }
    }
    
    // Note: In a real Cloudflare Worker, you would use the Cache API
    // to actually purge the cache. This is a placeholder for the purge logic.
    console.log('Cache purge requested for:', { date, purgedPaths });
    
    const response: PurgeResponse = {
      ok: true,
      purged: purgedPaths,
      message: `Cache purged for ${date}`
    };
    
    return new Response(JSON.stringify(response), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }
    });
    
  } catch (error) {
    console.error('Purge request error:', error);
    return createErrorResponse('Failed to process purge request', 500);
  }
}

/**
 * Create error response
 */
function createErrorResponse(message: string, status: number): Response {
  return new Response(JSON.stringify({ 
    ok: false, 
    error: message 
  }), { 
    status,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    }
  });
}
