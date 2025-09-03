/**
 * Robots.txt route for M6 Distribution & Discovery
 * Provides search engine crawling instructions
 */

import { getConfig } from '../config';
import { Env } from '../types';

/**
 * Handle robots.txt requests
 */
export async function handleRobotsRequest(
  request: Request,
  env: Env,
  path: string
): Promise<Response> {
  if (path !== '/robots.txt') {
    return createErrorResponse('Not found', 404);
  }
  
  try {
    const config = getConfig(env);
    
    const robotsTxt = `User-agent: *
Allow: /

# Sitemap
Sitemap: ${config.siteBaseUrl}/sitemap.xml

# Feeds
Allow: /feed.xml
Allow: /feed.atom
Allow: /feed.json

# Blog posts
Allow: /blog/

# Assets
Allow: /assets/
Allow: /stories/

# Disallow admin/control endpoints
Disallow: /control/

# Crawl delay (optional)
Crawl-delay: 1`;
    
    const response = new Response(robotsTxt, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'public, max-age=86400, s-maxage=86400', // 24 hours
      }
    });
    
    return response;
    
  } catch (error) {
    console.error('Robots.txt error:', error);
    return createErrorResponse('Failed to generate robots.txt', 500);
  }
}

/**
 * Create error response
 */
function createErrorResponse(message: string, status: number): Response {
  return new Response(message, { 
    status,
    headers: {
      'Content-Type': 'text/plain',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    }
  });
}
