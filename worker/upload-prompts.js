#!/usr/bin/env node

/**
 * Utility script to upload prompt files to Cloudflare KV storage
 * 
 * Usage:
 *   node upload-prompts.js [--env production|staging]
 */

import { readFileSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Get environment from command line args
const args = process.argv.slice(2);
const env = args.includes('--env') ? args[args.indexOf('--env') + 1] : 'production';

// Prompt files to upload
const prompts = [
  {
    key: 'prompts/default_voice.md',
    file: join(__dirname, '..', 'prompts', 'default_voice.md')
  },
  {
    key: 'prompts/paul_chris_luke.md',
    file: join(__dirname, '..', 'prompts', 'paul_chris_luke.md')
  }
];

async function uploadPrompts() {
  console.log(`Uploading prompts to ${env} environment...`);
  
  for (const prompt of prompts) {
    try {
      const content = readFileSync(prompt.file, 'utf8');
      
      // Use wrangler to upload to KV
      const { execSync } = await import('child_process');
      execSync(`npx wrangler kv:key put --binding=PROMPTS_KV "${prompt.key}" "${content.replace(/"/g, '\\"')}" --env=${env}`, {
        stdio: 'inherit',
        cwd: __dirname
      });
      
      console.log(`✅ Uploaded ${prompt.key}`);
    } catch (error) {
      console.error(`❌ Failed to upload ${prompt.key}:`, error.message);
    }
  }
  
  console.log('Done!');
}

uploadPrompts().catch(console.error);
