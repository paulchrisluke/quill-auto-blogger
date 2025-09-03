/**
 * Tests for cache helper functions
 */

import { makeETag, setCacheHeaders, setValidators, handleConditionalGet } from '../lib/cache';

describe('Cache Helpers', () => {
  describe('makeETag', () => {
    it('should generate consistent ETags for same content', async () => {
      const content = 'test content';
      const etag1 = await makeETag(content);
      const etag2 = await makeETag(content);
      
      expect(etag1).toBe(etag2);
      expect(etag1).toMatch(/^"[a-f0-9]{64}"$/);
    });

    it('should generate different ETags for different content', async () => {
      const etag1 = await makeETag('content 1');
      const etag2 = await makeETag('content 2');
      
      expect(etag1).not.toBe(etag2);
    });

    it('should handle ArrayBuffer input', async () => {
      const buffer = new TextEncoder().encode('test buffer');
      const etag = await makeETag(buffer);
      
      expect(etag).toMatch(/^"[a-f0-9]{64}"$/);
    });
  });

  describe('setCacheHeaders', () => {
    it('should set default cache headers', () => {
      const response = new Response();
      setCacheHeaders(response);
      
      const cacheControl = response.headers.get('Cache-Control');
      expect(cacheControl).toContain('public, max-age=300, s-maxage=1800, stale-while-revalidate=60');
    });

    it('should set custom cache headers', () => {
      const response = new Response();
      setCacheHeaders(response, { maxAge: 600, sMaxAge: 3600, swr: 120 });
      
      const cacheControl = response.headers.get('Cache-Control');
      expect(cacheControl).toContain('public, max-age=600, s-maxage=3600, stale-while-revalidate=120');
    });
  });

  describe('setValidators', () => {
    it('should set ETag and Last-Modified headers', () => {
      const response = new Response();
      const etag = '"test-etag"';
      const lastModified = new Date('2025-01-01T00:00:00Z');
      
      setValidators(response, { etag, lastModified });
      
      expect(response.headers.get('ETag')).toBe(etag);
      expect(response.headers.get('Last-Modified')).toBe(lastModified.toUTCString());
    });
  });

  describe('handleConditionalGet', () => {
    it('should return 304 for matching If-None-Match', () => {
      const request = new Request('https://example.com', {
        headers: { 'If-None-Match': '"test-etag"' }
      });
      
      const result = handleConditionalGet(request, {
        etag: '"test-etag"',
        lastModified: new Date()
      });
      
      expect(result).not.toBeNull();
      expect(result?.status).toBe(304);
    });

    it('should return 304 for matching If-Modified-Since', () => {
      const lastModified = new Date('2025-01-01T00:00:00Z');
      const request = new Request('https://example.com', {
        headers: { 'If-Modified-Since': lastModified.toUTCString() }
      });
      
      const result = handleConditionalGet(request, {
        etag: '"test-etag"',
        lastModified: lastModified
      });
      
      expect(result).not.toBeNull();
      expect(result?.status).toBe(304);
    });

    it('should return null when no conditions match', () => {
      const request = new Request('https://example.com');
      
      const result = handleConditionalGet(request, {
        etag: '"test-etag"',
        lastModified: new Date()
      });
      
      expect(result).toBeNull();
    });
  });
});
