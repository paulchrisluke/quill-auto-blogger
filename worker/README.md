# Blog AI Worker

This Cloudflare Worker handles AI-powered blog generation using Cloudflare Workers AI.

## Setup

1. Install Wrangler CLI:
```bash
npm install -g wrangler
```

2. Authenticate with Cloudflare:
```bash
wrangler login
```

3. Create a minimal `wrangler.toml` configuration file:
```toml
name = "blog-ai-worker"
main = "index.js"
compatibility_date = "2024-01-01"
account_id = "<your_account_id>"

[ai]
binding = "AI"
```

**Important:** Replace `<your_account_id>` with your actual Cloudflare account ID and adjust the `main` path if your entry file is different from `index.js`.

4. Deploy the worker:
```bash
cd worker
npm install
wrangler deploy
```

## Configuration

The worker uses the following environment variables:

- `BLOG_AUTHOR`: Author name for blog posts (defaults to "Paul Chris Luke")
- `BLOG_BASE_URL`: Base URL for the blog (defaults to "https://paulchrisluke.com")
- `BLOG_DEFAULT_IMAGE`: Default image URL for blog posts (defaults to base URL + "/default.jpg")
- `BLOG_VOICE_PROMPT`: Voice prompt text for AI blog generation (can be set as TOML variable or secret)
- `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins (defaults to "*" for development)

### Voice Prompt Configuration

You have two options for configuring the voice prompt:

#### Option 1: TOML Variable (for non-sensitive prompts)
Add the prompt directly to your `wrangler.toml`:
```toml
BLOG_VOICE_PROMPT = "You are a technical blogger writing in a conversational style..."
```

#### Option 2: Secret (for sensitive prompts)
Store the prompt as a Cloudflare secret:
```bash
wrangler secret put BLOG_VOICE_PROMPT
```
Then paste your prompt text when prompted.

### KV/R2 Binding Configuration

The worker uses Cloudflare KV to store prompt files. Configure the binding in `wrangler.toml`:
```toml
[[kv_namespaces]]
binding = "PROMPTS"
id = "your-production-namespace-id"
preview_id = "your-preview-namespace-id"
```

At runtime, the worker will fetch prompts from KV using the key `default_voice.md` or `paul_chris_luke.md`.

## KV Storage Setup

The worker uses Cloudflare KV to store prompt files. To set up:

### Option 1: Automated Setup (Recommended)
```bash
npm run setup-kv
```

This will automatically:
- Create production and preview KV namespaces
- Update `wrangler.toml` with the correct namespace IDs
- Provide next steps for uploading prompts

### Option 2: Manual Setup
1. Create KV namespaces:
```bash
wrangler kv:namespace create "PROMPTS_KV"
wrangler kv:namespace create "PROMPTS_KV" --preview
```

2. Update `wrangler.toml` with the namespace IDs:
```toml
[[kv_namespaces]]
binding = "PROMPTS_KV"
id = "your-production-namespace-id"
preview_id = "your-preview-namespace-id"
```

3. Upload prompt files to KV:
```bash
npm run upload-prompts          # Upload to production
npm run upload-prompts:staging  # Upload to staging
```

4. Test the functionality:
```bash
npm test
```

The upload script will automatically upload both `prompts/default_voice.md` and `prompts/paul_chris_luke.md` to the KV store.

### Fallback Behavior

If KV storage is not available or a prompt is not found, the worker will fall back to a built-in default prompt. This ensures the worker continues to function even if KV is not properly configured.

## CORS Security

The worker implements CORS origin validation to prevent unauthorized access:

- **Development/Staging**: Uses `ALLOWED_ORIGINS = "*"` to allow all origins
- **Production**: Uses `ALLOWED_ORIGINS = "https://paulchrisluke.com,https://www.paulchrisluke.com"` to restrict to specific domains

To configure CORS for your deployment:

1. **For development**: Leave `ALLOWED_ORIGINS = "*"` in `wrangler.toml`
2. **For production**: Update the production environment in `wrangler.toml`:
   ```toml
   [env.production]
   ALLOWED_ORIGINS = "https://yourdomain.com,https://www.yourdomain.com"
   ```

The worker will automatically validate the `Origin` header against the allowed origins list and return appropriate CORS headers.

## API Endpoints

### POST /generate-blog

Generates an AI-written blog post from digest data.

**Authentication:**
All API requests require a Bearer token in the Authorization header:
```
Authorization: Bearer YOUR_API_TOKEN
```

**Headers:**
- `Authorization: Bearer YOUR_API_TOKEN` (required)
- `Content-Type: application/json` (required)

**Request Body Schema:**
```json
{
  "digest": {
    "date": "2025-08-29",
    "twitch_clips": [
      {
        "id": "string",
        "url": "string",
        "title": "string",
        "duration": "number",
        "view_count": "number",
        "created_at": "string"
      }
    ],
    "github_events": [
      {
        "id": "string",
        "type": "string",
        "repo": {
          "name": "string",
          "full_name": "string"
        },
        "payload": "object",
        "created_at": "string"
      }
    ],
    "metadata": {
      "total_clips": "number",
      "total_events": "number",
      "date_range": "string"
    }
  }
}
```

**Concrete Example:**
```bash
curl -X POST https://your-worker.your-subdomain.workers.dev/generate-blog \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "digest": {
      "date": "2025-08-29",
      "twitch_clips": [
        {
          "id": "123456789",
          "url": "https://clips.twitch.tv/ExampleClip",
          "title": "Building a React Component",
          "duration": 180,
          "view_count": 1500,
          "created_at": "2025-08-29T14:30:00Z"
        }
      ],
      "github_events": [
        {
          "id": "53875743956",
          "type": "PushEvent",
          "repo": {
            "name": "quill-auto-blogger",
            "full_name": "paulchrisluke/quill-auto-blogger"
          },
          "payload": {
            "ref": "refs/heads/main",
            "commits": [
              {
                "message": "Add blog generation feature"
              }
            ]
          },
          "created_at": "2025-08-29T15:45:00Z"
        }
      ],
      "metadata": {
        "total_clips": 1,
        "total_events": 1,
        "date_range": "2025-08-29"
      }
    }
  }'
