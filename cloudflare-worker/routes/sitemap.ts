/**
 * Sitemap routes for M6 Distribution & Discovery
 * Generates XML sitemaps for SEO
 */

import { getConfig } from '../config';
import { CACHE_CONFIG } from '../config';
import { Env } from '../types';

export interface SitemapUrl {
  loc: string;
  lastmod: string;
  changefreq?: string;
  priority?: number;
}

/**
 * Handle sitemap requests
 */
export async function handleSitemapRequest(
  request: Request,
  env: Env,
  path: string
): Promise<Response> {
  try {
    if (path === '/sitemap.xml') {
      return await generateSitemapIndex(request, env);
    }
    
    // Handle monthly sitemaps: /sitemaps/blog-YYYY-MM.xml
    const monthlyMatch = path.match(/^\/sitemaps\/blog-(\d{4})-(\d{2})\.xml$/);
    if (monthlyMatch) {
      const [, year, month] = monthlyMatch;
      return await generateMonthlySitemap(request, env, year, month);
    }
    
    return createErrorResponse('Sitemap not found', 404);
    
  } catch (error) {
    console.error('Sitemap error:', error);
    return createErrorResponse('Failed to generate sitemap', 500);
  }
}

/**
 * Generate sitemap index
 */
async function generateSitemapIndex(request: Request, env: Env): Promise<Response> {
  const config = getConfig();
  const currentDate = new Date();
  
  // Generate monthly sitemap URLs for the last N months
  const sitemapUrls: string[] = [];
  for (let i = 0; i < config.sitemapMonths; i++) {
    const date = new Date(currentDate.getFullYear(), currentDate.getMonth() - i, 1);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    sitemapUrls.push(`${config.siteBaseUrl}/sitemaps/blog-${year}-${month}.xml`);
  }
  
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemapUrls.map(url => `  <sitemap>
    <loc>${url}</loc>
    <lastmod>${currentDate.toISOString()}</lastmod>
  </sitemap>`).join('\n')}
</sitemapindex>`;
  
  const response = new Response(xml, {
    status: 200,
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
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
 * Generate monthly sitemap
 */
async function generateMonthlySitemap(
  request: Request, 
  env: Env, 
  year: string, 
  month: string
): Promise<Response> {
  try {
    // List all blog posts for the given month
    const blogUrls = await getBlogUrlsForMonth(env, year, month);
    
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${blogUrls.map(url => `  <url>
    <loc>${url.loc}</loc>
    <lastmod>${url.lastmod}</lastmod>
    <changefreq>${url.changefreq || 'daily'}</changefreq>
    <priority>${url.priority || 0.6}</priority>
  </url>`).join('\n')}
</urlset>`;
    
    const response = new Response(xml, {
      status: 200,
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Vary': 'Accept-Encoding',
      }
    });
    
    // Set cache headers
    response.headers.set(
      'Cache-Control', 
      `public, max-age=${CACHE_CONFIG.feeds.maxAge}, s-maxage=${CACHE_CONFIG.feeds.sMaxAge}, stale-while-revalidate=${CACHE_CONFIG.feeds.swr}`
    );
    
    return response;
    
  } catch (error) {
    console.error('Monthly sitemap error:', error);
    return createErrorResponse('Failed to generate monthly sitemap', 500);
  }
}

/**
 * Get blog URLs for a specific month
 */
async function getBlogUrlsForMonth(env: Env, year: string, month: string): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = [];
  const config = getConfig();
  
  try {
    // List objects in the blogs directory for the month
    const prefix = `blogs/${year}-${month}`;
    const objects = await env.BLOG_BUCKET.list({ prefix });
    
    // Extract dates from object keys
    const dates = new Set<string>();
    for (const obj of objects.objects) {
      const match = obj.key.match(/^blogs\/(\d{4}-\d{2}-\d{2})\//);
      if (match) {
        dates.add(match[1]);
      }
    }
    
    // Convert dates to URLs
    for (const date of dates) {
      urls.push({
        loc: `${config.siteBaseUrl}/blog/${date}`,
        lastmod: new Date().toISOString(), // Use current time as fallback
        changefreq: 'daily',
        priority: 0.6
      });
    }
    
  } catch (error) {
    console.error('Error listing blog URLs for month:', error);
  }
  
  return urls;
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
