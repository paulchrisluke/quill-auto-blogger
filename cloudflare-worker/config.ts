/**
 * Configuration for M6 Distribution & Discovery
 */

import { Env } from './types';

export interface Config {
  siteBaseUrl: string;
  feedItems: number;
  sitemapMonths: number;
  controlApiToken: string;
}

/**
 * Get configuration from environment variables
 */
export function getConfig(env: Env): Config {
  return {
    siteBaseUrl: env.SITE_BASE_URL || 'https://paulchrisluke.com',
    feedItems: parseInt(env.FEED_ITEMS || '40'),
    sitemapMonths: parseInt(env.SITEMAP_MONTHS || '12'),
    controlApiToken: env.CONTROL_API_TOKEN || '',
  };
}

/**
 * Default cache settings
 */
export const CACHE_CONFIG = {
  // Blog content
  blog: {
    maxAge: 300,        // 5 minutes browser
    sMaxAge: 1800,      // 30 minutes edge
    swr: 60,            // 1 minute stale-while-revalidate
  },
  
  // Assets (images, videos)
  assets: {
    maxAge: 86400,      // 24 hours browser
    sMaxAge: 86400,     // 24 hours edge
    swr: 3600,          // 1 hour stale-while-revalidate
  },
  
  // HTML pages
  html: {
    maxAge: 3600,       // 1 hour browser
    sMaxAge: 86400,     // 24 hours edge
    swr: 300,           // 5 minutes stale-while-revalidate
  },
  
  // Feeds and sitemaps
  feeds: {
    maxAge: 1800,       // 30 minutes browser
    sMaxAge: 3600,      // 1 hour edge
    swr: 300,           // 5 minutes stale-while-revalidate
  },
} as const;

/**
 * Route patterns for canonical URLs
 */
export const ROUTES = {
  blog: '/blog/:date',
  blogs: '/blogs',
  feeds: {
    rss: '/feed.xml',
    atom: '/feed.atom',
    json: '/feed.json',
  },
  sitemap: {
    index: '/sitemap.xml',
    monthly: '/sitemaps/blog-:year-:month.xml',
  },
  control: {
    purge: '/control/purge',
  },
  robots: '/robots.txt',
} as const;
