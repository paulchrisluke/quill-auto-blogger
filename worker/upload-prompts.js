#!/usr/bin/env node

/**
 * Utility script to upload prompt files to Cloudflare KV storage
 * 
 * Usage:
 *   node upload-prompts.js [--env production|staging]
 */

import { readFileSync, writeFileSync, unlinkSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import { execFileSync } from 'child_process';
import { tmpdir } from 'os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Get environment from command line args
const args = process.argv.slice(2);

// Validate environment argument
function getEnvironment() {
  const envIndex = args.indexOf('--env');
  
  // If no --env flag, default to production
  if (envIndex === -1) {
    return 'production';
  }
  
  // Check if --env is the last argument (no value provided)
  if (envIndex === args.length - 1) {
    console.error('❌ Error: --env flag requires a value');
    console.error('Usage: node upload-prompts.js [--env production|staging]');
    process.exit(1);
  }
  
  const envValue = args[envIndex + 1];
  
  // Validate the environment value
  const allowedEnvironments = ['production', 'staging', 'development'];
  
  if (!envValue || !allowedEnvironments.includes(envValue)) {
    console.error(`❌ Error: Invalid environment "${envValue}"`);
    console.error(`Allowed environments: ${allowedEnvironments.join(', ')}`);
    console.error('Usage: node upload-prompts.js [--env production|staging]');
    process.exit(1);
  }
  
  return envValue;
}

const env = getEnvironment();

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
    let tempFile = null;
    try {
      const content = readFileSync(prompt.file, 'utf8');
      
      // Create a temporary file for the content
      tempFile = join(tmpdir(), `prompt-${Date.now()}-${Math.random().toString(36).substr(2, 9)}.md`);
      writeFileSync(tempFile, content, 'utf8');
      
      // Use wrangler to upload to KV with --path flag
      const wranglerArgs = [
        'wrangler',
        'kv:key',
        'put',
        '--binding=PROMPTS_KV',
        prompt.key,
        '--path',
        tempFile,
        `--env=${env}`
      ];
      
      execFileSync('npx', wranglerArgs, {
        stdio: 'inherit',
        cwd: __dirname
      });
      
      console.log(`✅ Uploaded ${prompt.key}`);
    } catch (error) {
      console.error(`❌ Failed to upload ${prompt.key}:`, error.message);
    } finally {
      // Clean up temporary file
      if (tempFile) {
        try {
          unlinkSync(tempFile);
        } catch (cleanupError) {
          console.warn(`⚠️  Warning: Could not clean up temporary file ${tempFile}:`, cleanupError.message);
        }
      }
    }
  }
  
  console.log('Done!');
}

uploadPrompts().catch(console.error);
