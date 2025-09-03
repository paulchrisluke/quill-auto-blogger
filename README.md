# Activity Fetcher

A Python project that fetches and processes Twitch clips and GitHub activity, with automatic transcription using the Cloudflare Workers AI Whisper API. It also includes a digest builder that generates daily blog posts with structured front matter for SEO and social sharing.

## M2 Features - Capture & Control

- **OBS Integration**: Safe start/stop recording via Discord/CLI
- **Story State Management**: Persist recording status in v2 digest files
- **Discord Bot**: Slash commands for story control and outlines
- **CLI Interface**: Command-line recording control
- **24h Reminders**: Gentle nudges for missing explainers
- **Local-first**: Minimal dependencies, no external services required

## M4 Features - Auto Blog Generation

- **Blog Generation**: Automatically generate markdown blog posts from daily development data
- **CLI Blog Commands**: Generate and preview blog posts
- **Structured Content**: SEO-optimized frontmatter and content organization
- **Environment Configuration**: Flexible target repository and path configuration

## M5 Features - Pure JSON API & AI Enhancement

- **Pure JSON API**: Cloudflare Worker serves enhanced blog data as JSON (no HTML rendering)
- **Dual Pipeline**: PRE-CLEANED (raw data) and FINAL (AI-enhanced) digest versions
- **AI Enhancement**: Automatic generation of SEO descriptions, holistic intros, wrap-ups, and story intros
- **R2 Integration**: Automatic upload to Cloudflare R2 for global API distribution
- **Structured SEO**: JSON-LD schema data embedded in frontmatter for search engines

## Features

- **Twitch Integration**: Fetch recent clips for any broadcaster
- **Audio Transcription**: Extract audio from videos and transcribe using Cloudflare Workers AI Whisper
- **GitHub Activity**: Track commits, PRs, issues, and other repository events
- **Deduplication**: Smart caching prevents processing duplicate content
- **Structured Storage**: All data stored as timestamped JSON files
- **CLI Interface**: Easy-to-use command-line interface
- **Authentication**: Automatic token refresh for Twitch OAuth
- **Digest Builder**: Generate daily blog posts as structured JSON for AI ingestion
- **SEO**: Schema.org metadata for Articles, VideoObjects, and FAQs
- **Social Sharing**: Open Graph metadata for social media platforms

## Prerequisites

- Python 3.8+
- ffmpeg (for audio extraction and video stitching)
- Playwright (for HTML→PNG rendering)
- Twitch Developer Account
- GitHub Personal Access Token
- Cloudflare Account with Workers AI
- PyYAML (for YAML front matter generation)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd quill-auto-blogger
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install ffmpeg:
   - **macOS**: `brew install ffmpeg`
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`
   - **Windows**: Download from https://ffmpeg.org/download.html

4. Install Playwright and Chromium browser:
```bash
python -m tools.setup_playwright
```

5. Set up environment variables:
```bash
cp env.example .env
# Edit .env with your credentials
```

## Configuration

### Twitch Setup

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Create a new application
3. Get your Client ID and Client Secret
4. Find your broadcaster ID:
   - Use a tool like [Twitch Username to User ID Converter](https://www.streamweasels.com/tools/convert-twitch-username-to-user-id/)
   - Or use the Twitch API: `GET https://api.twitch.tv/helix/users?login=YOUR_USERNAME`
5. Add them to your `.env` file

### GitHub Setup

