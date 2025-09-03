/**
 * Test setup for Vitest
 */

import { vi } from 'vitest';

// Mock TextDecoder for ArrayBuffer handling
global.TextDecoder = class TextDecoder {
  decode(input: BufferSource): string {
    if (input instanceof ArrayBuffer) {
      return String.fromCharCode.apply(null, new Uint8Array(input) as any);
    }
    if (input instanceof Uint8Array) {
      return String.fromCharCode.apply(null, input as any);
    }
    return '';
  }
} as any;

// Mock crypto.subtle for ETag generation tests
Object.defineProperty(global, 'crypto', {
  value: {
    subtle: {
      digest: vi.fn().mockImplementation(async (algorithm, data) => {
        // Simple mock hash function for testing
        const encoder = new TextEncoder();
        const text = typeof data === 'string' ? data : encoder.encode(data).toString();
        const hash = text.split('').reduce((acc, char) => {
          return ((acc << 5) - acc + char.charCodeAt(0)) & 0xffffffff;
        }, 0);
        
        const hashArray = new Uint8Array(32);
        for (let i = 0; i < 32; i++) {
          hashArray[i] = (hash >> (i * 8)) & 0xff;
        }
        
        return hashArray;
      })
    }
  }
});

// Mock Response and Request constructors if not available
if (typeof Response === 'undefined') {
  global.Response = class Response {
    status: number;
    headers: Headers;
    body: any;
    
    constructor(body?: any, init?: any) {
      this.body = body;
      this.status = init?.status || 200;
      this.headers = new Headers(init?.headers);
    }
  } as any;
}

if (typeof Headers === 'undefined') {
  global.Headers = class Headers {
    private map = new Map<string, string>();
    
    constructor(init?: any) {
      if (init) {
        Object.entries(init).forEach(([key, value]) => {
          this.map.set(key, value as string);
        });
      }
    }
    
    set(key: string, value: string) {
      this.map.set(key, value);
    }
    
    get(key: string): string | null {
      return this.map.get(key) || null;
    }
  } as any;
}

if (typeof Request === 'undefined') {
  global.Request = class Request {
    url: string;
    method: string;
    headers: Headers;
    
    constructor(url: string, init?: any) {
      this.url = url;
      this.method = init?.method || 'GET';
      this.headers = new Headers(init?.headers);
    }
  } as any;
}
