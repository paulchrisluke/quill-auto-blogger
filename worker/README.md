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

3. Deploy the worker:
```bash
cd worker
npm install
wrangler deploy
```

## Configuration

The worker uses the following environment variables:

- `BLOG_VOICE_PROMPT_PATH`: Path to the voice prompt file (optional, defaults to default prompt)

## API Endpoints

### POST /generate-blog

Generates an AI-written blog post from digest data.

**Request Body:**
```json
{
  "digest": {
    "date": "2025-08-29",
    "twitch_clips": [...],
    "github_events": [...],
    "metadata": {...}
  }
}
```

**Response:**
```json
{
  "date": "2025-08-29",
  "frontmatter": {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Daily Devlog — Aug 29, 2025",
    "datePublished": "2025-08-29",
    "author": "Paul Chris Luke",
    "keywords": [...],
    "video": [...],
    "faq": [...],
    "og": {...}
  },
  "body": "# Daily Devlog — August 29, 2025\n\n..."
}
```

## Development

To run the worker locally:

```bash
wrangler dev
```

## Deployment

The worker is automatically deployed to Cloudflare Workers when you run `wrangler deploy`.

The worker URL will be provided after deployment and should be set as the `CLOUDFLARE_WORKER_URL` environment variable in your main application.
