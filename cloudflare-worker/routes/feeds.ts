/**
 * Feed routes for M6 Distribution & Discovery
 * Generates RSS, Atom, and JSON Feed
 */

import { getConfig } from '../config';
import { CACHE_CONFIG } from '../config';
import { generateRSS, generateAtom, generateJSONFeed, FeedItem, truncateText } from '../lib/feeds';
import { Env } from '../types';

/**
 * Handle feed requests
 */
export async function handleFeedRequest(
  request: Request,
  env: Env,
  path: string
): Promise<Response> {
  try {
    if (path === '/feed.xml') {
      return await generateRSSFeed(request, env);
    } else if (path === '/feed.atom') {
      return await generateAtomFeed(request, env);
    } else if (path === '/feed.json') {
      return await generateJSONFeedResponse(request, env);
    }
    
    return createErrorResponse('Feed not found', 404);
    
  } catch (error) {
    console.error('Feed error:', error);
    return createErrorResponse('Failed to generate feed', 500);
  }
}

/**
 * Generate RSS feed
 */
async function generateRSSFeed(request: Request, env: Env): Promise<Response> {
  const config = getConfig();
  const feedItems = await getFeedItems(env, config.feedItems);
  
  const rss = generateRSS({
    title: 'Quill Auto Blogger',
    description: 'Automated blog posts generated from GitHub activity',
    siteUrl: config.siteBaseUrl,
    feedUrl: `${config.siteBaseUrl}/feed.xml`,
    items: feedItems
  });
  
  const response = new Response(rss, {
    status: 200,
    headers: {
      'Content-Type': 'application/rss+xml; charset=utf-8',
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
 * Generate Atom feed
 */
async function generateAtomFeed(request: Request, env: Env): Promise<Response> {
  const config = getConfig();
  const feedItems = await getFeedItems(env, config.feedItems);
  
  const atom = generateAtom({
    title: 'Quill Auto Blogger',
    description: 'Automated blog posts generated from GitHub activity',
    siteUrl: config.siteBaseUrl,
    feedUrl: `${config.siteBaseUrl}/feed.atom`,
    items: feedItems
  });
  
  const response = new Response(atom, {
    status: 200,
    headers: {
      'Content-Type': 'application/atom+xml; charset=utf-8',
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
 * Generate JSON Feed response
 */
async function generateJSONFeedResponse(request: Request, env: Env): Promise<Response> {
  const config = getConfig();
  const feedItems = await getFeedItems(env, config.feedItems);
  
  const jsonFeed = generateJSONFeed({
    title: 'Quill Auto Blogger',
    description: 'Automated blog posts generated from GitHub activity',
    siteUrl: config.siteBaseUrl,
    feedUrl: `${config.siteBaseUrl}/feed.json`,
    items: feedItems
  });
  
  const response = new Response(jsonFeed, {
    status: 200,
    headers: {
      'Content-Type': 'application/feed+json; charset=utf-8',
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
 * Get feed items from blog data
 */
async function getFeedItems(env: Env, maxItems: number): Promise<FeedItem[]> {
  const items: FeedItem[] = [];
  
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
    
    // Sort dates descending and take the most recent
    dates.sort((a, b) => b.localeCompare(a));
    const recentDates = dates.slice(0, maxItems);
    
    // Fetch blog data for each date
    for (const date of recentDates) {
      try {
        const digestKey = `blogs/${date}/FINAL-${date}_digest.json`;
        const digestObject = await env.BLOG_BUCKET.get(digestKey);
        
        if (digestObject) {
          const digestData = await digestObject.json() as any;
          
          // Find first story with video for PR link
          let storyPrLink: string | undefined;
          if (digestData.stories && digestData.stories.length > 0) {
            const firstStory = digestData.stories[0];
            if (firstStory.video_url) {
              storyPrLink = firstStory.video_url;
            }
          }
          
          items.push({
            title: digestData.title || `Blog Post - ${date}`,
            url: `${getConfig().siteBaseUrl}/blog/${date}`,
            datePublished: digestData.date || date,
            summary: truncateText(digestData.summary || digestData.description || 'Blog post content', 250),
            storyPrLink
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
