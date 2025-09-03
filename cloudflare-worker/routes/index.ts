/**
 * Index routes for M6 Distribution & Discovery
 * Lists recent blog posts
 */

import { getConfig } from '../config';
import { CACHE_CONFIG } from '../config';
import { Env } from '../types';

export interface BlogListItem {
  date: string;
  title: string;
  url: string;
  summary?: string;
}

/**
 * Handle index requests
 */
export async function handleIndexRequest(
  request: Request,
  env: Env,
  path: string
): Promise<Response> {
  try {
    if (path === '/blogs') {
      return await generateBlogsIndex(request, env);
    } else if (path === '/blogs/index.json') {
      return await generateBlogsJSON(request, env);
    }
    
    return createErrorResponse('Index not found', 404);
    
  } catch (error) {
    console.error('Index error:', error);
    return createErrorResponse('Failed to generate index', 500);
  }
}

/**
 * Generate HTML index of recent blog posts
 */
async function generateBlogsIndex(request: Request, env: Env): Promise<Response> {
  const config = getConfig();
  const blogItems = await getRecentBlogItems(env, 20);
  
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recent Blog Posts - Quill Auto Blogger</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        .blog-item { margin-bottom: 30px; padding: 20px; border: 1px solid #eee; border-radius: 8px; }
        .blog-date { color: #666; font-size: 0.9em; margin-bottom: 5px; }
        .blog-title { font-size: 1.4em; margin-bottom: 10px; }
        .blog-title a { color: #007acc; text-decoration: none; }
        .blog-title a:hover { text-decoration: underline; }
        .blog-summary { color: #555; line-height: 1.6; }
        .feed-links { margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; }
        .feed-links a { margin-right: 20px; color: #007acc; text-decoration: none; }
    </style>
</head>
<body>
    <h1>Recent Blog Posts</h1>
    
    ${blogItems.map(item => `
    <div class="blog-item">
        <div class="blog-date">${formatDate(item.date)}</div>
        <div class="blog-title"><a href="${item.url}">${escapeHtml(item.title)}</a></div>
        ${item.summary ? `<div class="blog-summary">${escapeHtml(item.summary)}</div>` : ''}
    </div>
    `).join('')}
    
    <div class="feed-links">
        <strong>Subscribe:</strong>
        <a href="/feed.xml">RSS Feed</a>
        <a href="/feed.atom">Atom Feed</a>
        <a href="/feed.json">JSON Feed</a>
        <a href="/sitemap.xml">Sitemap</a>
    </div>
</body>
</html>`;
  
  const response = new Response(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Vary': 'Accept-Encoding',
    }
  });
  
  // Set cache headers
  response.headers.set(
    'Cache-Control', 
    `public, max-age=${CACHE_CONFIG.html.maxAge}, s-maxage=${CACHE_CONFIG.html.sMaxAge}, stale-while-revalidate=${CACHE_CONFIG.html.swr}`
  );
  
  return response;
}

/**
 * Generate JSON index of recent blog posts
 */
async function generateBlogsJSON(request: Request, env: Env): Promise<Response> {
  const blogItems = await getRecentBlogItems(env, 50);
  
  const response = new Response(JSON.stringify(blogItems, null, 2), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Vary': 'Accept-Encoding',
    }
  });
  
  // Set cache headers
  response.headers.set(
    'Cache-Control', 
    `public, max-age=${CACHE_CONFIG.feeds.maxAge}, s-maxage=${CACHE_CONFIG.feeds.sMaxAge}, stale-while-revalidate=${CACHE_CONFIG.feeds.swr}`
  );
  
  return response;
}

/**
 * Get recent blog items
 */
async function getRecentBlogItems(env: Env, maxItems: number): Promise<BlogListItem[]> {
  const items: BlogListItem[] = [];
  const config = getConfig();
  
  try {
    // List all blog objects to find recent posts
    const objects = await env.BLOG_BUCKET.list({ prefix: 'blogs/' });
    
    // Extract dates and sort by most recent
    const dates: string[] = [];
    for (const obj of objects.objects) {
      const match = obj.key.match(/^blogs\/(\d{4}-\d{2}-\d{2})\//);
      if (match) {
        dates.push(match[1]);
      }
    }
    
    // Deduplicate dates, sort descending, and take the most recent
    const uniqueDates = Array.from(new Set(dates));
    uniqueDates.sort((a, b) => b.localeCompare(a));
    const recentDates = uniqueDates.slice(0, maxItems);
    
    // Fetch blog data for each date
    for (const date of recentDates) {
      try {
        const digestKey = `blogs/${date}/FINAL-${date}_digest.json`;
        const digestObject = await env.BLOG_BUCKET.get(digestKey);
        
        if (digestObject) {
          const digestData = await digestObject.json() as any;
          
          items.push({
            date: digestData.date || date,
            title: digestData.title || `Blog Post - ${date}`,
            url: `${config.siteBaseUrl}/blog/${date}`,
            summary: digestData.summary || digestData.description
          });
        }
      } catch (error) {
        console.error(`Error fetching blog data for ${date}:`, error);
      }
    }
    
  } catch (error) {
    console.error('Error listing blog objects:', error);
  }
  
  return items;
}

/**
 * Format date for display
 */
function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  } catch {
    return dateString;
  }
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
