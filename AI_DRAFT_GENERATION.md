# AI Draft Generation - Phase 3

This document describes the AI-powered blog draft generation feature that extends the activity fetcher to automatically create blog posts from structured digest data.

## Overview

The AI draft generation feature allows you to automatically generate blog posts from your daily activity data using Cloudflare Workers AI. The system:

1. Reads pre-cleaned digest JSON files
2. Sends the data to a Cloudflare Worker with AI capabilities
3. Generates structured blog content with frontmatter and body
4. Saves drafts for human review before publishing

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CLI Command   │───▶│  Cloudflare      │───▶│  AI Response    │
│ generate-blog   │    │  Worker          │    │  (JSON)         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Digest JSON    │    │  GPT-4o-mini     │    │  Draft File     │
│  (Input)        │    │  AI Model        │    │  (Output)       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Setup

### 1. Environment Configuration

Add the following variables to your `.env` file:

```bash
# Cloudflare Worker Configuration
CLOUDFLARE_WORKER_URL=https://your-worker.your-subdomain.workers.dev

# Blog AI Voice Configuration
BLOG_VOICE_PROMPT_PATH=prompts/paul_chris_luke.md
```

### 2. Cloudflare Worker Deployment

1. Navigate to the worker directory:
   ```bash
   cd worker
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Deploy the worker:
   ```bash
   wrangler deploy
   ```

4. Note the worker URL and add it to your `.env` file.

### 3. Voice Prompts

The system uses configurable voice prompts to control the AI's writing style:

- **Default**: `prompts/default_voice.md` - Professional technical blog style
- **Custom**: `prompts/paul_chris_luke.md` - Paul Chris Luke's personal voice

You can create custom voice prompts by:
1. Creating a new `.md` file in the `prompts/` directory
2. Setting `BLOG_VOICE_PROMPT_PATH` in your `.env` file

## Usage

### Basic Workflow

1. **Build a digest** (if you haven't already):
   ```bash
   python main.py build-digest --date 2025-08-29
   ```

2. **Generate AI blog draft**:
   ```bash
   python main.py generate-blog --date 2025-08-29
   ```

3. **Review the draft**:
   - Check `drafts/2025-08-29-DRAFT.json`
   - Edit as needed
   - Move to your Nuxt repo when ready

### Command Options

```bash
# Generate for specific date
python main.py generate-blog --date 2025-08-29

# Generate for latest available date
python main.py generate-blog
```

### Output Format

The AI generates a structured JSON response:

```json
{
  "date": "2025-08-29",
  "frontmatter": {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Daily Devlog — Aug 29, 2025",
    "datePublished": "2025-08-29",
    "author": "Paul Chris Luke",
    "keywords": ["twitch", "github", "AI"],
    "video": [...],
    "faq": [...],
    "og": {
      "title": "...",
      "description": "...",
      "type": "article",
      "url": "https://paulchrisluke.com/2025-08-29",
      "image": "https://paulchrisluke.com/default.jpg"
    }
  },
  "body": "# Daily Devlog — August 29, 2025\n\nToday was a productive day..."
}
```

## File Structure

```
quill-auto-blogger/
├── main.py                 # CLI with generate-blog command
├── services/
│   └── blog.py            # Extended with AI generation methods
├── digests/               # Input JSON digests
├── drafts/                # AI blog drafts for review
├── prompts/               # Voice/style prompt files
│   ├── default_voice.md
│   └── paul_chris_luke.md
├── worker/                # Cloudflare Worker
│   ├── index.js           # Worker endpoint
│   ├── package.json
│   └── wrangler.toml
└── tests/
    └── test_blog_ai.py    # AI generation tests
```

## API Reference

### Cloudflare Worker Endpoint

**POST** `/generate-blog`

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
  "frontmatter": {...},
  "body": "..."
}
```

### BlogDigestBuilder Methods

#### `generate_ai_blog(target_date: str) -> Dict[str, Any]`
Generates an AI-written blog draft from digest data.

#### `save_ai_draft(target_date: str, ai_response: Dict[str, Any]) -> Path`
Saves AI-generated blog draft to file.

#### `load_digest_from_file(target_date: str) -> Dict[str, Any]`
Loads a digest from the digests directory.

## Testing

Run the AI generation tests:

```bash
python -m pytest tests/test_blog_ai.py -v
```

## Error Handling

The system handles various error conditions:

- **Missing Worker URL**: Raises `ValueError` if `CLOUDFLARE_WORKER_URL` not configured
- **HTTP Errors**: Wraps in `RuntimeError` with descriptive message
- **Invalid Responses**: Validates response structure and raises `RuntimeError` if invalid
- **File System Errors**: Uses atomic writes to prevent corruption

## Customization

### Voice Prompts

Create custom voice prompts by writing markdown files that describe the desired writing style. Include:

- Writing tone and personality
- Content structure preferences
- Technical depth requirements
- Specific phrases or terminology to use

### AI Model Configuration

The worker uses `@cf/openai/gpt-4o-mini` by default. You can modify the worker to use different models or adjust parameters like:

- `max_tokens`: Maximum response length
- `temperature`: Creativity level (0.0-1.0)
- `stream`: Whether to stream responses

## Troubleshooting

### Common Issues

1. **Worker URL not configured**
   - Ensure `CLOUDFLARE_WORKER_URL` is set in `.env`
   - Verify the worker is deployed and accessible

2. **AI response parsing errors**
   - Check that the worker is returning valid JSON
   - Verify the response contains required `frontmatter` and `body` fields

3. **Timeout errors**
   - Increase the timeout in the `generate_ai_blog` method
   - Check network connectivity to Cloudflare

### Debug Mode

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

Potential improvements for future phases:

1. **Multiple AI Models**: Support for different AI models (Claude, Gemini, etc.)
2. **Template System**: Customizable blog post templates
3. **Batch Processing**: Generate multiple drafts at once
4. **Quality Scoring**: AI-generated quality metrics for drafts
5. **Auto-publishing**: Direct integration with Nuxt repo
6. **Feedback Loop**: Learn from human edits to improve future generations

## Security Considerations

- Worker endpoints are protected by CORS
- No sensitive data is sent to the AI service
- All file operations use atomic writes
- Environment variables are used for configuration
- Input validation prevents injection attacks
