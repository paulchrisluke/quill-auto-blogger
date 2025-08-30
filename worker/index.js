import { Ai } from '@cloudflare/ai';

export default {
  async fetch(request, env, ctx) {
    // Handle CORS
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    // Only allow POST requests
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { 
        status: 405,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Content-Type': 'text/plain',
        }
      });
    }

    try {
      // Parse the request body
      const requestData = await request.json();
      
      if (!requestData.digest) {
        return new Response('Missing digest data', { 
          status: 400,
          headers: {
            'Access-Control-Allow-Origin': '*',
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
        const jsonMatch = responseText.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          aiResponse = JSON.parse(jsonMatch[0]);
        } else {
          throw new Error('No JSON found in response');
        }
      } catch (parseError) {
        // If parsing fails, create a structured response
        aiResponse = {
          date: requestData.digest.date,
          frontmatter: {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": `Daily Devlog — ${requestData.digest.date}`,
            "datePublished": requestData.digest.date,
            "author": "Paul Chris Luke",
            "keywords": requestData.digest.metadata?.keywords || [],
            "video": [],
            "faq": [],
            "og": {
              "title": `Daily Devlog — ${requestData.digest.date}`,
              "description": "Daily development log",
              "type": "article",
              "url": `https://paulchrisluke.com/${requestData.digest.date}`,
              "image": "https://paulchrisluke.com/default.jpg"
            }
          },
          body: response.response
        };
      }

      // Return the response
      return new Response(JSON.stringify(aiResponse), {
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Content-Type': 'application/json',
        },
      });

    } catch (error) {
      console.error('Error processing request:', error);
      
      return new Response(JSON.stringify({
        error: 'Internal server error',
        message: error.message
      }), {
        status: 500,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Content-Type': 'application/json',
        },
      });
    }
  },
};

async function loadVoicePrompt(env) {
  // Check if a custom prompt path is provided
  const promptPath = env.BLOG_VOICE_PROMPT_PATH || 'prompts/default_voice.md';
  
  try {
    // For now, return a default prompt
    // In a real implementation, you might want to store this in KV or R2
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
  } catch (error) {
    console.error('Error loading voice prompt:', error);
    return 'Write a technical blog post in a professional but approachable tone.';
  }
}