1. Go to [GitHub Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Generate a new **fine-grained token** with appropriate permissions:
   - Repository access: Select repositories or "All repositories"
   - Permissions: 
     - Repository permissions: Contents (Read), Metadata (Read)
     - Account permissions: Email addresses (Read)
3. Set expiration (recommended: 90 days)
4. Add the token to your `.env` file
5. Run `python main.py setup-github-token` to initialize token caching

### Cloudflare Setup

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Create an API token with Workers AI permissions
3. Get your Account ID and API Token
4. Add them to your `.env` file

## Usage

### CLI Commands

```bash
# Fetch and transcribe Twitch clips
python main.py fetch-twitch --broadcaster username

# Fetch GitHub activity for a user
python main.py fetch-github --user username

# Fetch GitHub activity for a repository
python main.py fetch-github --repo owner/repo

# Run both Twitch and GitHub fetchers
python main.py sync-all

# Validate authentication
python main.py validate-auth

# Setup GitHub token (first time only)
python main.py setup-github-token

# Get broadcaster ID from username
python main.py get-broadcaster-id username

# Clear cache and seen IDs
python main.py clear-cache

# Build digest for a specific date
python main.py build-digest --date 2025-01-15

# Build digest for a specific date (alternative command)
python main.py build-digest-for-date 2025-01-15

# Build digest for the latest available date
python main.py build-latest-digest

# Blog generation (M4)
devlog blog generate --date 2025-01-15
devlog blog preview --date 2025-01-15

# Static site publishing (M6)
devlog site build
devlog site publish         # uploads index/docs + all API-v3 digests
devlog site publish --dry-run
```

### Examples

```bash
# Fetch clips from a specific broadcaster (by username)
python main.py fetch-twitch --broadcaster shroud

# Fetch clips from a specific broadcaster (by ID)
python main.py fetch-twitch --broadcaster-id 12345678

# Fetch GitHub activity for your account
python main.py fetch-github --user your-username

# Fetch activity for a specific repository
python main.py fetch-github --repo facebook/react

# Run full sync with environment variables
python main.py sync-all

# Setup GitHub token (first time setup)
python main.py setup-github-token

# Get broadcaster ID from username
python main.py get-broadcaster-id shroud

# Build digest for latest date
python main.py build-latest-digest

# Build digest for specific date
python main.py build-digest --date 2025-01-15

# Build digest for specific date (alternative command)
python main.py build-digest-for-date 2025-01-15

# Blog generation (M4)
devlog blog generate --date 2025-01-15
devlog blog preview --date 2025-01-15
```

## Data Storage

All data is stored in the `data/` directory with the following structure:

```
data/
├── YYYY-MM-DD/
│   ├── twitch_clip_clip_id_title_20231201_143022.json
│   ├── github_event_event_id_repo_20231201_143045.json
│   └── ...
└── seen_ids.json

blogs/
├── YYYY-MM-DD/
│   ├── PRE-CLEANED-YYYY-MM-DD_digest.json (raw data, no AI)
│   └── FINAL-YYYY-MM-DD_digest.json (AI-enhanced for API)
└── ...
```

### Twitch Clip Data Structure

```json
{
  "id": "clip_id",
  "title": "Clip Title",
  "url": "https://clips.twitch.tv/clip_id",
  "broadcaster_name": "broadcaster",
  "created_at": "2023-12-01T14:30:22+00:00",
  "transcript": "Transcribed audio content...",
  "video_path": "/tmp/video_clip_id.mp4",
  "audio_path": "/tmp/audio_clip_id.wav",
  "duration": 30.5,
  "view_count": 1000,
  "language": "en"
}
```

### GitHub Event Data Structure

```json
{
  "id": "event_id",
  "type": "PushEvent",
  "repo": "owner/repo",
  "actor": "username",
  "created_at": "2023-12-01T14:30:45+00:00",
  "details": {
    "commits": 3,
    "branch": "main",
    "commit_messages": ["feat: add new feature", "fix: bug fix"]
  },
  "url": "https://github.com/owner/repo/commit/abc123",
  "title": null,
  "body": null
}
```

### Blog Digest Structure

```json
{
  "date": "2025-01-15",
  "twitch_clips": [...],
  "github_events": [...],
  "metadata": {
    "total_clips": 3,
    "total_events": 5,
    "keywords": ["repo_name", "language", "event_type"],
    "date_parsed": "2025-01-15"
  }
}
```

### Markdown Front Matter Structure

```yaml
---
title: "Daily Devlog — Jan 15, 2025"
date: "2025-01-15"
author: "Your Name"
schema:
  article:
    "@context": "https://schema.org"
    "@type": "Article"
    headline: "Daily Devlog — Jan 15, 2025"
    datePublished: "2025-01-15"
    author:
      "@type": "Person"
      name: "Your Name"
    keywords: ["repo_name", "language", "event_type"]
    url: "https://yourblog.com/blog/2025-01-15"
    image: "https://yourblog.com/default.jpg"
  videos:
    - "@type": "VideoObject"
      name: "Clip Title"
      description: "Clip description..."
      url: "https://clips.twitch.tv/clip_id"
      uploadDate: "2025-01-15T12:00:00+00:00"
      duration: "PT30S"
      thumbnailUrl: "https://clips-media-assets2.twitch.tv/clip_id/preview-480x272.jpg"
  faq:
    "@context": "https://schema.org"
    "@type": "FAQPage"
    mainEntity:
      - "@type": "Question"
        name: "Question text"
        acceptedAnswer:
          "@type": "Answer"
          text: "Answer text"
og:
  og:title: "Daily Devlog — Jan 15, 2025"
  og:description: "Daily development log with 3 Twitch clips and 5 GitHub events"
  og:type: "article"
```

## Blog Generation Workflow (M4)

The blog generation system automatically creates both markdown blog posts and JSON API endpoints from your daily development data.

### Quick Start

1. **Generate a blog post**:
   ```bash
   # Generate for latest date
   devlog blog generate
   
   # Generate for specific date
   devlog blog generate --date 2025-01-15
   ```

2. **Preview the content**:
   ```bash
   devlog blog preview --date 2025-01-15
   ```

### Blog Commands

#### `devlog blog generate`
Generate a markdown blog post from your daily development data.

**Options:**
- `--date YYYY-MM-DD`: Specific date (defaults to latest available date)

**Output:**
- Creates `drafts/YYYY-MM-DD.md` with the generated markdown
- Creates `blogs/YYYY-MM-DD/PRE-CLEANED-YYYY-MM-DD_digest.json` (raw data)
- Creates `blogs/YYYY-MM-DD/FINAL-YYYY-MM-DD_digest.json` (AI-enhanced for API)
- Uploads FINAL version to R2 bucket for Worker API consumption
- Displays title and story count

#### `devlog blog preview`
Preview the content of a blog post without generating files.

**Options:**
- `--date YYYY-MM-DD`: Required date

**Output:**
- Shows title, date, tags, and first ~10 lines of content

### API Access (M5)

The generated blog content is available via the Cloudflare Worker API:

```bash
# Get complete blog data for a date
curl "https://quill-blog-api.paulchrisluke.workers.dev/blog/2025-01-15"

# Response includes:
# - Frontmatter with SEO metadata and JSON-LD schema
# - Story packets with AI-enhanced intros
# - All assets and metadata
```

**API Endpoints:**
- `/blog/{date}` - Complete blog data as JSON
- `/assets/*` - Static assets (images, videos)
- `/health` - Health check endpoint

### Static Site Publishing

The project includes a minimal R2 publisher for static site files and blog JSON:

- **`devlog site build`**: Creates `out/site/{index.html, docs.html}` from root HTML files
- **`devlog site publish`**: Uploads site files and API-v3 digests to R2 with idempotency
- **Idempotent uploads**: Files are only uploaded if content has changed (MD5/ETag comparison)
- **Proper headers**: HTML gets `text/html; charset=utf-8` with 1-hour cache, JSON gets `application/json` with 5-minute cache
- **R2 integration**: Uses existing R2 credentials via `AuthService.get_r2_credentials()`

The publisher uploads:
- `index.html` → R2 root
- `docs.html` → R2 root  
- `blogs/YYYY-MM-DD/API-v3-YYYY-MM-DD_digest.json` → R2 `blogs/` path

## Video Rendering (M3)

The project now uses an HTML→PNG renderer for creating story videos. This replaces the legacy FFmpeg drawtext approach with a more flexible and maintainable solution.

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Setup Playwright browser
python -m tools.setup_playwright

# Run tests to verify setup
python -m pytest tests/test_renderer_html.py -v

# Render videos for a specific date
python -m tools.renderer_html 2025-01-15

# Or use the devlog command
python -m tools.devlog render --date 2025-01-15
```

### Renderer Features

- **HTML Templates**: Modular templates for intro, why, highlights, and outro slides
- **GitHub-style Design**: Clean typography with Inter font, high contrast cards
- **Brand Tokens**: Consistent spacing, colors, and shadows via CSS variables
- **Smart Text Handling**: Auto-truncation, ellipsis, and quality validation
- **1080×1920 Output**: Optimized for vertical video platforms
- **FFmpeg Stitching**: High-quality MP4 output with H.264 encoding
- **Environment Configuration**: Configurable viewport, fps, quality via env vars
- **Idempotent Rendering**: Skip re-render if video exists (unless --force)
- **Integration Tests**: Comprehensive end-to-end testing with theme validation

### Slide Types

1. **Intro Slide**: Title with subtitle (repo, PR number, date)
2. **Why Slide**: "Why it matters" explanation
3. **Highlights Slides**: Up to 3 slides with 2-3 bullet points each
4. **Outro Slide**: CTA with attribution

### Environment Configuration

The renderer can be configured via environment variables:

```bash
# Viewport size for HTML→PNG rendering
RENDERER_VIEWPORT=1080x1920

# Video output settings
RENDERER_FPS=30
RENDERER_SLIDE_SECONDS=6
RENDERER_CRF=18

# Force re-render even if video exists
RENDERER_FORCE=false
```

### Troubleshooting

- **Font Issues**: The renderer uses Google Fonts (Inter) with system fallbacks
- **macOS Permissions**: Ensure Playwright has permission to run headless browser
- **FFmpeg Errors**: Verify ffmpeg is installed and in PATH
- **Brand Tokens**: CSS variables ensure consistent design across all slides
- **Quality Issues**: Check RENDERER_CRF setting (lower = higher quality, 18-28 recommended)
- **Missing Libraries**: On Linux, install: `sudo apt-get install libnss3 libatk-bridge2.0-0 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libdrm2 libxss1 libgtk-3-0 libxshmfence1`
- **CI Setup**: Use `python -m tools.setup_ci` to install dependencies in CI environment
- **Theme Issues**: Set `RENDERER_THEME=dark` for dark mode slides
- **Testing**: Run `python -m pytest tests/test_renderer_html.py -v` for comprehensive testing

## Testing

Run the test suite:

```bash
pytest tests/
```

Run specific test categories:

```bash
# Test authentication
pytest tests/test_auth.py

# Test models
pytest tests/test_models.py

# Test utilities
pytest tests/test_utils.py

# Test transcription
pytest tests/test_transcribe.py

# Test blog digest builder
pytest tests/test_blog.py

# Test OBS controller
pytest tests/test_obs_controller.py

# Test story state
pytest tests/test_story_state.py

# Test HTML renderer
pytest tests/test_renderer_html.py

# Test HTML renderer integration (end-to-end)
pytest tests/test_renderer_html.py::TestRendererIntegration -v
```

### M2 - Capture & Control Usage

#### Start Bots

```bash
# Discord Bot
python discord_bot.py

# Reminder Service (optional)
python -m services.reminder
```

#### Record from CLI

```bash
# Start recording for a story
python -m cli.devlog record --story story_20250827_pr35 --action start --date 2025-08-27

# Stop recording for a story
python -m cli.devlog record --story story_20250827_pr35 --action stop --date 2025-08-27
```

#### Discord Commands

- `/story_list` - List today's stories with statuses
- `/record_start <id>` - Start recording for a story
- `/record_stop <id>` - Stop recording for a story  
- `/story_outline <id>` - Generate talk track outline

#### Webhook Endpoints

```bash
# Start recording via HTTP
curl -X POST http://localhost:8000/control/record/start \
  -H "Content-Type: application/json" \
  -d '{"story_id": "story_20250827_pr35", "date": "2025-08-27"}'

# Stop recording via HTTP
curl -X POST http://localhost:8000/control/record/stop \
  -H "Content-Type: application/json" \
  -d '{"story_id": "story_20250827_pr35", "date": "2025-08-27"}'
```
```

## Project Structure

```
quill-auto-blogger/
├── main.py                 # CLI entrypoint
├── models.py              # Pydantic schemas
├── services/
│   ├── __init__.py
│   ├── auth.py            # Authentication service
│   ├── twitch.py          # Twitch API client
│   ├── github.py          # GitHub API client
│   ├── transcribe.py      # Audio transcription
│   ├── utils.py           # Cache and utility functions
│   ├── blog.py            # Digest builder and front matter generator
│   ├── obs_controller.py  # OBS recording control
│   ├── story_state.py     # Story state persistence
│   ├── outline.py         # Talk track generation
│   └── reminder.py        # 24h reminder service
├── data/                  # Stored JSON data
├── blogs/                 # Generated JSON digests (pre-cleaned for AI processing)
├── tests/                 # Test suite
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_models.py
│   ├── test_utils.py
│   ├── test_transcribe.py
│   ├── test_blog.py
│   ├── test_obs_controller.py
│   └── test_story_state.py
├── requirements.txt
├── env.example
└── README.md
```

## API Rate Limits

- **Twitch**: 800 requests per minute for authenticated requests
- **GitHub**: 5,000 requests per hour for authenticated requests
- **Cloudflare Workers AI**: Varies by plan

## Error Handling

The application includes comprehensive error handling:

- Network timeouts and retries
- API rate limiting
- File system errors
- Authentication failures
- Transcription errors

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Common Issues

1. **ffmpeg not found**: Install ffmpeg and ensure it's in your PATH
2. **Authentication errors**: Check your API credentials in `.env`
3. **GitHub token expired**: Fine-grained tokens expire. Run `python main.py setup-github-token` after refreshing
4. **Rate limiting**: The app handles rate limits automatically, but you may need to wait
5. **Transcription failures**: Ensure your Cloudflare credentials are correct and you have sufficient credits

### Debug Mode

Enable debug logging by setting the `DEBUG` environment variable:

```bash
export DEBUG=1
python main.py fetch-twitch
```

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review the test files for usage examples
3. Open an issue on GitHub
