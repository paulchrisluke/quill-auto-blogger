import { Ai } from '@cloudflare/ai';

// Helper function to validate CORS origin
function getCorsOrigin(request, env) {
  const allowedOrigins = env.ALLOWED_ORIGINS;
  
  // If no allowed origins configured, allow all (for development)
  if (!allowedOrigins || allowedOrigins === '*') {
    return '*';
  }
  
  // Parse allowed origins (comma-separated)
  const allowedOriginsList = allowedOrigins.split(',').map(origin => origin.trim());
  
  // Get the origin from the request
  const requestOrigin = request.headers.get('Origin');
  
  // If no origin in request, return null (will be handled by caller)
  if (!requestOrigin) {
    return null;
  }
  
  // Check if the request origin is in the allowed list
  if (allowedOriginsList.includes(requestOrigin)) {
    return requestOrigin;
  }
  
  // Origin not allowed
  return null;
}

// Helper function to create CORS headers
function createCorsHeaders(corsOrigin) {
  const headers = {};
  
  if (corsOrigin) {
    headers['Access-Control-Allow-Origin'] = corsOrigin;
    headers['Vary'] = 'Origin';
  }
  
  return headers;
}

export default {
  async fetch(request, env, ctx) {
    // Get CORS origin
    const corsOrigin = getCorsOrigin(request, env);
    
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      const corsHeaders = createCorsHeaders(corsOrigin);
      return new Response(null, {
        status: 200,
        headers: {
          ...corsHeaders,
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
      });
    }

    // Only allow POST requests
    if (request.method !== 'POST') {
      const corsHeaders = createCorsHeaders(corsOrigin);
      return new Response('Method not allowed', { 
        status: 405,
        headers: {
          ...corsHeaders,
          'Content-Type': 'text/plain',
        }
      });
    }

    try {
      // Check authentication if bearer token is configured
      const bearerToken = env.BEARER_TOKEN;
      if (bearerToken) {
        const authHeader = request.headers.get('Authorization');
        if (!authHeader || !authHeader.startsWith('Bearer ')) {
          const corsHeaders = createCorsHeaders(corsOrigin);
          return new Response('Unauthorized', {
            status: 401,
            headers: {
              ...corsHeaders,
              'Content-Type': 'text/plain',
              'WWW-Authenticate': 'Bearer',
            }
          });
        }
        
        const token = authHeader.substring(7); // Remove 'Bearer ' prefix
        if (token !== bearerToken) {
          const corsHeaders = createCorsHeaders(corsOrigin);
          return new Response('Forbidden', {
            status: 403,
            headers: {
              ...corsHeaders,
              'Content-Type': 'text/plain',
            }
          });
        }
      }
      
      // Parse the request body
      const requestData = await request.json();
      
      if (!requestData.digest) {
        const corsHeaders = createCorsHeaders(corsOrigin);
        return new Response('Missing digest data', { 
          status: 400,
          headers: {
            ...corsHeaders,
            'Content-Type': 'text/plain',
          }
        });
      }

      // Load the voice prompt
      const voicePrompt = await loadVoicePrompt(env);
      
      // Initialize AI
      const ai = new Ai(env.AI);
      
      // Prepare the system and user messages
      const systemMessage = {
        role: 'system',
        content: voicePrompt
      };
      
      const userMessage = {
        role: 'user',
        content: `Write a blog post based on this structured data. The response should be a JSON object with two fields:
- 'frontmatter': A JSON object containing metadata like title, date, author, keywords, etc.
- 'body': A string containing the full blog post content in Markdown format (not JSON, just plain Markdown text)

Digest data:
${JSON.stringify(requestData.digest, null, 2)}`
      };

      // Generate the blog post
      const response = await ai.run('@cf/google/gemma-3-12b-it', {
        messages: [systemMessage, userMessage],
        stream: false,
        max_tokens: 4000,
        temperature: 0.7,
      });

      // Parse the AI response
      let aiResponse;
      try {
        // Try to extract JSON from the response
        const responseText = response.response;
        
        // First, look for a fenced JSON code block (```json ... ```)
        const fencedJsonMatch = responseText.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
        let jsonString = null;
        
        if (fencedJsonMatch) {
          // Found a fenced code block, use the non-greedy match inside it
          jsonString = fencedJsonMatch[1];
        } else {
          // Fall back to non-greedy brace match (smallest {...} occurrence)
          const braceMatch = responseText.match(/\{[\s\S]*?\}/);
          if (braceMatch) {
            jsonString = braceMatch[0];
          }
        }
        
        if (jsonString) {
          // Trim whitespace and parse
          aiResponse = JSON.parse(jsonString.trim());
        } else {
          throw new Error('No JSON found in response');
        }
      } catch (parseError) {
        // Get configuration from environment variables with sensible defaults
        const authorName = env.BLOG_AUTHOR || "Paul Chris Luke";
        const siteBaseUrl = env.BLOG_BASE_URL || "https://paulchrisluke.com";
        const defaultImage = env.BLOG_DEFAULT_IMAGE || `${siteBaseUrl}/default.jpg`;
        
        // If parsing fails, create a structured response
        aiResponse = {
          date: requestData.digest.date,
          frontmatter: {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": `Daily Devlog — ${requestData.digest.date}`,
            "datePublished": requestData.digest.date,
            "author": authorName,
            "keywords": requestData.digest.metadata?.keywords || [],
            "video": [],
            "faq": [],
            "og": {
              "title": `Daily Devlog — ${requestData.digest.date}`,
              "description": "Daily development log",
              "type": "article",
              "url": `${siteBaseUrl}/${requestData.digest.date}`,
              "image": defaultImage
            }
          },
          body: response.response
        };
      }

      // Return the response
      const corsHeaders = createCorsHeaders(corsOrigin);
      return new Response(JSON.stringify(aiResponse), {
        status: 200,
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json',
        },
      });

    } catch (error) {
      console.error('Error processing request:', error);
      
      const corsHeaders = createCorsHeaders(corsOrigin);
      return new Response(JSON.stringify({
        error: 'Internal server error',
        message: error.message
      }), {
        status: 500,
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json',
        },
      });
    }
  },
};

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
