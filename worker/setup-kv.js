#!/usr/bin/env node

/**
 * Setup script to create KV namespaces and update wrangler.toml
 * 
 * Usage:
 *   node setup-kv.js
 */

import { execSync } from 'child_process';
import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function setupKV() {
  console.log('Setting up KV namespaces for prompts...');
  
  try {
    // Create production namespace
    console.log('Creating production KV namespace...');
    const prodOutput = execSync('wrangler kv:namespace create "PROMPTS_KV"', {
      encoding: 'utf8',
      cwd: __dirname
    });
    const prodId = prodOutput.match(/id = "([^"]+)"/)?.[1];
    
    // Create preview namespace
    console.log('Creating preview KV namespace...');
    const previewOutput = execSync('wrangler kv:namespace create "PROMPTS_KV" --preview', {
      encoding: 'utf8',
      cwd: __dirname
    });
    const previewId = previewOutput.match(/id = "([^"]+)"/)?.[1];
    
    if (!prodId || !previewId) {
      throw new Error('Failed to extract namespace IDs');
    }
    
    // Update wrangler.toml
    console.log('Updating wrangler.toml...');
    const wranglerPath = join(__dirname, 'wrangler.toml');
    let wranglerContent = readFileSync(wranglerPath, 'utf8');
    
    // Replace placeholder IDs with actual IDs
    wranglerContent = wranglerContent.replace(
      /id = "your-kv-namespace-id"/g,
      `id = "${prodId}"`
    );
    wranglerContent = wranglerContent.replace(
      /preview_id = "your-preview-kv-namespace-id"/g,
      `preview_id = "${previewId}"`
    );
    
    writeFileSync(wranglerPath, wranglerContent);
    
    console.log('✅ KV setup complete!');
    console.log(`Production namespace ID: ${prodId}`);
    console.log(`Preview namespace ID: ${previewId}`);
    console.log('\nNext steps:');
    console.log('1. Run: npm run upload-prompts');
    console.log('2. Run: npm run upload-prompts:staging');
    console.log('3. Deploy: npm run deploy');
    
  } catch (error) {
    console.error('❌ Setup failed:', error.message);
    console.log('\nManual setup required:');
    console.log('1. Run: wrangler kv:namespace create "PROMPTS_KV"');
    console.log('2. Run: wrangler kv:namespace create "PROMPTS_KV" --preview');
    console.log('3. Update wrangler.toml with the namespace IDs');
    console.log('4. Run: npm run upload-prompts');
  }
}

setupKV().catch(console.error);
