# Quill Auto Blogger Cloudflare Worker

A clean, focused Cloudflare Worker that serves blog content and API endpoints for the Quill Auto Blogger system.

## Architecture

The worker follows a clean separation of concerns:

- **`worker.js`** - Core routing and API logic (kept minimal and focused)
- **`index.html`** - Static home page with API documentation
- **`upload-index.sh`** - Helper script to upload the index file to R2

## Features

### Core Functions
- **Blog API** (`/blog/{date}`) - Serves FINAL digest data as JSON with AI enhancements
- **Asset Serving** (`/assets/*`) - Serves static assets from R2 bucket
- **Health Check** (`/health`) - Simple health endpoint
- **Home Page** (`/`) - Serves the static index.html file

### CORS Support
- Handles preflight requests
- Adds CORS headers to all responses
- Configurable for cross-origin access

### Edge Caching
- Browser cache: 5 minutes for API, 1 hour for HTML
- Edge cache: 30 minutes for API, 24 hours for HTML
- CDN-optimized headers

## Setup

### Prerequisites
1. **Install Wrangler CLI:**
   ```bash
   npm install -g wrangler
   ```

2. **Authenticate with Cloudflare:**
   ```bash
   wrangler login
   ```

### Configuration

The worker uses the same `CLOUDFLARE_API_TOKEN` from your root `.env` file for authentication.
No additional environment configuration is needed in the worker.

### Deployment

1. **Deploy the worker:**
   ```bash
   wrangler deploy
   ```

2. **Upload the index.html file:**
   ```bash
   ./upload-index.sh
   ```
   
   Note: This uploads to the `quill-auto-blogger` R2 bucket.

3. **Test the endpoints:**
   ```bash
   # Test home page
   curl https://your-worker.your-subdomain.workers.dev/
   
   # Test blog API
   curl https://your-worker.your-subdomain.workers.dev/blog/2025-08-29
   
   # Test health
   curl https://your-worker.your-subdomain.workers.dev/health
   ```

## Environment Variables

The worker uses the following from your root `.env` file:
- `CLOUDFLARE_API_TOKEN` - Used for authentication and API access

### R2 Bucket Binding
- `BLOG_BUCKET` - R2 bucket containing blog data and index.html (configured in wrangler.toml)

## File Structure

```
cloudflare-worker/
├── worker.js          # Main worker logic (clean and focused)
├── index.html         # Static home page with API docs
├── upload-index.sh    # Script to upload index.html to R2
├── wrangler.toml      # Worker configuration
└── README.md          # This file
```

## Benefits of This Structure

1. **Separation of Concerns** - Worker handles logic, HTML handles presentation
2. **Maintainability** - Easy to update the home page without touching worker code
3. **Performance** - Static HTML served from R2 with proper caching
4. **Clean Code** - Worker.js is now focused and readable
5. **Scalability** - Easy to add more static assets or modify the home page
6. **Pure JSON API** - Serves FINAL digest data with AI enhancements for frontend consumption
7. **Global Distribution** - R2-backed API with edge caching for fast global access
8. **Simplified Configuration** - Uses existing root .env file, no duplication
9. **Type Safe** - R2 bucket binding provides proper R2Bucket object type

## Future Enhancements

- Add more API endpoints as needed
- Implement authentication for protected routes
- Add rate limiting
- Expand asset serving capabilities
- Add monitoring and logging
