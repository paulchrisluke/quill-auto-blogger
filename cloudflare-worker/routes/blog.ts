/**
 * Blog routes for M6 Distribution & Discovery
 * Handles canonical URLs, conditional GET, and caching
 */

import { setCacheHeaders, setValidators, handleConditionalGet, getLastModified } from '../lib/cache';
import { CACHE_CONFIG } from '../config';
import { Env } from '../types';

export interface BlogData {
  date: string;
  title: string;
  summary?: string;
  stories?: Array<{
    pr_number: number;
    video_url?: string;
  }>;
  [key: string]: any;
}

/**
 * Handle blog requests with canonical URL support and conditional GET
 */
export async function handleBlogRequest(
  request: Request,
  env: Env,
  path: string
): Promise<Response> {
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
    
    let digestData: BlogData | null = null;
    let digestObject: any = null;
    let lastModified: Date | null = null;
    
    // First, try to get object metadata for conditional GET without reading the body
    try {
      digestObject = await env.BLOG_BUCKET.get(digestKey);
    } catch (error) {
      console.log('Digest metadata fetch failed', { 
        date, 
        digestKey, 
        error: error instanceof Error ? error.message : String(error)
      });
    }
    
    // If we have object metadata, handle conditional GET first
    if (digestObject) {
      // Use R2 object metadata for conditional GET (avoid reading body)
      const r2Etag = digestObject.httpEtag;
      lastModified = getLastModified(digestObject);
      
      // Check conditional GET using R2 metadata
      if (r2Etag) {
        const conditionalResponse = handleConditionalGet(request, { 
          etag: `"${r2Etag}"`, 
          lastModified 
        });
        if (conditionalResponse) {
          // Set cache headers on 304 response
          setCacheHeaders(conditionalResponse, CACHE_CONFIG.blog);
          setValidators(conditionalResponse, { 
            etag: `"${r2Etag}"`, 
            lastModified 
          });
          return conditionalResponse;
        }
      }
      
      // Only read and parse the body if conditional GET is not satisfied
      try {
        digestData = await digestObject.json();
      } catch (error) {
        console.log('Digest body parsing failed', { 
          date, 
          digestKey, 
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }
    
    // If we have digest data, return it
    if (digestData && digestObject) {
      
      // Build response with cache headers and validators
      const body = JSON.stringify(digestData);
      const response = new Response(body, {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Vary': 'Accept-Encoding',
        }
      });
      
      // Set cache headers and validators using R2 metadata
      setCacheHeaders(response, CACHE_CONFIG.blog);
      setValidators(response, { 
        etag: `"${digestObject.httpEtag || 'unknown'}"`, 
        lastModified: lastModified || new Date()
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
 * Handle canonical redirects for alternate blog URLs
 */
export function handleCanonicalRedirect(path: string): Response | null {
  // Handle /blogs/YYYY/MM/DD → /blog/YYYY-MM-DD
  const blogsMatch = path.match(/^\/blogs\/(\d{4})\/(\d{2})\/(\d{2})\/?$/);
  if (blogsMatch) {
    const [, year, month, day] = blogsMatch;
    const canonicalUrl = `/blog/${year}-${month}-${day}`;
    return new Response(null, {
      status: 301,
      headers: {
        'Location': canonicalUrl,
        'Cache-Control': 'public, max-age=86400',
      }
    });
  }
  
  // Handle /blog/YYYY/MM/DD → /blog/YYYY-MM-DD
  const blogMatch = path.match(/^\/blog\/(\d{4})\/(\d{2})\/(\d{2})\/?$/);
  if (blogMatch) {
    const [, year, month, day] = blogMatch;
    const canonicalUrl = `/blog/${year}-${month}-${day}`;
    return new Response(null, {
      status: 301,
      headers: {
        'Location': canonicalUrl,
        'Cache-Control': 'public, max-age=86400',
      }
    });
  }
  
  return null;
}

/**
 * Create error response with CORS headers
 */
function createErrorResponse(message: string, status: number): Response {
  return new Response(message, { 
    status,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    }
  });
}
