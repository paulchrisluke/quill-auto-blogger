/**
 * Type definitions for Cloudflare Worker environment
 */

export interface Env {
  BLOG_BUCKET: R2Bucket;
  CONTROL_API_TOKEN?: string;
  SITE_BASE_URL?: string;
  FEED_ITEMS?: string;
  SITEMAP_MONTHS?: string;
  LOCAL_API_URL?: string;
}

export interface R2Object {
  key: string;
  size: number;
  uploaded?: Date;
  httpEtag?: string;
  httpMetadata?: {
    contentType?: string;
    contentEncoding?: string;
    contentLanguage?: string;
    cacheControl?: string;
    cacheExpiry?: Date;
  };
  customMetadata?: Record<string, string>;
  body: ReadableStream | null;
  
  // Methods
  json(): Promise<any>;
  text(): Promise<string>;
  arrayBuffer(): Promise<ArrayBuffer>;
  stream(): ReadableStream;
}

export interface R2Bucket {
  get(key: string): Promise<R2Object | null>;
  put(key: string, value: string | ArrayBuffer | ArrayBufferView | ReadableStream, options?: any): Promise<void>;
  delete(key: string): Promise<void>;
  list(options?: {
    prefix?: string;
    delimiter?: string;
    limit?: number;
    cursor?: string;
  }): Promise<{
    objects: R2Object[];
    truncated: boolean;
    cursor?: string;
    delimitedPrefixes: string[];
  }>;
}

export interface ExecutionContext {
  waitUntil(promise: Promise<any>): void;
  passThroughOnException(): void;
}
