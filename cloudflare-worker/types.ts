/// <reference types="@cloudflare/workers-types" />

/**
 * Type definitions for Cloudflare Worker environment
 * Using official types from @cloudflare/workers-types
 */

// Declare readonly environment bindings
export interface Env {
  readonly BLOG_BUCKET: R2Bucket;
  readonly CLOUDFLARE_API_TOKEN: string;
}
