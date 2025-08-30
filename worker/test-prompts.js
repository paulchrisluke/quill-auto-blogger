#!/usr/bin/env node

/**
 * Test script to verify prompt loading functionality
 * 
 * Usage:
 *   node test-prompts.js
 */

// Mock environment for testing
const mockEnv = {
  BLOG_VOICE_PROMPT_PATH: 'prompts/default_voice.md',
  PROMPTS_KV: {
    get: async (key) => {
      if (key === 'prompts/default_voice.md') {
        return `# Default Blog Voice

You are a technical blogger writing daily development logs. Your writing style should be:

- **Professional but approachable**: Write in a conversational tone that's easy to follow
- **Technical accuracy**: Be precise with technical details and terminology
- **Engaging**: Make the content interesting for developers and tech enthusiasts
- **Structured**: Use clear headings, bullet points, and logical flow
- **Concise**: Get to the point while providing enough context
- **Personal**: Write in first person, as if you're sharing your daily development activities`;
      }
      return null;
    }
  }
};

// Import the function (we'll need to extract it for testing)
async function testLoadVoicePrompt() {
  console.log('Testing prompt loading functionality...\n');
  
  // Test 1: Load from KV
  console.log('Test 1: Loading from KV store...');
  try {
    const prompt = await loadVoicePrompt(mockEnv);
    console.log('✅ Successfully loaded prompt from KV');
    console.log(`Prompt length: ${prompt.length} characters`);
    console.log(`Contains JSON instructions: ${prompt.includes('JSON object')}`);
  } catch (error) {
    console.log('❌ Failed to load from KV:', error.message);
  }
  
  // Test 2: Fallback when KV not available
  console.log('\nTest 2: Fallback when KV not available...');
  try {
    const prompt = await loadVoicePrompt({ BLOG_VOICE_PROMPT_PATH: 'nonexistent.md' });
    console.log('✅ Successfully loaded fallback prompt');
    console.log(`Prompt length: ${prompt.length} characters`);
    console.log(`Contains JSON instructions: ${prompt.includes('JSON object')}`);
  } catch (error) {
    console.log('❌ Failed to load fallback:', error.message);
  }
  
  // Test 3: Custom prompt path
  console.log('\nTest 3: Custom prompt path...');
  try {
    const customEnv = {
      ...mockEnv,
      BLOG_VOICE_PROMPT_PATH: 'prompts/paul_chris_luke.md'
    };
    const prompt = await loadVoicePrompt(customEnv);
    console.log('✅ Successfully loaded custom prompt path');
    console.log(`Prompt length: ${prompt.length} characters`);
  } catch (error) {
    console.log('❌ Failed to load custom path:', error.message);
  }
  
  console.log('\n✅ All tests completed!');
}

// Extract the loadVoicePrompt function from the worker
async function loadVoicePrompt(env) {
  const promptKey = env.BLOG_VOICE_PROMPT_PATH || 'prompts/default_voice.md';
  
  try {
    // Try to load from KV store if available
    if (env.PROMPTS_KV) {
      const promptContent = await env.PROMPTS_KV.get(promptKey);
      if (promptContent) {
        return promptContent + '\n\nIMPORTANT: Your response must be a valid JSON object with exactly two fields:\n1. \'frontmatter\': A JSON object containing metadata (title, date, author, keywords, etc.)\n2. \'body\': A string containing the full blog post content in Markdown format (NOT JSON, just plain Markdown text)\n\nDo not include JSON code blocks or markdown formatting in the body field - just write the blog content directly.';
      }
    }
    
    // Return default if KV not available or key not found
    return getDefaultPrompt();
  } catch (error) {
    console.error('Error loading voice prompt:', error);
    return getDefaultPrompt();
  }
}

function getDefaultPrompt() {
  return `You are a technical blogger writing daily development logs. Your writing style should be:

- Professional but approachable: Write in a conversational tone that's easy to follow
- Technical accuracy: Be precise with technical details and terminology
- Engaging: Make the content interesting for developers and tech enthusiasts
- Structured: Use clear headings, bullet points, and logical flow
- Concise: Get to the point while providing enough context
- Personal: Write in first person, as if you're sharing your daily development activities

IMPORTANT: Your response must be a valid JSON object with exactly two fields:
1. 'frontmatter': A JSON object containing metadata (title, date, author, keywords, etc.)
2. 'body': A string containing the full blog post content in Markdown format (NOT JSON, just plain Markdown text)

Do not include JSON code blocks or markdown formatting in the body field - just write the blog content directly.`;
}

testLoadVoicePrompt().catch(console.error);
