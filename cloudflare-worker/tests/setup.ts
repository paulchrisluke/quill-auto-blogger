/**
 * Test setup for Vitest
 */

import { vi } from 'vitest';
import { TextDecoder as NodeTextDecoder } from 'util';

// Mock TextDecoder for ArrayBuffer handling with proper UTF-8 support
global.TextDecoder = class TextDecoder {
  private decoder: NodeTextDecoder;
  
  constructor(label: string = 'utf-8') {
    this.decoder = new NodeTextDecoder(label);
  }
  
  decode(input: BufferSource): string {
    // Normalize input to Uint8Array for consistent handling
    let normalized: Uint8Array;
    
    if (input instanceof ArrayBuffer) {
      normalized = new Uint8Array(input);
    } else if (input instanceof Uint8Array) {
      normalized = input;
    } else {
      // Handle other BufferSource types by converting to Uint8Array
      normalized = new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
    }
    
    // Use Node's TextDecoder for proper UTF-8 decoding
    return this.decoder.decode(normalized);
  }
} as any;

// Mock crypto.subtle for ETag generation tests
Object.defineProperty(global, 'crypto', {
  value: {
    subtle: {
      digest: vi.fn().mockImplementation(async (algorithm, data) => {
        // Improved mock hash function for testing
        let inputBytes: Uint8Array;
        
        // Handle different input types properly
        if (typeof data === 'string') {
          inputBytes = new TextEncoder().encode(data);
        } else if (data instanceof ArrayBuffer) {
          inputBytes = new Uint8Array(data);
        } else if (data instanceof Uint8Array) {
          inputBytes = data;
        } else {
          // Handle other BufferSource types
          inputBytes = new Uint8Array(data);
        }
        
        // Use a more realistic hash algorithm (simplified SHA-256-like)
        let hash = 0x6a09e667; // Initial hash value (first 32 bits of SHA-256)
        
        // Process input bytes in chunks
        for (let i = 0; i < inputBytes.length; i++) {
          const byte = inputBytes[i];
          // Mix the byte into the hash using bit operations
          hash = ((hash << 13) | (hash >>> 19)) + byte; // Rotate left and add
          hash = hash ^ (hash >>> 16); // XOR with upper half
          hash = hash * 0x85ebca6b; // Multiply by prime
          hash = hash ^ (hash >>> 13); // XOR with upper half
          hash = hash * 0xc2b2ae35; // Multiply by prime
          hash = hash ^ (hash >>> 16); // Final XOR
        }
        
        // Ensure hash is positive 32-bit integer
        hash = hash >>> 0;
        
        // Create a 32-byte hash output (like SHA-256)
        const hashArray = new Uint8Array(32);
        
        // Fill first 4 bytes with the 32-bit hash
        hashArray[0] = (hash >>> 24) & 0xff;
        hashArray[1] = (hash >>> 16) & 0xff;
        hashArray[2] = (hash >>> 8) & 0xff;
        hashArray[3] = hash & 0xff;
        
        // Fill remaining bytes with derived values for consistency
        for (let i = 4; i < 32; i++) {
          // Use the hash value to generate additional bytes
          const derivedHash = ((hash * (i + 1)) ^ (hash >>> (i % 16))) >>> 0;
          hashArray[i] = derivedHash & 0xff;
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