```

**Response Schema:**
```json
{
  "date": "2025-08-29",
  "frontmatter": {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Daily Devlog — Aug 29, 2025",
    "datePublished": "2025-08-29",
    "author": "Paul Chris Luke",
    "keywords": ["development", "streaming", "github"],
    "video": [
      {
        "@type": "VideoObject",
        "name": "Building a React Component",
        "description": "Live coding session on React development",
        "thumbnailUrl": "https://example.com/thumbnail.jpg",
        "uploadDate": "2025-08-29T14:30:00Z",
        "duration": "PT3M",
        "url": "https://clips.twitch.tv/ExampleClip"
      }
    ],
    "faq": [
      {
        "question": "What did you work on today?",
        "answer": "Today I focused on building React components and pushing code to the quill-auto-blogger repository."
      }
    ],
    "og": {
      "title": "Daily Devlog — Aug 29, 2025",
      "description": "Today's development activities including React component building and GitHub contributions",
      "image": "https://paulchrisluke.com/default.jpg"
    }
  },
  "body": "# Daily Devlog — August 29, 2025\n\nToday I worked on building React components and made several contributions to the quill-auto-blogger repository..."
}
```

**CORS Configuration:**
For browser-based applications, the worker supports CORS with configurable origins:

- **Development**: `ALLOWED_ORIGINS = "*"` (allows all origins)
- **Production**: `ALLOWED_ORIGINS = "https://yourdomain.com,https://www.yourdomain.com"` (restricted origins)

**Security Notes:**
- The endpoint is protected by Bearer token authentication
- CORS origins are validated against the `ALLOWED_ORIGINS` environment variable
- Server-side token validation prevents unauthorized access
- For production use, ensure `ALLOWED_ORIGINS` is set to specific domains, not wildcards

## Development

To run the worker locally:

```bash
wrangler dev --remote
```

## Deployment

The worker is automatically deployed to Cloudflare Workers when you run `wrangler deploy`.

The worker URL will be provided after deployment and should be set as the `CLOUDFLARE_WORKER_URL` environment variable in your main application.
