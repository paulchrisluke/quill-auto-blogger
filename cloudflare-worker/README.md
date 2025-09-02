# Cloudflare Worker for Quill Auto Blogger

This Cloudflare Worker provides a fast, edge-cached API for serving blog posts and assets from your Quill Auto Blogger application.

## Features

- **Edge Caching**: Responses are cached at Cloudflare's edge for fast global delivery
- **R2 Integration**: Direct access to Cloudflare R2 storage for assets
- **CORS Support**: Built-in CORS handling for cross-origin requests
- **API Proxy**: Forwards requests to your local API server and caches responses
- **Asset Serving**: Serves static assets (images, videos) directly from R2

## Prerequisites

1. **Cloudflare Account**: You need a Cloudflare account with Workers enabled
2. **R2 Bucket**: Your `quill-auto-blogger` R2 bucket should be set up
3. **Wrangler CLI**: Install Cloudflare's Wrangler CLI tool

## Installation

1. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```

2. Login to Cloudflare:
   ```bash
   wrangler login
   ```

3. Set your Cloudflare account ID:
   ```bash
   wrangler config set account-id YOUR_ACCOUNT_ID
   ```

## Configuration

1. **Update `wrangler.toml`**:
   - Set your R2 bucket name
   - Update `LOCAL_API_URL` for production
   - Configure environment-specific settings

2. **Set Secrets**:
   ```bash
   wrangler secret put WORKER_BEARER_TOKEN
   # Enter your bearer token when prompted
   ```

## Deployment

### Development
```bash
cd cloudflare-worker
wrangler dev
```

### Production
```bash
cd cloudflare-worker
wrangler deploy --env production
```

### Staging
```bash
cd cloudflare-worker
wrangler deploy --env staging
```

## API Endpoints

The worker provides the following endpoints:

### Blog Posts
- `GET /api/blog/{date}` - Get complete blog post data
- `GET /api/blog/{date}/markdown` - Get raw markdown content
- `GET /api/blog/{date}/digest` - Get digest data

### Assets
- `GET /api/assets/stories/{date}` - List all story assets for a date
- `GET /api/assets/stories/{date}/{story_id}` - Get assets for a specific story
- `GET /api/assets/blog/{date}` - Get all assets for a blog post

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOCAL_API_URL` | URL of your local API server | `http://localhost:8000` |
| `WORKER_BEARER_TOKEN` | Secret token for API authentication | Required |
| `BLOG_BUCKET` | R2 bucket binding for assets | `quill-auto-blogger` |

## Caching Strategy

- **Blog Data**: 5 minutes browser, 1 hour edge
- **Asset Metadata**: 5 minutes browser, 30 minutes edge
- **Static Assets**: 24 hours browser and edge

## Security

- **Bearer Token**: All API requests require valid `Authorization: Bearer <token>` header
- **CORS**: Configured for cross-origin requests (customize as needed)
- **Input Validation**: Date format and path validation

## Monitoring

Monitor your worker in the Cloudflare dashboard:
- **Analytics**: Request counts, response times, cache hit rates
- **Logs**: Real-time request logs and errors
- **Performance**: Edge caching effectiveness

## Troubleshooting

### Common Issues

1. **R2 Access Denied**: Check R2 bucket permissions and API tokens
2. **API Timeout**: Verify your local API server is accessible
3. **CORS Errors**: Check CORS configuration in your local API
4. **Cache Misses**: Verify cache headers are being set correctly

### Debug Mode

Enable debug logging in development:
```bash
wrangler dev --log-level debug
```

## Future Enhancements

- **Direct R2 Asset Serving**: Serve assets directly from R2 without proxying
- **Image Optimization**: Automatic image resizing and format conversion
- **Rate Limiting**: Implement request rate limiting
- **Analytics**: Custom analytics and metrics collection
- **A/B Testing**: Support for content variants and testing

## Support

For issues and questions:
1. Check Cloudflare Worker logs
2. Verify R2 bucket configuration
3. Test local API endpoints
4. Review CORS and authentication setup
