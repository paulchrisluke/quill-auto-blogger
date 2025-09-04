"""
Pydantic models for story packet schema (v2 digest).
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from enum import Enum
import re


class StoryType(str, Enum):
    """Story type classification."""
    FEAT = "feat"
    FIX = "fix"
    PERF = "perf"
    SECURITY = "security"
    INFRA = "infra"
    DOCS = "docs"
    OTHER = "other"


class ExplainerStatus(str, Enum):
    """Status of explainer recording."""
    MISSING = "missing"
    RECORDING = "recording"
    RECORDED = "recorded"


class VideoStatus(str, Enum):
    """Status of final video rendering."""
    PENDING = "pending"
    RENDERING = "rendering"
    RENDERED = "rendered"
    FAILED = "failed"


class PairingInfo(BaseModel):
    """Information about clip pairing for a story."""
    clip_id: Optional[str] = None
    clip_created_at: Optional[datetime] = None
    score: Optional[float] = None  # 0.0-1.0 pairing confidence
    needs_broll: bool = True


class ExplainerInfo(BaseModel):
    """Information about explainer recording."""
    required: bool = True
    status: ExplainerStatus = ExplainerStatus.MISSING
    target_seconds: int = Field(default=90, ge=30, le=300)


class VideoInfo(BaseModel):
    """Information about final video artifact."""
    status: VideoStatus = VideoStatus.PENDING
    path: Optional[str] = None
    duration_s: Optional[float] = None
    canvas: str = "1080x1920"
    force_rerender: bool = False


class StoryLinks(BaseModel):
    """Links related to the story."""
    pr_url: Optional[str] = None
    commit_compare_url: Optional[str] = None
    clip_url: Optional[str] = None
    permalink: Optional[str] = None


class StoryPacket(BaseModel):
    """A story packet representing a single story from a merged PR."""
    id: str = Field(..., description="Stable identifier for the story")
    kind: Literal["pr_merge"] = "pr_merge"  # Future-proof for other story types
    repo: str
    pr_number: int
    merged_at: str
    title_raw: str = Field(..., description="Original PR title")
    title_human: str = Field(..., description="Human-readable title for display")
    why: str = Field(..., description="Why this story matters")
    highlights: List[str] = Field(default_factory=list, description="Key highlights")
    story_type: StoryType
    pairing: PairingInfo = Field(default_factory=PairingInfo)
    explainer: ExplainerInfo = Field(default_factory=ExplainerInfo)
    video: VideoInfo = Field(default_factory=VideoInfo)
    links: StoryLinks = Field(default_factory=StoryLinks)


class FrontmatterInfo(BaseModel):
    """Pre-computed frontmatter for blog generation."""
    title: str
    date: str
    author: Optional[str] = None
    canonical: Optional[str] = None
    image: Optional[str] = None
    og: Dict[str, Any] = Field(default_factory=dict)
    schema_data: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    tags: List[str] = Field(default_factory=list)
    lead: Optional[str] = None
    description: Optional[str] = None
    
    model_config = {"populate_by_name": True}


class DigestV2(BaseModel):
    """Version 2 digest schema with story packets."""
    version: Literal["2"] = "2"
    date: str
    twitch_clips: List[Dict[str, Any]] = Field(default_factory=list)
    github_events: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    frontmatter: FrontmatterInfo
    story_packets: List[StoryPacket] = Field(default_factory=list)


# Helper functions for story packet creation
def make_story_packet(
    pr_event: Dict[str, Any],
    pairing: PairingInfo,
    _clips: List[Dict[str, Any]],
) -> StoryPacket:
    """Create a story packet from a merged PR event."""
    
    # Extract PR details
    pr_number = pr_event["details"]["number"]
    
    # Handle datetime parsing - follow existing pattern from GitHub service
    created_at = pr_event["created_at"]
    if isinstance(created_at, str):
        merged_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    else:
        merged_at = created_at
    
    # Convert to strict ISO-8601 format for JSON output
    merged_at_iso = merged_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    title_raw = pr_event.get("title", "Untitled PR")
    
    # Generate human-readable title
    title_human = _generate_human_title(title_raw)
    
    # Determine story type from title and body
    story_type = _classify_story_type(title_raw, pr_event.get("body", ""))
    
    # Generate why and highlights
    why, highlights = _extract_why_and_highlights(pr_event)
    
    # Set explainer requirement based on story type
    explainer_required = story_type in [StoryType.FEAT, StoryType.PERF, StoryType.SECURITY]
    
    # Create story ID
    story_id = f"story_{merged_at.strftime('%Y%m%d')}_pr{pr_number}"
    
    # Create permalink
    permalink = f"/stories/{merged_at.strftime('%Y/%m/%d')}/pr-{pr_number}"
    
    return StoryPacket(
        id=story_id,
        repo=pr_event["repo"],
        pr_number=pr_number,
        merged_at=merged_at_iso,
        title_raw=title_raw,
        title_human=title_human,
        why=why,
        highlights=highlights,
        story_type=story_type,
        pairing=pairing,
        explainer=ExplainerInfo(required=explainer_required),
        links=StoryLinks(
            pr_url=pr_event.get("url"),
            permalink=permalink
        )
    )


def _generate_human_title(title_raw: str) -> str:
    """Generate a human-readable title from PR title."""
    # Remove common prefixes
    prefixes_to_remove = ["feat:", "fix:", "perf:", "security:", "infra:", "docs:"]
    title = title_raw
    for prefix in prefixes_to_remove:
        if title.lower().startswith(prefix):
            title = title[len(prefix):].strip()
            break
    
    # Handle feature branch patterns before slash normalization
    title_lower = title.lower()
    if "feature/cloudflare" in title_lower and "whisper" in title_lower:
        title = "Cloudflare Whisper Transcription"
    
    # Remove common path prefixes first (before converting slashes)
    path_prefixes = ["feature/", "fix/", "security/", "docs/", "perf/", "infra/"]
    title_lower = title.lower()
    for prefix in path_prefixes:
        if title_lower.startswith(prefix):
            title = title[len(prefix):].strip()
            break
    
    # Clean up remaining slashes and paths - convert to spaces and normalize
    title = title.replace("/", " ").replace("\\", " ")
    title = title.replace("-", " ").replace("_", " ")
    
    # Convert to title case first
    title = " ".join(word.capitalize() for word in title.split())
    
    # Then normalize technical terms to restore correct casing
    title = _normalize_technical_terms(title)
    
    # Create stable, human-readable titles
    title_lower = title.lower()
    if "twitch clips" in title_lower and ("download" in title_lower or "convert" in title_lower) and "transcribe" in title_lower:
        title = "Twitch Clips → Audio → Transcribe"
    elif "security" in title_lower and "implementation" in title_lower:
        title = "Security Implementation"
    elif "deduplication" in title_lower and "caching" in title_lower:
        title = "Deduplication & Caching"
    elif "cloudflare" in title_lower and "whisper" in title_lower:
        title = "Cloudflare Whisper Transcription"
    elif "content generation" in title_lower and "schema" in title_lower:
        title = "Content Generation Schema"
    elif "ai blog generation" in title_lower:
        title = "AI Blog Generation"
    
    # Add "Shipped:" prefix for features
    if any(word in title_raw.lower() for word in ["feat", "feature", "add", "implement"]):
        title = f"Shipped: {title}"
    
    return title


def _normalize_technical_terms(title: str) -> str:
    """Normalize technical terms for better title casing."""
    # Common technical terms that should be properly cased
    tech_terms = {
        "api": "API",
        "ai": "AI",
        "ui": "UI",
        "ux": "UX",
        "ci": "CI",
        "cd": "CD",
        "r2": "R2",
        "d1": "D1",
        "hmac": "HMAC",
        "jwt": "JWT",
        "oauth": "OAuth",
        "oauth2": "OAuth2",
        "json": "JSON",
        "yaml": "YAML",
        "xml": "XML",
        "html": "HTML",
        "css": "CSS",
        "js": "JS",
        "ts": "TS",
        "sql": "SQL",
        "nosql": "NoSQL",
        "rest": "REST",
        "graphql": "GraphQL",
        "http": "HTTP",
        "https": "HTTPS",
        "url": "URL",
        "uri": "URI",
        "sdk": "SDK",
        "cli": "CLI",
        "sso": "SSO",
        "mfa": "MFA",
        "2fa": "2FA",
        "cors": "CORS",
        "csp": "CSP",
        "xss": "XSS",
        "csrf": "CSRF",
        "redis": "Redis",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "k8s": "K8s",
        "aws": "AWS",
        "gcp": "GCP",
        "azure": "Azure",
        "vercel": "Vercel",
        "netlify": "Netlify",
        "cloudflare": "Cloudflare",
        "github": "GitHub",
        "gitlab": "GitLab",
        "bitbucket": "Bitbucket",
        "npm": "npm",
        "yarn": "Yarn",
        "pnpm": "pnpm",
        "webpack": "Webpack",
        "vite": "Vite",
        "rollup": "Rollup",
        "babel": "Babel",
        "eslint": "ESLint",
        "prettier": "Prettier",
        "typescript": "TypeScript",
        "javascript": "JavaScript",
        "python": "Python",
        "node": "Node.js",
        "react": "React",
        "vue": "Vue",
        "angular": "Angular",
        "next": "Next.js",
        "nuxt": "Nuxt.js",
        "svelte": "Svelte",
        "tailwind": "Tailwind CSS",
        "bootstrap": "Bootstrap",
        "material": "Material-UI",
        "antd": "Ant Design",
        "prisma": "Prisma",
        "sequelize": "Sequelize",
        "mongoose": "Mongoose",
        "express": "Express",
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "rails": "Rails",
        "laravel": "Laravel",
        "spring": "Spring",
        "dotnet": ".NET",
        "aspnet": "ASP.NET",
        "wordpress": "WordPress",
        "drupal": "Drupal",
        "joomla": "Joomla",
        "shopify": "Shopify",
        "woocommerce": "WooCommerce",
        "stripe": "Stripe",
        "paypal": "PayPal",
        "twilio": "Twilio",
        "sendgrid": "SendGrid",
        "mailchimp": "Mailchimp",
        "slack": "Slack",
        "discord": "Discord",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "zoom": "Zoom",
        "teams": "Microsoft Teams",
        "figma": "Figma",
        "sketch": "Sketch",
        "invision": "InVision",
        "adobe": "Adobe",
        "photoshop": "Photoshop",
        "illustrator": "Illustrator",
        "xd": "Adobe XD",
        "blender": "Blender",
        "unity": "Unity",
        "unreal": "Unreal Engine",
        "godot": "Godot"
    }
    
    # Replace technical terms
    for term, replacement in tech_terms.items():
        # Use word boundaries to avoid partial matches
        # Handle cases where terms might be followed by punctuation
        pattern = r'\b' + re.escape(term) + r'\b'
        title = re.sub(pattern, replacement, title, flags=re.IGNORECASE)
        
        # Also handle cases where terms are followed by common punctuation
        # This makes the function more robust and idempotent
        if term.lower() in title.lower():
            # Double-check we didn't miss any cases due to punctuation
            title = re.sub(
                r'\b' + re.escape(term) + r'([^\w]|$)', 
                replacement + r'\1', 
                title, 
                flags=re.IGNORECASE
            )
    
    return title


def _classify_story_type(title: str, body: str) -> StoryType:
    """Classify the story type based on title and body."""
    text = f"{title} {body}".lower()
    
    # Check security first (more specific)
    if any(word in text for word in ["security", "secure", "auth", "hmac", "token", "authentication"]):
        return StoryType.SECURITY
    elif any(word in text for word in ["feat", "feature", "add", "implement", "new"]):
        return StoryType.FEAT
    elif any(word in text for word in ["fix", "bug", "issue", "resolve"]):
        return StoryType.FIX
    elif any(word in text for word in ["perf", "performance", "optimize", "speed", "fast"]):
        return StoryType.PERF
    elif any(word in text for word in ["infra", "deploy", "ci", "cd", "pipeline", "worker"]):
        return StoryType.INFRA
    elif any(word in text for word in ["docs", "readme", "documentation"]):
        return StoryType.DOCS
    else:
        return StoryType.OTHER


def _extract_why_and_highlights(pr_event: Dict[str, Any]) -> tuple[str, List[str]]:
    """Extract why and highlights from PR event."""
    body = pr_event.get("body", "")
    commit_messages = pr_event.get("details", {}).get("commit_messages", [])
    
    # Extract why from PR body or first commit message
    why = ""
    if body and "why" in body.lower():
        # Look for why in PR body
        lines = body.split("\n")
        for line in lines:
            if "why" in line.lower() and ":" in line:
                why = line.split(":", 1)[1].strip()
                break
    
    if not why and commit_messages:
        # Use first commit message as why
        first_commit = commit_messages[0] if commit_messages else ""
        why = first_commit.split("\n")[0] if first_commit else ""  # First line only
    
    if not why:
        # Try to extract from CodeRabbit summary - look for actual feature descriptions
        if body and "Summary by CodeRabbit" in body:
            lines = body.split("\n")
            in_summary = False
            in_new_features = False
            for line in lines:
                line = line.strip()
                if "Summary by CodeRabbit" in line:
                    in_summary = True
                    continue
                if in_summary and (line.startswith("- New Features") or line.startswith("- New Features")):
                    in_new_features = True
                    continue
                if in_new_features and (line.startswith("  - ") or line.startswith("  - ") or line.startswith("- ") or line.startswith("- ")):
                    # Remove the prefix (could be "  - ", "  - ", "- ", or "- ")
                    if line.startswith("  - ") or line.startswith("  - "):
                        feature = line[4:]
                    else:
                        feature = line[2:]
                    # Only use if it's a real feature description, not a generic header
                    if len(feature) > 10 and not feature.lower() in ["improvements", "documentation", "chores", "tests"]:
                        why = f"Added {feature.lower()}"
                        break
                if in_summary and line.startswith("<!-- end of auto-generated comment"):
                    break
        
        if not why:
            # Generate more specific why based on title
            title = pr_event.get('title', '').lower()
            if 'security' in title:
                why = "Enhanced system security with authentication and validation"
            elif 'deduplication' in title:
                why = "Improved pipeline efficiency by preventing duplicate processing"
            elif 'twitch' in title and 'transcribe' in title:
                why = "Automated content processing from clips to searchable transcripts"
            elif 'cloudflare' in title and 'whisper' in title:
                why = "Integrated AI-powered transcription for audio content"
            elif 'content generation' in title and 'schema' in title:
                why = "Implemented unified content generation schema for better data organization"
            elif 'ai blog generation' in title:
                why = "Added AI-powered blog generation with automated content creation"
            else:
                why = "Delivered new functionality to improve the system"
    
    # Extract highlights from commit messages and PR body
    highlights = []
    
    # First try to get highlights from CodeRabbit summary - but filter out generic headers
    if body and "Summary by CodeRabbit" in body:
        lines = body.split("\n")
        in_summary = False
        in_new_features = False
        for line in lines:
            line = line.strip()
            if "Summary by CodeRabbit" in line:
                in_summary = True
                continue
            if in_summary and (line.startswith("- New Features") or line.startswith("- New Features")):
                in_new_features = True
                continue
            if in_new_features and (line.startswith("  - ") or line.startswith("  - ") or line.startswith("- ") or line.startswith("- ")):
                # Remove the prefix (could be "  - ", "  - ", "- ", or "- ")
                if line.startswith("  - ") or line.startswith("  - "):
                    feature = line[4:]
                else:
                    feature = line[2:]
                # Only include if it's a real feature description, not a generic header
                if len(feature) > 10 and len(feature) < 100 and not feature.lower() in ["improvements", "documentation", "chores", "tests"]:
                    highlights.append(feature)
            if in_summary and line.startswith("<!-- end of auto-generated comment"):
                break
    
    # If no highlights from PR body, use commit messages
    if not highlights and commit_messages:
        for commit in commit_messages[:3]:  # Top 3 commits
            first_line = commit.split("\n")[0]
            if len(first_line) > 10 and len(first_line) < 100:
                highlights.append(first_line)
    
    # If still no highlights, use PR title
    if not highlights:
        title = pr_event.get("title", "").lower()
        if 'security' in title:
            highlights = ["HMAC authentication", "CORS protection", "Rate limiting"]
        elif 'deduplication' in title:
            highlights = ["Duplicate detection", "File cleanup", "Pipeline optimization"]
        elif 'twitch' in title and 'transcribe' in title:
            highlights = ["Audio processing", "Cloud storage", "Background tasks"]
        elif 'cloudflare' in title and 'whisper' in title:
            highlights = ["AI transcription", "Validation", "Automated scheduling"]
        elif 'content generation' in title and 'schema' in title:
            highlights = ["Unified data schema", "Content API", "Job processing"]
        elif 'ai blog generation' in title:
            highlights = ["AI-powered drafting", "Automated metadata", "Idempotent generation"]
        else:
            highlights = ["New feature implementation"]
    
    # Clean up highlights - remove generic headers and improve quality
    filtered_highlights = []
    generic_headers = ["improvements", "documentation", "chores", "tests", "feature/", "fix/", "security/"]
    generic_phrases = [
        "transcripts and github context", 
        "secrets and local dev overrides",
        "new test/run scripts",
        "added runtime deps",
        "db migration for persistent jobs",
        "stronger production guards",
        "updated env examples",
        "secret placeholder",
        "secrets, local dev overrides",
        "migration workflow",
        "failure-tracking docs"
    ]
    
    for h in highlights:
        h_lower = h.lower()
        # Skip if it's a generic header, too short, or contains generic content
        if (len(h) > 5 and 
            not any(header in h_lower for header in generic_headers) and
            not h_lower.startswith("feature/") and
            not h_lower.startswith("fix/") and
            not h_lower.startswith("security/") and
            not any(phrase in h_lower for phrase in generic_phrases)):
            filtered_highlights.append(h)
    
    # If we filtered out everything, provide better defaults
    if not filtered_highlights:
        title = pr_event.get("title", "").lower()
        if 'content generation' in title and 'schema' in title:
            filtered_highlights = ["Content API with background queue", "Daily manifest builder", "Blog generator with AI judging"]
        elif 'ai blog generation' in title:
            filtered_highlights = ["AI-powered blog drafting", "Production blog generation", "Automated metadata and idempotent drafts"]
        else:
            filtered_highlights = ["New feature implementation"]
    
    # Clean up why text - make it more polished
    why = why.replace("Added added", "Added").replace("Completed work on", "Delivered")
    why = why.replace("Delivered Feature/", "Delivered ").replace("Delivered feature/", "Delivered ")
    
    # Ensure why ends with a period
    if why and not why.endswith('.'):
        why = why + '.'
    
    # Filter highlights to be more action-oriented and specific
    final_highlights = []
    for highlight in filtered_highlights:
        # Skip single words or very short phrases
        if len(highlight.split()) < 2:
            continue
        # Skip generic phrases
        if any(generic in highlight.lower() for generic in ["added", "updated", "improved", "enhanced", "fixed"]):
            continue
        final_highlights.append(highlight)
    
    # If we filtered out too much, add some defaults
    if not final_highlights and filtered_highlights:
        final_highlights = filtered_highlights[:2]
    
    return why, final_highlights[:3]  # Max 3 highlights


def pair_with_clip(
    pr_event: Dict[str, Any],
    clips: List[Dict[str, Any]],
    time_window_hours: float = 2.0
) -> PairingInfo:
    """Pair a PR with the best matching clip within time window."""
    # Handle datetime parsing - follow existing pattern from GitHub service
    created_at = pr_event["created_at"]
    if isinstance(created_at, str):
        pr_merged_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    else:
        pr_merged_at = created_at
    
    best_clip = None
    best_score = 0.0
    
    for clip in clips:
        # Handle datetime parsing for clip - follow existing pattern
        clip_created_at_str = clip["created_at"]
        if isinstance(clip_created_at_str, str):
            clip_created_at = datetime.fromisoformat(clip_created_at_str.replace("Z", "+00:00"))
        else:
            clip_created_at = clip_created_at_str
        
        # Check time window (± time_window_hours)
        time_diff = abs((pr_merged_at - clip_created_at).total_seconds() / 3600)
        if time_diff > time_window_hours:
            continue
        
        # Calculate pairing score
        score = _calculate_pairing_score(pr_event, clip, time_diff)
        
        if score > best_score:
            best_score = score
            best_clip = clip
    
    # Return pairing info
    if best_clip and best_score >= 0.55:  # Threshold for good pairing
        # Handle datetime parsing for best clip - follow existing pattern
        best_clip_created_at_str = best_clip["created_at"]
        if isinstance(best_clip_created_at_str, str):
            best_clip_created_at = datetime.fromisoformat(best_clip_created_at_str.replace("Z", "+00:00"))
        else:
            best_clip_created_at = best_clip_created_at_str
        
        return PairingInfo(
            clip_id=best_clip["id"],
            clip_created_at=best_clip_created_at,
            score=best_score,
            needs_broll=False
        )
    else:
        return PairingInfo(needs_broll=True)


def _calculate_pairing_score(pr_event: Dict[str, Any], clip: Dict[str, Any], time_diff: float) -> float:
    """Calculate pairing score between PR and clip (0.0-1.0)."""
    score = 0.0
    
    # Time proximity (closer = better, max 0.4 points)
    time_score = max(0, 1 - (time_diff / 2.0)) * 0.4
    score += time_score
    
    # Keyword overlap (0.6 points)
    pr_text = f"{pr_event.get('title', '')} {pr_event.get('body', '')}".lower()
    clip_text = f"{clip.get('title', '')} {clip.get('transcript', '')}".lower()
    
    # Simple keyword matching
    pr_words = set(pr_text.split())
    clip_words = set(clip_text.split())
    
    if pr_words and clip_words:
        overlap = len(pr_words.intersection(clip_words))
        total = len(pr_words.union(clip_words))
        keyword_score = (overlap / total) * 0.6
        score += keyword_score
    
    return min(1.0, score)
