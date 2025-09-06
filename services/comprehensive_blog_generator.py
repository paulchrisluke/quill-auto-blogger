"""
Comprehensive AI blog generator.
Generates entire blog posts from raw data in a single AI call.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dotenv import load_dotenv

from .ai_client import CloudflareAIClient, AIClientError, TokenLimitExceededError, AIResponseError

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Precompiled regex patterns for low-value commit messages
LOW_VALUE_PATTERNS = [
    re.compile(r'^update\s+', re.IGNORECASE),
    re.compile(r'^fix\s+', re.IGNORECASE),
    re.compile(r'^bump\s+', re.IGNORECASE),
    re.compile(r'^chore\s*:', re.IGNORECASE),
    re.compile(r'^style\s*:', re.IGNORECASE),
    re.compile(r'^refactor\s*:', re.IGNORECASE),
    re.compile(r'^clean\s+', re.IGNORECASE),
    re.compile(r'^remove\s+', re.IGNORECASE),
    re.compile(r'^delete\s+', re.IGNORECASE),
    re.compile(r'^merge\s+', re.IGNORECASE),
    re.compile(r'^resolve\s+', re.IGNORECASE),
    re.compile(r'^update\s+.*\.json', re.IGNORECASE),
    re.compile(r'^update\s+.*\.md', re.IGNORECASE),
    re.compile(r'^update\s+.*\.txt', re.IGNORECASE),
    re.compile(r'^update\s+.*\.yml', re.IGNORECASE),
    re.compile(r'^update\s+.*\.yaml', re.IGNORECASE),
    re.compile(r'^update\s+.*\.lock', re.IGNORECASE)
]


class ComprehensiveBlogGenerator:
    """Generates complete blog posts using comprehensive AI approach."""
    
    def __init__(self):
        self.ai_enabled = os.getenv("AI_COMPREHENSIVE_ENABLED", "true").lower() == "true"
        self.ai_client = None
        logger.info(f"Comprehensive blog generator initializing, AI enabled: {self.ai_enabled}")
        
        try:
            self.voice_prompt = self._load_voice_prompt()
            logger.info(f"Voice prompt loaded, length: {len(self.voice_prompt)}")
        except Exception as e:
            logger.error(f"Failed to load voice prompt: {e}")
            raise
            
        if self.ai_enabled:
            try:
                logger.info("Initializing AI client...")
                self.ai_client = CloudflareAIClient()
                logger.info("Comprehensive blog generator initialized successfully")
            except AIClientError as e:
                logger.warning(f"Failed to initialize AI client during init: {e}. Will retry during generation.")
                self.ai_client = None
    
    def _load_voice_prompt(self) -> str:
        """Load the voice prompt from the configured path."""
        voice_prompt_path = os.getenv("BLOG_VOICE_PROMPT_PATH", "prompts/paul_chris_luke.md")
        
        try:
            if os.path.exists(voice_prompt_path):
                with open(voice_prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    logger.info(f"Loaded voice prompt from {voice_prompt_path}")
                    return content
            else:
                logger.error(f"Voice prompt file not found: {voice_prompt_path}")
                raise FileNotFoundError(f"Voice prompt file not found: {voice_prompt_path}")
        except Exception as e:
            logger.error(f"Failed to load voice prompt: {e}")
            raise
    
    def generate_blog_content(self, date: str, twitch_clips: List[Dict[str, Any]], github_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate complete blog content from raw data using 4-call chunking approach.
        
        Args:
            date: Date in YYYY-MM-DD format
            twitch_clips: List of Twitch clip data
            github_events: List of GitHub event data
            
        Returns:
            Dictionary with title, description, tags, and markdown content
            
        Raises:
            AIClientError: If AI generation fails
        """
        if not self.ai_enabled:
            raise AIClientError("Comprehensive AI generation not available")
        
        # Retry AI client initialization if it failed during init
        if not self.ai_client:
            try:
                logger.info("Retrying AI client initialization...")
                self.ai_client = CloudflareAIClient()
                logger.info("AI client initialized successfully")
            except AIClientError as e:
                logger.error(f"Failed to initialize AI client: {e}")
                raise AIClientError("Comprehensive AI generation not available")
        
        try:
            # Prepare data for AI
            ai_data = self._prepare_ai_data(date, twitch_clips, github_events)
            
            # Create compact tables for token efficiency
            clips_rows = self._compact_clip_rows(ai_data["twitch_clips"])
            prs_rows = self._compact_pr_rows(ai_data["github_events"])
            
            logger.info(f"🚀 Starting 4-call chunking blog generation for {date}")
            logger.info(f"📊 Data Summary: {len(clips_rows)} clips, {len(prs_rows)} PRs")
            
            # 1) Generate outline
            logger.info("📋 Step 1/4: Generating outline...")
            logger.info(f"🔗 Available anchors: {[row['anchor'] for row in prs_rows + clips_rows]}")
            outline = self._generate_outline(date, prs_rows, clips_rows)
            logger.info(f"📋 Generated outline with section plans: {outline.get('section_plan', {})}")
            state = {
                "prev_last_sentence": "",
                "motifs": ["automation paradox", "Clanker", "live-streaming rubber duck", "tech debt", "caffeine-fueled coding"],
                "motifs_used": [],  # Track which motifs have been used
                "used_anchors": set()  # Track used anchors across all sections
            }
            
            blocks = {}
            
            # 2) Hook + Context
            logger.info("📝 Step 2/4: Generating Hook + Context sections...")
            r1 = self._generate_sections_group(date, outline, state, prs_rows, clips_rows,
                                               "hook_ctx", ["Hook","Context"])
            blocks.update(r1["sections"])
            
            # 3) What Shipped + Twitch Clips
            logger.info("📝 Step 3/4: Generating What Shipped + Twitch Clips sections...")
            r2 = self._generate_sections_group(date, outline, state, prs_rows, clips_rows,
                                               "shipped_clips", ["What Shipped","Twitch Clips"])
            blocks.update(r2["sections"])
            
            # 4) Why It Matters + Human Story + Wrap-Up
            logger.info("📝 Step 4/4: Generating Why It Matters + Human Story + Wrap-Up sections...")
            r3 = self._generate_sections_group(date, outline, state, prs_rows, clips_rows,
                                               "why_human_wrap", ["Why It Matters","Human Story","Wrap-Up"])
            blocks.update(r3["sections"])
            
            # 5) Stitch sections together
            logger.info("🔗 Stitching sections together...")
            result = self._stitch_sections(outline, blocks)
            
            # 6) Expansion mini-pass (optional - add 300-400 words to weakest section)
            logger.info("📈 Step 5/5: Expansion mini-pass...")
            weakest_section = self._find_weakest_section(blocks)
            expansion_content = self._expand_weakest_section(date, blocks, weakest_section, prs_rows, clips_rows)
            
            # Insert expansion into the weakest section
            if expansion_content and weakest_section in blocks:
                current_content = blocks[weakest_section]["content"]
                # Insert expansion before the last paragraph
                paragraphs = current_content.split('\n\n')
                if len(paragraphs) > 1:
                    paragraphs.insert(-1, expansion_content)
                    blocks[weakest_section]["content"] = '\n\n'.join(paragraphs)
                    logger.info(f"✅ Added expansion to {weakest_section}")
                else:
                    # If no paragraphs, just append
                    blocks[weakest_section]["content"] = current_content + '\n\n' + expansion_content
                    logger.info(f"✅ Appended expansion to {weakest_section}")
                
                # Re-stitch with expanded content
                result = self._stitch_sections(outline, blocks)
            
            # Enhanced content validation and logging
            content = result.get('content', '')
            word_count = len(content.split()) if content else 0
            char_count = len(content) if content else 0
            
            logger.info(f"✅ Successfully generated chunked blog content for {date}")
            logger.info(f"📊 Content Stats - Words: {word_count:,}, Characters: {char_count:,}")
            logger.info(f"📏 Content Length: {len(content):,} characters")
            
            # Validate content length
            target_words = 2700  # Updated target for enhanced chunked approach
            if word_count < target_words:
                logger.warning(f"⚠️ Content shorter than target: {word_count:,} words (target: {target_words:,})")
            else:
                logger.info(f"🎯 Content length target met: {word_count:,} words")
            
            return result
            
        except TokenLimitExceededError as e:
            logger.error(f"Token limit exceeded for {date}: {e}")
            # Try to reduce prompt size and retry
            return self._handle_token_limit_exceeded(date, twitch_clips, github_events, e)
        except AIClientError as e:
            logger.error(f"AI generation failed for {date}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in comprehensive blog generation: {e}")
            raise AIClientError(f"Comprehensive blog generation failed: {e}")
    
    def _handle_token_limit_exceeded(self, date: str, twitch_clips: List[Dict[str, Any]], github_events: List[Dict[str, Any]], error: TokenLimitExceededError) -> Dict[str, Any]:
        """Handle token limit exceeded by reducing data size and retrying."""
        logger.info(f"Attempting to reduce prompt size for {date} due to token limit")
        
        # Reduce data size by limiting clips and events
        reduced_clips = twitch_clips[:3]  # Limit to 3 clips
        reduced_events = github_events[:10]  # Limit to 10 events
        
        logger.info(f"Reduced data: {len(reduced_clips)} clips, {len(reduced_events)} events")
        
        try:
            # Prepare reduced data for AI
            ai_data = self._prepare_ai_data(date, reduced_clips, reduced_events)
            
            # Generate comprehensive prompt with reduced data
            system_prompt, user_prompt = self._create_comprehensive_prompt(ai_data)
            
            # Use lower max tokens for output
            configured_tokens = max(int(os.getenv("AI_COMPREHENSIVE_MAX_TOKENS", "4000")), 1)
            max_tokens = max(min(configured_tokens, 4096) // 2, 1)  # Reduce by half, ensure at least 1
            
            logger.info(f"Retrying with reduced prompt size - Max tokens: {max_tokens}")
            result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=max_tokens)
            
            # Parse AI response
            parsed_content = self._parse_ai_response(result, date)
            
            logger.info(f"Successfully generated comprehensive blog content for {date} with reduced data")
            return parsed_content
            
        except TokenLimitExceededError:
            logger.error(f"Still exceeding token limits after reduction for {date}")
            # Return a minimal fallback response
            return {
                "title": f"Daily Digest - {date}",
                "description": f"Daily digest for {date} with limited content due to size constraints.",
                "tags": ["daily-digest", "limited-content"],
                "content": f"# Daily Digest - {date}\n\nContent generation was limited due to input size constraints. Please check individual clips and events for full details."
            }
        except Exception as e:
            logger.error(f"Failed to generate reduced content for {date}: {e}")
            raise AIClientError(f"Failed to generate content even with reduced data: {e}")
    
    def _prepare_ai_data(self, date: str, twitch_clips: List[Dict[str, Any]], github_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepare data for AI consumption - only clips with transcripts and events with good commit messages."""
        
        # Filter for clips with transcripts only
        clips_with_transcripts = [clip for clip in twitch_clips if clip.get('transcript')]
        logger.info(f"Filtered clips: {len(twitch_clips)} total -> {len(clips_with_transcripts)} with transcripts")
        
        # Filter for merged PR events only
        merged_events = self._filter_merged_events(github_events)
        logger.info(f"Filtered events: {len(github_events)} total -> {len(merged_events)} merged PRs")
        
        # Count commit messages for logging
        total_commit_messages = sum(len(event.get('details', {}).get('commit_messages', [])) for event in merged_events)
        logger.info(f"📝 Total commit messages available: {total_commit_messages}")
        
        # Sort clips by view count (descending) and take top ones
        max_clips = int(os.getenv("AI_MAX_CLIPS", "5"))  # Increased since we're filtering
        sorted_clips = sorted(clips_with_transcripts, key=lambda x: x.get('view_count', 0), reverse=True)
        limited_clips = sorted_clips[:max_clips]
        
        # Sort events by importance and take top ones
        max_events = int(os.getenv("AI_MAX_EVENTS", "15"))  # Increased since we're filtering
        def event_priority(event):
            if event.get('type') == 'PullRequestEvent':
                return 0
            elif event.get('type') == 'PushEvent':
                return 1
            else:
                return 2
        
        sorted_events = sorted(merged_events, key=lambda x: (event_priority(x), x.get('created_at', '')), reverse=True)
        limited_events = sorted_events[:max_events]
        
        # Enrich the data with additional context
        enriched_clips = self._enrich_clip_data(limited_clips)
        enriched_events = self._enrich_event_data(limited_events)
        
        logger.info(f"Final data size: {len(enriched_clips)} clips with transcripts, {len(enriched_events)} merged PRs")
        
        return {
            "date": date,
            "voice_prompt": self.voice_prompt,
            "twitch_clips": enriched_clips,
            "github_events": enriched_events,
            "summary": self._create_data_summary(enriched_clips, enriched_events)
        }
    
    def _filter_merged_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter GitHub events to include merged PullRequestEvents, PushEvents, and other relevant events."""
        merged_events = []
        
        for event in events:
            if event.get('type') == 'PullRequestEvent':
                # Check if the PR was merged
                details = event.get('details', {})
                if details.get('merged', False):
                    merged_events.append(event)
                    logger.info(f"Including merged PR: {details.get('title', 'No title')} (PR #{details.get('number', 'No number')})")
            elif event.get('type') == 'PushEvent':
                # Include PushEvents (they represent actual work done)
                merged_events.append(event)
                details = event.get('details', {})
                branch = details.get('branch', 'unknown branch')
                commits = details.get('commits', 0)
                logger.info(f"Including PushEvent: {commits} commits to {branch}")
            elif event.get('type') in ['IssueCommentEvent', 'PullRequestReviewCommentEvent', 'PullRequestReviewEvent']:
                # Include these event types as they represent meaningful activity
                merged_events.append(event)
                logger.info(f"Including {event.get('type')}: {event.get('id', 'No ID')}")
        
        return merged_events
    
    
    def _enrich_clip_data(self, clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich clip data with additional context for better AI generation."""
        enriched = []
        for clip in clips:
            enriched_clip = clip.copy()
            
            # Add contextual information
            enriched_clip["context"] = {
                "view_count_category": "high" if clip.get('view_count', 0) > 10 else "low",
                "duration_category": "short" if clip.get('duration', 0) < 30 else "medium" if clip.get('duration', 0) < 90 else "long",
                "has_transcript": bool(clip.get('transcript')),
                "title_sentiment": self._analyze_title_sentiment(clip.get('title', ''))
            }
            
            # Add formatted display info
            enriched_clip["display_info"] = {
                "formatted_duration": f"{int(clip.get('duration', 0))}s",
                "view_count_text": f"{clip.get('view_count', 0)} views",
                "transcript_preview": clip.get('transcript', '')[:100] + "..." if clip.get('transcript') else "No transcript available"
            }
            
            enriched.append(enriched_clip)
        
        return enriched
    
    def _enrich_event_data(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich event data with additional context for better AI generation."""
        enriched = []
        for event in events:
            enriched_event = event.copy()
            
            # Truncate long text fields to reduce token usage
            self._truncate_event_text(enriched_event)
            
            # Add contextual information
            enriched_event["context"] = {
                "event_type_category": "code_change" if event.get('type') in ['PullRequestEvent', 'PushEvent'] else "other",
                "has_detailed_body": bool(event.get('body') and len(event.get('body', '')) > 50),
                "is_merged_pr": event.get('details', {}).get('merged', False),
                "pr_number": event.get('details', {}).get('number'),
                "action_type": event.get('details', {}).get('action', 'unknown')
            }
            
            # Add formatted display info
            enriched_event["display_info"] = {
                "formatted_type": event.get('type', 'UnknownEvent').replace('Event', ''),
                "pr_display": f"PR #{event.get('details', {}).get('number')}" if event.get('details', {}).get('number') else "No PR number",
                "action_display": event.get('details', {}).get('action', 'unknown').title(),
                "body_preview": event.get('body', '')[:150] + "..." if event.get('body') else "No description available"
            }
            
            # For merged PRs, add summarized commit messages
            if event.get('type') == 'PullRequestEvent' and event.get('details', {}).get('merged', False):
                commit_summary = self._summarize_commit_messages(event)
                enriched_event["commit_summary"] = commit_summary
            
            enriched.append(enriched_event)
        
        return enriched
    
    def _truncate_event_text(self, event: Dict[str, Any]) -> None:
        """Clean and truncate event data to focus on merges and commit messages."""
        # Clean up the event to focus on what matters
        details = event.get('details', {})
        if details:
            # For merged PRs, keep only essential info
            if event.get('type') == 'PullRequestEvent' and details.get('merged', False):
                # Keep PR title, number, and commit messages
                pr = details.get('pull_request', {})
                if pr:
                    # Truncate PR body to just the essential summary
                    if pr.get('body') and len(pr['body']) > 300:
                        pr['body'] = pr['body'][:300] + "... [truncated]"
                
                # Clean up commit messages - remove noise and keep meaningful ones
                commit_messages = details.get('commit_messages', [])
                if commit_messages:
                    cleaned_messages = []
                    for msg in commit_messages:
                        # Skip merge commits and other noise
                        if not any(skip in msg.lower() for skip in ['merge', 'revert', 'fix lint', 'update readme']):
                            if len(msg) > 150:
                                cleaned_messages.append(msg[:150] + "...")
                            else:
                                cleaned_messages.append(msg)
                    details['commit_messages'] = cleaned_messages[:5]  # Limit to 5 most relevant commits
            
            # For push events, clean up commit messages
            elif event.get('type') == 'PushEvent':
                commit_messages = details.get('commit_messages', [])
                if commit_messages:
                    cleaned_messages = []
                    for msg in commit_messages:
                        if not any(skip in msg.lower() for skip in ['merge', 'revert', 'fix lint']):
                            if len(msg) > 150:
                                cleaned_messages.append(msg[:150] + "...")
                            else:
                                cleaned_messages.append(msg)
                    details['commit_messages'] = cleaned_messages[:5]
    
    def _summarize_commit_messages(self, pr_event: Dict[str, Any]) -> str:
        """Summarize the commit messages for a merged PR to provide better context."""
        details = pr_event.get('details', {})
        commit_messages = details.get('commit_messages', [])
        
        if not commit_messages:
            return "No commit messages available"
        
        # Filter out low-value commit messages and summarize the meaningful ones
        meaningful_commits = []
        for message in commit_messages:
            if self._is_meaningful_commit_message(message):
                meaningful_commits.append(message)
        
        if not meaningful_commits:
            return "Routine updates and maintenance"
        
        # If we have 1-2 meaningful commits, list them
        if len(meaningful_commits) <= 2:
            return " | ".join(meaningful_commits)
        
        # If we have more, summarize the key themes
        themes = self._extract_commit_themes(meaningful_commits)
        return f"Key changes: {', '.join(themes)}"
    
    def _is_meaningful_commit_message(self, message: str) -> bool:
        """Check if a commit message is meaningful (not just 'Update', 'Fix', etc.)."""
        if not message or len(message.strip()) < 10:
            return False
        
        message_lower = message.lower().strip()
        
        # Check against precompiled low-value patterns
        for pattern in LOW_VALUE_PATTERNS:
            if pattern.match(message_lower):
                return False
        
        return True
    
    def _extract_commit_themes(self, commit_messages: List[str]) -> List[str]:
        """Extract key themes from commit messages."""
        themes = []
        
        # Look for common patterns and extract themes
        for message in commit_messages:
            message_lower = message.lower()
            
            if any(word in message_lower for word in ['feature', 'add', 'implement', 'create']):
                themes.append("new features")
            elif any(word in message_lower for word in ['fix', 'bug', 'error', 'issue']):
                themes.append("bug fixes")
            elif any(word in message_lower for word in ['improve', 'enhance', 'optimize', 'better']):
                themes.append("improvements")
            elif any(word in message_lower for word in ['security', 'auth', 'permission', 'access']):
                themes.append("security updates")
            elif any(word in message_lower for word in ['ui', 'design', 'style', 'layout']):
                themes.append("UI/UX changes")
            elif any(word in message_lower for word in ['api', 'endpoint', 'service', 'integration']):
                themes.append("API changes")
            elif any(word in message_lower for word in ['test', 'spec', 'coverage']):
                themes.append("testing")
            elif any(word in message_lower for word in ['doc', 'readme', 'comment', 'explain']):
                themes.append("documentation")
        
        # Remove duplicates and limit to top 3
        unique_themes = list(dict.fromkeys(themes))[:3]
        
        if not unique_themes:
            return ["code changes"]
        
        return unique_themes
    
    def _analyze_title_sentiment(self, title: str) -> str:
        """Simple sentiment analysis of clip titles."""
        if not title:
            return "neutral"
        
        title_lower = title.lower()
        if any(word in title_lower for word in ['lol', 'funny', 'haha', 'banger', 'epic']):
            return "positive"
        elif any(word in title_lower for word in ['fail', 'broken', 'error', 'bug']):
            return "negative"
        else:
            return "neutral"
    
    def _create_data_summary(self, clips: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a summary of the data for AI context."""
        pr_events = [e for e in events if e.get('type') == 'PullRequestEvent']
        push_events = [e for e in events if e.get('type') == 'PushEvent']
        merged_prs = [e for e in pr_events if e.get('context', {}).get('is_merged_pr')]
        
        high_view_clips = [c for c in clips if c.get('context', {}).get('view_count_category') == 'high']
        clips_with_transcripts = [c for c in clips if c.get('context', {}).get('has_transcript')]
        
        return {
            "total_clips": len(clips),
            "total_events": len(events),
            "merged_prs": len(merged_prs),
            "push_events": len(push_events),
            "high_view_clips": len(high_view_clips),
            "clips_with_transcripts": len(clips_with_transcripts),
            "key_achievements": [e.get('title', '') for e in merged_prs[:3]] + [e.get('details', {}).get('commit_messages', [''])[0] for e in push_events[:3] if e.get('details', {}).get('commit_messages')],  # Top 3 merged PRs + PushEvent commit messages
            "notable_clips": [c.get('title', '') for c in high_view_clips[:3]]  # Top 3 clips by views
        }
    
    def _create_comprehensive_prompt(self, ai_data: Dict[str, Any]) -> tuple[str, str]:
        """Create comprehensive system and user prompts."""
        
        system_prompt = f"""You are Paul Chris Luke, a developer who live-streams his coding sessions and writes engaging technical blog posts. Your voice is witty, self-aware, technically accurate but accessible, and you're not afraid to be meta about the development process.

Your job is to generate the NARRATIVE STRUCTURE and PERSONALITY of the blog post. Python will handle adding specific links, data, and formatting later.

CRITICAL REQUIREMENTS:
1. Write in first person as Paul Chris Luke with AUTHENTIC PERSONALITY
2. Create a compelling narrative that weaves together the day's activities
3. Use SPECIFIC details from the data - actual PR numbers, clip titles, view counts, transcripts
4. Focus on STORY and PERSONALITY, not technical formatting
5. Include proper markdown structure with clear headings
6. Make it engaging, technical, and humorous with meta-commentary
7. Reference actual events with rich context and personality
8. Include the human story behind the technical work

NARRATIVE STRUCTURE (Follow This Pattern - BE EXTENSIVE AND DETAILED):
- **Hook**: Start with a compelling, personality-driven opening using the ACTUAL DATE from the data
- **Context**: Set the scene with the day's activities and the absurdity of the situation (2-3 paragraphs)
- **What Shipped**: Detailed sections for each major PR with rich context and personality (1-2 paragraphs per PR)
- **Twitch Clips**: Bring the clips to life with personality and humor (2-3 paragraphs)
- **Why It Matters**: Meta-commentary on automation, paradoxes, and the human condition (2-3 paragraphs)
- **Human Story**: The deeper narrative about development, automation, and identity (2-3 paragraphs)
- **Wrap-Up**: Witty, memorable closer that ties everything together (1-2 paragraphs)

LENGTH REQUIREMENTS (CRITICAL):
- Target 3000-5000 words total
- Each section should be substantial and detailed (2-4 paragraphs each)
- Include specific examples, quotes, and anecdotes
- Expand on the human story and meta-commentary extensively
- Make it feel like a comprehensive, engaging read
- Don't rush through any section - give each one proper depth and development
- Use the full narrative structure with rich detail in every section

PERSONALITY REQUIREMENTS (CRITICAL):
- Start with a compelling, personality-driven hook
- Include self-aware humor and meta-commentary about the absurdity of building automation tools
- Use ironic observations about the development process
- Add existential musings about AI, automation, and the human condition
- End with a witty, memorable closer
- NEVER use generic corporate language
- ALWAYS inject personality, humor, and authentic voice into every paragraph
- Write like you're telling a story to a friend, not writing a corporate blog

Return your response in the following JSON format:
{{
    "title": "SEO-optimized title that captures the day's essence (be specific and engaging)",
    "description": "SEO description for meta tags (150-160 characters)",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "content": "Complete blog post in markdown format with rich narrative and personality. All newlines must be escaped as \\n for valid JSON."
}}

Voice Guidelines:
{ai_data['voice_prompt']}"""

        # Create a more structured user prompt with better context
        summary = ai_data.get('summary', {})
        clips = ai_data.get('twitch_clips', [])
        events = ai_data.get('github_events', [])
        
        # Safe JSON serialization function to handle datetime and other non-serializable objects
        def safe_json_serializer(obj):
            """Convert non-serializable objects to safe representations."""
            if hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            elif hasattr(obj, '__dict__'):  # custom objects
                return str(obj)
            else:
                return str(obj)
        
        def safe_json_dumps(data, indent=2):
            """Safely serialize data to JSON with fallback handling."""
            try:
                return json.dumps(data, indent=indent, ensure_ascii=False, default=safe_json_serializer)
            except Exception as e:
                # Fallback to string representation if JSON serialization fails
                return f"<Serialization Error: {str(e)}>\nData: {repr(data)}"
        
        user_prompt = f"""Generate a blog post for {ai_data.get('date')} based on this data:

DAY SUMMARY:
- {summary.get('merged_prs', 0)} merged PRs, {summary.get('push_events', 0)} push events
- {summary.get('total_clips', 0)} Twitch clips, {summary.get('high_view_clips', 0)} with high views
- Key achievements: {', '.join(summary.get('key_achievements', [])[:3])}
- Notable clips: {', '.join(summary.get('notable_clips', [])[:3])}

DETAILED TWITCH CLIPS:
{safe_json_dumps(clips)}

DETAILED GITHUB EVENTS:
{safe_json_dumps(events)}

COMMIT MESSAGE DETAILS:
Use the detailed commit messages from the GitHub events to add technical depth and context. Each commit message contains specific technical details about what was changed and why. Extract the technical specifics, problem statements, and solutions from these commit messages to create rich, detailed content.

STORY CONTEXT:
This is a day in the life of Paul Chris Luke, a developer who live-streams his coding sessions and builds AI automation tools. The irony is that he's building tools that might eventually replace parts of his own job, all while live-streaming the process and explaining the absurdity of it to his audience.

Focus on the actual technical work and the human story behind it. Use the commit messages to understand the technical challenges and solutions that were implemented.

WRITING INSTRUCTIONS:
Create a compelling, EXTENSIVE narrative that weaves together the technical work with the human story behind it. Focus on STORY and PERSONALITY, not technical formatting. Use the SPECIFIC details provided - actual PR numbers, clip titles, view counts, transcripts, and event details. Make it engaging and authentic to Paul's voice. Include the meta-commentary about building automation tools while live-streaming the process.

Follow the narrative structure: Hook → Context → What Shipped → Twitch Clips → Why It Matters → Human Story → Wrap-Up

NARRATIVE WRITING STYLE (CRITICAL):
- Write in LONG-FORM PARAGRAPHS, not bullet points or lists
- Each PR should be wrapped in a story paragraph explaining WHY it mattered
- Include 200+ words per section with natural keyword variation for SEO
- Use smooth transitions between sections - connect Twitch clips to PRs, PRs to automation themes
- Tell the story of WHY each change mattered to workflow, streaming, or automation
- Include "color commentary" and audience reactions for unique long-tail content
- Avoid documentation-style writing - this is storytelling, not changelog

EXAMPLE OF GOOD PR WRITING (EXPANDED):
Instead of: "The first PR was a feature/clip recap pipeline analysis, which included daily recap posts generated as standard Markdown files, pull requests targeting the staging branch by default, and updated notification wording for the bot channel."

Do this: "The first major milestone of the day was a significant refactor that transformed how data gets processed inside my system. Up until now, handling this workflow was messy — duplicates, inconsistent formatting, and a lot of manual cleanup. With this change, I introduced caching and deduplication that make ingestion far more efficient. On top of that, the pipeline now generates structured updates automatically, creating organized content I can share with my community. Even the notifications were polished with clearer wording, making the workflow more transparent for both me and my viewers. In short, this wasn't just about technical optimization; it was about building a smoother bridge between live-streaming content and developer storytelling. But the real story here isn't just about the technical implementation — it's about the human side of automation. As I was building these tools, I couldn't help but think about the irony of it all. Here I am, live-streaming my coding sessions, building tools that might eventually replace parts of my own job, all while explaining the absurdity of it to my audience. It's a delicate balance between showcasing technical prowess and acknowledging the existential questions that come with creating tools that might eventually make me obsolete. The community feedback I received during this process was invaluable — viewers commented on the clarity of my explanations, the quality of my code, and the humor I brought to the process. It was a reminder that, even in the midst of building automation tools, there is still a human element that makes the work worth doing."

SEO AND DEPTH REQUIREMENTS:
- Target 200+ words per major section
- Use natural keyword variation throughout
- Include specific technical details but wrapped in narrative
- Create unique long-tail content through personality and meta-commentary
- Make each section feel like a mini-story within the larger narrative

KEYWORD INTEGRATION (CRITICAL):
- Weave keywords naturally into the narrative flow
- Instead of "I merged four pull requests", use "On GitHub, I merged four pull requests that pushed forward my automation workflow — from AI-powered code generation to API documentation improvements"
- Include relevant keywords: GitHub, automation, AI, Twitch, live-streaming, developer, coding, workflow, API, documentation
- Make keyword usage feel natural and conversational, not forced

TWITCH SECTION ENHANCEMENT:
- Write a short paragraph for each clip with context + humor + relevance
- Example: "The clip titled 'jams going hard in the paint' isn't about shipping features — it's about the vibe that keeps me going. Mid-debugging session, I let the music take over, which perfectly illustrates how coding is equal parts focus and chaos. These moments help my Twitch audience connect with me as more than just a developer."
- Include audience reactions, chat comments, or community feedback
- Connect clips to the broader narrative and automation themes
- For each clip, explain the context, what happened, why it matters, and how it connects to the day's work

TRANSITION IMPROVEMENTS:
- Create smooth handoffs between sections
- Example: "But development doesn't happen in isolation. While the code merged quietly in the background, Twitch captured the human side of the work — the jams, the commentary, and the irony of building automation tools while live-streaming the process."
- Use transitional phrases that connect themes across sections
- Make the flow feel like a continuous story, not separate sections

HUMAN STORY EXPANSION:
- Include tension between efficiency vs. creativity
- Explore the absurdity of "building tools that build tools"
- Add reflection on community feedback (viewer comments, PR reception)
- Include personal insights about the development process
- Connect to broader themes about automation and human creativity

LENGTH AND DETAIL REQUIREMENTS (CRITICAL):
- Target 2500-3500 words total (you have 4096 tokens available - use them!)
- Each section should be substantial and detailed (4-6 paragraphs each)
- Include specific examples, quotes, and anecdotes from commit messages
- Expand on the human story and meta-commentary extensively
- Make it feel like a comprehensive, engaging read
- Don't rush through sections - give each one proper depth and development
- Use the full narrative structure with rich detail in every section
- Leverage the detailed commit messages for technical depth and context
- WRITE EXTENSIVELY - this should be a substantial, detailed blog post
- Use all available tokens - don't be concise, be comprehensive

IMPORTANT: 
- Start with a personality-driven hook using the actual date and events from the data
- Include self-aware humor and meta-commentary throughout
- End with a witty, memorable closer
- Avoid generic corporate language
- Write like you're telling a story to a friend
- Focus on the narrative flow and personality, not technical formatting
- NO BULLET POINTS OR LISTS - use flowing paragraphs instead
- BE EXTENSIVE - this should be a substantial, detailed blog post

CRITICAL LENGTH REQUIREMENT:
- You have 4096 tokens available for output - USE ALL OF THEM
- This should be a comprehensive, detailed blog post of 2500+ words
- Don't be concise - be thorough and detailed
- Expand on every section with rich detail and storytelling
- Include extensive meta-commentary and personal reflections
- Use the full narrative structure with substantial depth in every section
- CONTINUE WRITING until you reach the token limit - don't stop early
- Add more detail, more examples, more personal reflections
- Make this the most comprehensive blog post possible

CRITICAL JSON FORMATTING REQUIREMENTS:
- All newlines in the content field must be escaped as \\n
- All quotes in the content must be escaped as \\"
- The response must be valid JSON that can be parsed
- Do not include any text outside the JSON object

Return only the JSON response as specified in the system prompt.

IMPORTANT: Use ALL available tokens (4096) to create the most comprehensive, detailed blog post possible. Don't stop early - continue writing until you've exhausted the token limit with rich, detailed content."""

        return system_prompt, user_prompt
    
    def _parse_ai_response(self, ai_response: Union[Dict[str, Any], str], date: str = None) -> Dict[str, Any]:
        """Parse AI response into structured format."""
        try:
            # Handle dict response (from JSON schema)
            if isinstance(ai_response, dict):
                logger.info("Received structured JSON response from AI")
                return ai_response
            
            # Handle string response (legacy format)
            if isinstance(ai_response, str):
                # Clean up the response (remove any markdown formatting if present)
                cleaned_response = ai_response.strip()
            else:
                raise ValueError(f"Unexpected response type: {type(ai_response)}")
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            # Parse JSON with proper error handling and recovery
            parsed = None
            parse_attempts = [
                # First attempt: parse as-is
                cleaned_response,
                # Second attempt: try to fix common JSON issues
                self._fix_common_json_issues(cleaned_response),
                # Third attempt: extract JSON from markdown code blocks
                self._extract_json_from_markdown(cleaned_response)
            ]
            
            for attempt, response_text in enumerate(parse_attempts, 1):
                try:
                    parsed = json.loads(response_text)
                    logger.info(f"Successfully parsed JSON on attempt {attempt}")
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse attempt {attempt} failed: {e}")
                    if attempt < len(parse_attempts) - 1:
                        # Apply 70B model specific fixes
                        response_text = self._fix_70b_model_json_issues(response_text)
                    if attempt == len(parse_attempts) - 1:
                        # All attempts failed, raise the last error
                        raise e
            
            # Validate required fields
            required_fields = ['title', 'description', 'tags', 'content']
            for field in required_fields:
                if field not in parsed:
                    raise ValueError(f"Missing required field: {field}")
            
            # Map 'content' to 'markdown_body' for consistency
            if 'content' in parsed and 'markdown_body' not in parsed:
                parsed['markdown_body'] = parsed['content']
            
            # Add date field for compatibility with ContentGenerator
            if date:
                parsed['date'] = date
            
            # Validate content
            if not parsed['title'] or len(parsed['title']) < 10:
                raise ValueError("Title too short or empty")
            
            if not parsed['description'] or len(parsed['description']) < 50:
                raise ValueError("Description too short or empty")
            
            if not parsed['content'] or len(parsed['content']) < 100:
                raise ValueError("Content too short or empty")
            
            if not isinstance(parsed['tags'], list) or len(parsed['tags']) == 0:
                raise ValueError("Tags must be a non-empty list")
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            # Sanitize AI response for logging to avoid leaking model output
            sanitized_response = self._sanitize_ai_response_for_logging(ai_response)
            logger.error(f"AI Response (sanitized): {sanitized_response}")
            
            # Try to extract content using regex as fallback
            try:
                logger.info("Attempting to extract content using regex fallback...")
                import re
                
                # Extract title
                title_match = re.search(r'"title":\s*"([^"]*)"', ai_response)
                title = title_match.group(1) if title_match else "Generated Blog Post"
                
                # Extract description
                desc_match = re.search(r'"description":\s*"([^"]*)"', ai_response)
                description = desc_match.group(1) if desc_match else "A blog post generated by AI"
                
                # Extract tags
                tags_match = re.search(r'"tags":\s*\[(.*?)\]', ai_response, re.DOTALL)
                tags = []
                if tags_match:
                    tag_text = tags_match.group(1)
                    tag_matches = re.findall(r'"([^"]*)"', tag_text)
                    tags = tag_matches
                
                # Extract content - handle multiline content properly
                # First try to find content between quotes, handling escaped quotes
                content_match = re.search(r'"content":\s*"((?:[^"\\]|\\.)*)"', ai_response, re.DOTALL)
                if not content_match:
                    # Try to find content between quotes and the next field
                    content_match = re.search(r'"content":\s*"([^"]*(?:"[^"]*"[^"]*)*)"', ai_response, re.DOTALL)
                if not content_match:
                    # Last resort: find content between quotes and closing brace
                    content_match = re.search(r'"content":\s*"([^"]*)"\s*}', ai_response, re.DOTALL)
                
                content = content_match.group(1) if content_match else "Content could not be extracted"
                
                # Clean up the content
                content = content.replace('\\"', '"').replace('\\n', '\n')
                
                logger.info("Successfully extracted content using regex fallback")
                return {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "content": content,
                    "markdown_body": content
                }
                
            except Exception as fallback_error:
                logger.error(f"Regex fallback also failed: {fallback_error}")
                raise AIResponseError(f"Invalid JSON response from AI: {e}")
                
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            # Sanitize AI response for logging to avoid leaking model output
            sanitized_response = self._sanitize_ai_response_for_logging(ai_response)
            logger.error(f"AI Response (sanitized): {sanitized_response}")
            raise AIResponseError(f"Failed to parse AI response: {e}")
    
    def _fix_common_json_issues(self, json_text: str) -> str:
        """Fix common JSON issues without corrupting valid content."""
        import re
        
        # Fix unescaped newlines in string values (but preserve escaped ones)
        # This is safer than the previous approach as it only targets actual newlines
        def fix_newlines_in_strings(match):
            # Only replace actual newlines, not escaped ones
            content = match.group(1)
            # Replace actual newlines and control characters with escaped versions
            fixed = content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            # Fix other control characters
            import re
            fixed = re.sub(r'[\x00-\x1f\x7f-\x9f]', lambda m: f'\\u{ord(m.group(0)):04x}', fixed)
            return f'"{fixed}"'
        
        # Remove markdown/code-fence wrappers if present
        json_text = json_text.strip()
        if json_text.startswith('```json'):
            json_text = json_text[7:]  # Remove ```json
        elif json_text.startswith('```'):
            json_text = json_text[3:]   # Remove ```
        if json_text.endswith('```'):
            json_text = json_text[:-3]  # Remove trailing ```
        json_text = json_text.strip()
        
        return json_text
    
    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON from markdown code blocks or other formatting."""
        import re
        
        # Try to find JSON within markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Try to find JSON object boundaries
        start_brace = text.find('{')
        if start_brace != -1:
            # Find the matching closing brace
            brace_count = 0
            for i, char in enumerate(text[start_brace:], start_brace):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return text[start_brace:i+1]
        
        return text

    def _compact_clip_rows(self, clips):
        """Create compact clip rows for token efficiency with anchor tokens."""
        out = []
        for c in clips:
            clip_id = c.get("id") or c.get("slug") or c.get("url", "")[-8:]
            transcript = c.get("transcript") or ""
            
            # Extract a compelling quote from transcript
            quote = ""
            if transcript:
                # Find a sentence that's not too short or too long
                sentences = [s.strip() for s in transcript.split('.') if 20 < len(s.strip()) < 120]
                if sentences:
                    quote = sentences[0] + "."
            
            out.append({
                "anchor": f"[CLIP:{clip_id}]",
                "id": clip_id,
                "title": (c.get("title") or "")[:120],
                "views": int(c.get("view_count", 0)),
                "duration_s": int(c.get("duration", 0)),
                "quote": quote[:200],  # Key quote for narrative use
                "excerpt": transcript.replace("\n"," ")[:280]
            })
        return out

    def _compact_pr_rows(self, events):
        """Create compact PR rows for token efficiency with anchor tokens."""
        rows = []
        for e in events:
            # Handle multiple GitHub event types
            if e.get("type") not in ["PullRequestEvent", "PushEvent", "IssueCommentEvent", "PullRequestReviewCommentEvent", "PullRequestReviewEvent"]: 
                continue
            
            d = e.get("details", {}) or {}
            
            # For PullRequestEvent, check if merged
            if e.get("type") == "PullRequestEvent" and not d.get("merged", False):
                continue
            
            # Handle different event types
            if e.get("type") == "PushEvent":
                event_id = e.get("id", "unknown")
                commit_summary = "\n".join(d.get("commit_messages", []))
                branch = d.get("branch", "main")
                title = f"Push to {branch}"
                
                # Extract numbers and technical details for richer content
                body_text = (e.get("body") or "") + " " + commit_summary
                numbers = re.findall(r'\b\d{1,5}\b', body_text)[:5]  # Extract numbers
                files_hint = ", ".join(d.get("files", [])[:5])[:160] if d.get("files") else ""
                
                # Create GitHub URL for PushEvent using commit SHA
                commit_sha = d.get('commit_sha')
                if commit_sha:
                    github_url = f"https://github.com/{e.get('repo', 'paulchrisluke/pcl-labs')}/commit/{commit_sha}"
                else:
                    # Fallback to event page if commit SHA is not available
                    github_url = f"https://github.com/{e.get('repo', 'paulchrisluke/pcl-labs')}/events/{event_id}"
            elif e.get("type") == "PullRequestEvent":
                # PullRequestEvent
                event_id = d.get("number")
                commit_summary = e.get("commit_summary", "")
                title = d.get("title", "")
                
                # Create GitHub URL for PullRequestEvent
                github_url = f"https://github.com/{e.get('repo', 'paulchrisluke/pcl-labs')}/pull/{event_id}"
            else:
                # Handle IssueCommentEvent, PullRequestReviewCommentEvent, PullRequestReviewEvent
                event_id = e.get("id", "unknown")
                title = d.get("title", "") or f"{e.get('type', 'Event')} in {e.get('repo', '')}"
                commit_summary = ""
                body_text = (e.get("body") or "") + " " + (d.get("body", "") or "")
                
                # Create GitHub URL for other event types
                # Try to get the issue/PR number from the details
                issue_number = d.get("issue", {}).get("number") if d.get("issue") else None
                pr_number = d.get("pull_request", {}).get("number") if d.get("pull_request") else None
                
                if issue_number:
                    github_url = f"https://github.com/{e.get('repo', 'paulchrisluke/pcl-labs')}/issues/{issue_number}"
                elif pr_number:
                    github_url = f"https://github.com/{e.get('repo', 'paulchrisluke/pcl-labs')}/pull/{pr_number}"
                else:
                    # Fallback to event URL
                    github_url = f"https://github.com/{e.get('repo', 'paulchrisluke/pcl-labs')}/events/{event_id}"
                numbers = re.findall(r'\b\d{1,5}\b', body_text)[:5]  # Extract numbers
                files_hint = ""
            
            # Extract key commit message for narrative use
            key_commit = ""
            if commit_summary:
                # Find the most interesting commit message
                commits = [c.strip() for c in commit_summary.split('\n') if c.strip()]
                if commits:
                    # Prefer commits that aren't just "update" or "fix"
                    interesting_commits = [c for c in commits if not any(c.lower().startswith(prefix) for prefix in ['update', 'fix', 'bump', 'chore'])]
                    key_commit = interesting_commits[0] if interesting_commits else commits[0]
                    key_commit = key_commit[:150]  # Truncate if too long
            
            row_data = {
                "anchor": f"[EVENT:{event_id}]",
                "id": e.get("id"),
                "number": event_id,
                "title": (title[:140]),
                "body_excerpt": ((e.get("body") or "").replace("\n"," ")[:300]),
                "commit_summary": commit_summary[:200],
                "key_commit": key_commit,  # Most interesting commit for narrative
                "type": e.get("type"),
                "branch": d.get("branch", ""),
                "github_url": github_url  # Add GitHub URL for proper linking
            }
            
            # Add rich details for PushEvents and other event types
            if e.get("type") in ["PushEvent", "IssueCommentEvent", "PullRequestReviewCommentEvent", "PullRequestReviewEvent"]:
                row_data.update({
                    "numbers": numbers,
                    "files_hint": files_hint,
                    "config_values": self._extract_config_values(body_text),
                    "error_strings": self._extract_error_strings(body_text)
                })
            
            rows.append(row_data)
        return rows

    def _extract_config_values(self, text: str) -> List[str]:
        """Extract configuration values from text."""
        config_patterns = [
            r'(\d+)s\s*timeout',
            r'(\d+)MB\s*memory',
            r'(\d+)\s*clips?',
            r'(\d+)\s*files?',
            r'(\d+)\s*commits?',
            r'rate\s*limit[:\s]*(\d+)',
            r'timeout[:\s]*(\d+)',
            r'memory[:\s]*(\d+)'
        ]
        values = []
        for pattern in config_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            values.extend(matches)
        return values[:3]  # Limit to 3 most relevant

    def _extract_error_strings(self, text: str) -> List[str]:
        """Extract error-related strings from text."""
        error_patterns = [
            r'error[:\s]*([^.\n]{10,50})',
            r'failed[:\s]*([^.\n]{10,50})',
            r'timeout[:\s]*([^.\n]{10,50})',
            r'crash[:\s]*([^.\n]{10,50})'
        ]
        errors = []
        for pattern in error_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            errors.extend(matches)
        return errors[:2]  # Limit to 2 most relevant

    def _extract_result_json(self, text: str) -> str:
        """Extract JSON from sentinel tags and clean it."""
        start = text.find("<RESULT_JSON>")
        end = text.find("</RESULT_JSON>")
        if start != -1 and end != -1:
            json_text = text[start+13:end].strip()
        else:
            json_text = text.strip()
        
        # Clean control characters and other JSON issues
        json_text = self._clean_json_text(json_text)
        return json_text
    
    def _extract_result_json_with_validation(self, text: str) -> tuple[str, bool]:
        """
        Extract JSON from sentinel tags with validation.
        Returns (extracted_json, has_sentinel_tags)
        """
        start = text.find("<RESULT_JSON>")
        end = text.find("</RESULT_JSON>")
        
        if start != -1 and end != -1:
            json_text = text[start+13:end].strip()
            return self._clean_json_text(json_text), True
        else:
            # No sentinel tags found, return the full text cleaned
            return self._clean_json_text(text.strip()), False
    
    def _extract_json_with_regex_fallback(self, text: str) -> str:
        """
        Attempt to extract JSON using regex patterns as a fallback.
        This is used when sentinel tags are missing.
        """
        import re
        
        # Try to find JSON-like structures in the text
        # Look for patterns that start with { and end with }
        json_patterns = [
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Simple nested braces
            r'\{.*?\}',  # Any content between braces
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                # Try to clean and validate this potential JSON
                cleaned = self._clean_json_text(match)
                try:
                    # Quick validation - if it can be parsed, it's probably valid
                    import json
                    json.loads(cleaned)
                    return cleaned
                except json.JSONDecodeError:
                    continue
        
        # If no valid JSON found, return the cleaned original text
        return self._clean_json_text(text.strip())

    def _clean_json_text(self, json_text: str) -> str:
        """Clean JSON text to remove control characters and other issues."""
        import re
        
        # Remove control characters (except \n, \r, \t)
        json_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_text)
        
        # Remove any non-printable characters but keep JSON structure
        json_text = re.sub(r'[^\x20-\x7E\n\r\t{}[\]",:]+', '', json_text)
        
        # Fix common JSON issues
        json_text = re.sub(r'\\n', '\\n', json_text)  # Ensure proper newline escaping
        json_text = re.sub(r'\\"', '\\"', json_text)  # Ensure proper quote escaping
        
        # Remove any trailing commas before closing braces/brackets
        json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
        
        # Fix unescaped quotes in content strings
        json_text = re.sub(r'"content":\s*"([^"]*)"([^"]*)"([^"]*)"', r'"content": "\1\2\3"', json_text)
        
        # Remove JSON fragments that might be embedded in content
        json_text = re.sub(r',\s*anchors_used:\s*\[\]', '', json_text)
        json_text = re.sub(r',\s*char_count\s*[0-9]*', '', json_text)
        json_text = re.sub(r'\s*anchors_used:\s*\[\]', '', json_text)
        json_text = re.sub(r'\s*char_count\s*[0-9]*', '', json_text)
        
        # Remove more complex JSON fragments
        json_text = re.sub(r',\s*anchors_used:\s*\[[^\]]*\]', '', json_text)
        json_text = re.sub(r'\s*anchors_used:\s*\[[^\]]*\]', '', json_text)
        json_text = re.sub(r',\s*anchors_used\s*$', '', json_text)
        json_text = re.sub(r'\s*anchors_used\s*$', '', json_text)
        
        # Remove any remaining problematic characters
        json_text = re.sub(r'[^\x20-\x7E\n\r\t{}[\]",:]+', '', json_text)
        
        # Fix malformed JSON with weird characters from AI
        json_text = re.sub(r'!([^"]*?)!', r'"\1"', json_text)  # Fix !text! to "text"
        json_text = re.sub(r'#([^"]*?)#', r'"\1"', json_text)  # Fix #text# to "text"
        json_text = re.sub(r'!!', '"', json_text)  # Fix !! to "
        json_text = re.sub(r'##', '"', json_text)  # Fix ## to "
        
        # Fix malformed schema_version
        json_text = re.sub(r'"schema_version"!:\s*!v1"', '"schema_version": "v1"', json_text)
        json_text = re.sub(r'"schema_version"!:\s*"!v1"', '"schema_version": "v1"', json_text)
        
        # Fix malformed keys and values
        json_text = re.sub(r'"!([^"]*?)!":', r'"\1":', json_text)  # Fix "!key!": to "key":
        json_text = re.sub(r':\s*!([^"]*?)!', r': "\1"', json_text)  # Fix : !value! to : "value"
        
        return json_text

    def _extract_last_sentence(self, text: str) -> str:
        """Extract the last sentence from text."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return sentences[-1] if sentences else ""

    def _generate_outline(self, date, prs_rows, clips_rows):
        """Generate a brief outline for the blog post using actual data anchors."""
        system = (
            "Return JSON only inside <RESULT_JSON>...</RESULT_JSON>. "
            "Do not add code fences or extra text."
        )
        
        # Extract actual anchors from the data
        pr_anchors = [row["anchor"] for row in prs_rows]
        clip_anchors = [row["anchor"] for row in clips_rows]
        all_anchors = pr_anchors + clip_anchors
        
        user = f"""
DATE: {date}

TASK:
Create a brief plan for a long-form blog post in Paul Chris Luke's voice.
Sections to plan: Hook, Context, What Shipped, Twitch Clips, Why It Matters, Human Story, Wrap-Up.

AVAILABLE DATA ANCHORS (use these exact anchor tokens):
{all_anchors}

DATA (MODEL-READABLE):
PRS_JSON:
<PRS_JSON>
{json.dumps(prs_rows, ensure_ascii=False)}
</PRS_JSON>

GITHUB_URLS (use these for proper linking):
{chr(10).join([f"{row['anchor']} -> {row.get('github_url', 'No URL')}" for row in prs_rows if row.get('github_url')])}

CLIPS_JSON:
<CLIPS_JSON>
{json.dumps(clips_rows, ensure_ascii=False)}
</CLIPS_JSON>

OUTPUT (JSON inside <RESULT_JSON> tags):
{{
  "schema_version":"v1",
  "thesis":"",
  "tone":{{"humor":"dry","energy":"medium"}},
  "section_plan":{{
    "Hook":{{"goal":"", "uses":[]}},
    "Context":{{"goal":"", "uses":[]}},
    "What Shipped":{{"goal":"", "uses":[]}},
    "Twitch Clips":{{"goal":"", "uses":[]}},
    "Why It Matters":{{"goal":"", "uses":[]}},
    "Human Story":{{"goal":"", "uses":[]}},
    "Wrap-Up":{{"goal":"", "uses":[]}}
  }},
  "transition_seeds":{{
    "Hook->Context":"",
    "Context->What Shipped":"",
    "What Shipped->Twitch Clips":"",
    "Twitch Clips->Why It Matters":"",
    "Why It Matters->Human Story":"",
    "Human Story->Wrap-Up":""
  }}
}}

RULES:
- For "uses" arrays, ONLY use the exact anchor tokens from AVAILABLE_DATA_ANCHORS above
- Distribute the available anchors across sections logically (e.g., EVENT anchors for "What Shipped", CLIP anchors for "Twitch Clips")
- If no data available, leave "uses" as empty arrays
- Focus on creating a coherent narrative flow
- Example: if you have [EVENT:54113400422] and [CLIP:abc123], use them like ["[EVENT:54113400422]", "[CLIP:abc123]"]
"""
        effective_tokens = self.ai_client.get_effective_max_tokens(700)
        raw = self.ai_client.generate(user, system, max_tokens=effective_tokens)
        
        # First, check if the response contains sentinel tags
        extracted_json, has_sentinel_tags = self._extract_result_json_with_validation(raw)
        
        try:
            js = json.loads(extracted_json)
            return js
        except json.JSONDecodeError as e:
            # Log the specific error with context about sentinel tags
            sanitized_raw = self._sanitize_ai_response_for_logging(raw)
            raw_sample = raw[:200] + "..." if len(raw) > 200 else raw
            
            if not has_sentinel_tags:
                logger.error(f"JSON parsing error in outline generation: {e}")
                logger.error(f"Missing <RESULT_JSON> sentinel tags in AI response")
                logger.error(f"Raw response sample: {raw_sample}")
                logger.error(f"Sanitized response: {sanitized_raw}")
                
                # Try regex-based extraction as fallback
                try:
                    fallback_json = self._extract_json_with_regex_fallback(raw)
                    js = json.loads(fallback_json)
                    logger.warning("Successfully extracted JSON using regex fallback after missing sentinel tags")
                    return js
                except json.JSONDecodeError as fallback_e:
                    logger.error(f"Regex fallback also failed: {fallback_e}")
                    raise ValueError(
                        f"AI response missing <RESULT_JSON> sentinel tags and no valid JSON found. "
                        f"Original error: {e}. Raw response sample: {raw_sample}"
                    )
            else:
                # Sentinel tags were present but JSON is malformed
                logger.error(f"JSON parsing error in outline generation: {e}")
                logger.error(f"Sentinel tags present but JSON is malformed")
                logger.error(f"Raw response sample: {raw_sample}")
                logger.error(f"Sanitized response: {sanitized_raw}")
                
                # Try the existing aggressive cleaning approach
                try:
                    json_text = self._extract_result_json(raw)
                    json_text = self._clean_json_text(json_text)
                    js = json.loads(json_text)
                    logger.warning("Successfully parsed JSON after aggressive cleaning")
                    return js
                except json.JSONDecodeError as clean_e:
                    logger.error(f"Aggressive cleaning also failed: {clean_e}")
                    raise ValueError(
                        f"AI response contains <RESULT_JSON> tags but JSON is malformed. "
                        f"Original error: {e}. Raw response sample: {raw_sample}"
                    )

    def _generate_sections_group(self, date, outline, state, prs_rows, clips_rows, group_name, sections_in_group, pr_ids=None, clip_ids=None):
        """Generate a group of sections in a single call with enhanced prompts."""
        pr_subset = [r for r in prs_rows if not pr_ids or f"[EVENT:{r['id']}]" in pr_ids]
        clip_subset = [r for r in clips_rows if not clip_ids or f"[CLIP:{r['id']}]" in clip_ids]

        # Determine word targets based on group (pushed to 2.7-3.2k total)
        if group_name == "hook_ctx":
            target_words = "850-1000 words combined"
            per_section_min, per_section_max = 425, 500
            max_tokens = self.ai_client.get_effective_max_tokens(2400)
        elif group_name == "shipped_clips":
            target_words = "1100-1250 words combined"
            per_section_min, per_section_max = 550, 625
            max_tokens = self.ai_client.get_effective_max_tokens(2600)
        elif group_name == "why_human_wrap":
            target_words = "1200-1400 words combined"
            per_section_min, per_section_max = 400, 467
            max_tokens = self.ai_client.get_effective_max_tokens(2800)
        else:
            target_words = "500-600 words per section"
            per_section_min, per_section_max = 500, 600
            max_tokens = self.ai_client.get_effective_max_tokens(2000)

        # Get voice prompt for consistency
        voice_prompt = self._load_voice_prompt()

        # Initialize motifs if not present
        if "motifs" not in state:
            state["motifs"] = ["automation paradox", "Clanker", "live-streaming rubber duck", "tech debt", "caffeine-fueled coding"]
        if "motifs_used" not in state:
            state["motifs_used"] = []

        system = f"""
{voice_prompt}

Return JSON only inside <RESULT_JSON>...</RESULT_JSON>. 
No extra text, no code fences. Long-form paragraphs only.

EVIDENCE BUDGET (HARD REQUIREMENTS):
- Include at least 3 concrete facts per section (IDs, numbers, filenames, config values, error strings)
- Use at least 1 transcript quote when clips are provided (prefix with "Transcript:")
- Mention exact IDs via anchors (e.g., [EVENT:53857843117], [CLIP:xyz])
- If fewer than 3 facts exist, use all available facts and add [MISSING:<field>] once

LENGTH ENFORCEMENT (CRITICAL):
- You have {max_tokens} tokens available - USE ALL OF THEM
- Target {target_words} total - DO NOT STOP EARLY
- Each section must be at least {per_section_min} words
- If you're under target, ADD MORE DETAIL, EXAMPLES, ANECDOTES
- Expand technical explanations, add more personal stories
- Include more [meta-aside] and [humor-dry] moments if needed

TONE REQUIREMENTS (must include in each section):
- One [meta-aside] line with self-aware commentary
- One [humor-dry] line with witty observation  
- One [dev-jargon] moment explained in plain English
- Use exactly one motif from MOTIFS (rotate to avoid repetition)
- Maintain Paul Chris Luke's distinctive voice throughout
"""
        
        uses_plan = {s: outline["section_plan"].get(s, {}).get("uses", []) for s in sections_in_group}
        goals_plan = {s: outline["section_plan"].get(s, {}).get("goal", "") for s in sections_in_group}

        # Create transition hints
        transition_hints = {}
        for i in range(len(sections_in_group) - 1):
            key = f"{sections_in_group[i]}->{sections_in_group[i+1]}"
            transition_hints[key] = outline.get("transition_seeds", {}).get(key, "")

        # Select motif for this group (enforce rotation - no repeats until all used)
        available_motifs = [m for m in state["motifs"] if m not in state["motifs_used"]]
        if not available_motifs:
            # All motifs used once, reset and start over
            available_motifs = state["motifs"]
            state["motifs_used"] = []
            logger.info(f"🔄 Motif rotation: All motifs used, resetting for {group_name}")
        
        selected_motif = available_motifs[0]
        state["motifs_used"].append(selected_motif)
        logger.info(f"🎭 Using motif '{selected_motif}' for {group_name} (used: {len(state['motifs_used'])}/{len(state['motifs'])})")

        user = f"""
DATE: {date}

MOTIFS: {state["motifs"]}
SELECTED_MOTIF: {selected_motif} (use this one in this section group)

STATE:
- thesis: {outline.get('thesis','')}
- tone: {outline.get('tone',{})}
- prev_last_sentence: "{state.get('prev_last_sentence','')}"
- transition_hints: {transition_hints}

SECTIONS (exact H2 headings in this order): {sections_in_group}
TARGET LENGTH: ~{target_words} words total for this group.
PER SECTION: ~{per_section_min}–{per_section_max} words.

SECTION_GOALS: {goals_plan}
SECTION_USES (anchors you MUST cite when available): {uses_plan}

Anchor format:
- Events: [EVENT:<id>] (for all GitHub events including PRs, issues, comments, etc.)
- Clips:  [CLIP:<id>] (for Twitch clips)
Do not output container tags as anchors. Example: "In [EVENT:53857843117], I raised the timeout to 900s and memory to 3008MB."

IMPORTANT: Use the GitHub URLs provided in GITHUB_URLS section for proper linking.
Instead of just using [EVENT:123], use the full GitHub URL when referencing events.
Example: "In [this pull request](https://github.com/paulchrisluke/pcl-labs/pull/44), I implemented..."

RULES (HARD):
- Start the first section with a one-sentence bridge from prev_last_sentence (do not repeat it verbatim)
- Include ≥ 3 concrete facts per section (IDs, numbers, filenames, config values, errors, quotes)
- If quoting a transcript, prefix with "Transcript:"
- Use exactly one motif per section from MOTIFS (rotate; do not reuse the same motif consecutively)
- First-person; witty; accurate; well-formatted markdown
- CRITICAL: Target {target_words} - DO NOT END EARLY, write until you reach the target
- Each section MUST be at least {per_section_min} words - if you're under, ADD MORE DETAIL
- Use ALL available tokens - the AI has {max_tokens} tokens available, USE THEM ALL
- Expand on technical details, add more examples, include more personal anecdotes
- If you're running short, add more meta-commentary and dry humor naturally
- CRITICAL: ONLY use anchors that exist in the provided data - DO NOT generate fake anchors like [CLIP:xyz] or [PR:1234]
- If no clips are available, do not reference clips at all - focus on other content

MARKDOWN FORMATTING RULES:
- Use **bold** for technical terms, config values, and key concepts
- Use `code formatting` for file names, commands, and technical values
- Use > blockquotes for transcript excerpts and important quotes
- Break long paragraphs into 2-3 shorter paragraphs for readability
- Use bullet points (-) for technical details and lists when appropriate
- Use numbered lists (1.) for step-by-step processes
- Use *italics* for emphasis and meta-commentary
- Keep paragraphs to 3-4 sentences maximum for better scanning
- DO NOT include [meta-aside], [humor-dry], or [dev-jargon] tags in the final output
- Write meta-commentary naturally without special tags
- IMPORTANT: When using bullet points, add a blank line before the first bullet
- Example: "The features include:\n\n- Feature 1\n- Feature 2" (not "The features include: - Feature 1")

DATA:
EVENTS_JSON:
<EVENTS_JSON>
{json.dumps(pr_subset, ensure_ascii=False)}
</EVENTS_JSON>

GITHUB_URLS (use these for proper linking):
{chr(10).join([f"{row['anchor']} -> {row.get('github_url', 'No URL')}" for row in pr_subset if row.get('github_url')])}

CLIPS_JSON:
<CLIPS_JSON>
{json.dumps(clip_subset, ensure_ascii=False)}
</CLIPS_JSON>

Return JSON only inside <RESULT_JSON>…</RESULT_JSON>:
{{
  "schema_version":"v1",
  "sections": {{
    "{sections_in_group[0]}": {{"content":"", "anchors_used":[], "char_count":0}},
    {(",".join([f'"{s}": {{"content":"", "anchors_used":[], "char_count":0}}' for s in sections_in_group[1:]]) if len(sections_in_group)>1 else "")}
  }}
}}
"""
        raw = self.ai_client.generate(user, system, max_tokens=max_tokens)
        try:
            js = json.loads(self._extract_result_json(raw))
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in section group {group_name}: {e}")
            # Sanitize raw response for logging
            sanitized_raw = self._sanitize_ai_response_for_logging(raw)
            logger.error(f"Raw response (sanitized): {sanitized_raw}")
            # Try to extract and clean the JSON more aggressively
            json_text = self._extract_result_json(raw)
            json_text = self._clean_json_text(json_text)
            try:
                js = json.loads(json_text)
            except json.JSONDecodeError:
                # Last resort: try to extract content manually
                logger.warning(f"Using manual content extraction for {group_name}")
                js = self._extract_content_manually(json_text, sections_in_group)
        
        # Quality gates with retry
        js = self._validate_and_retry_section_group(js, sections_in_group, uses_plan, state, user, system, max_tokens, group_name)
        
        # Update state with last sentence of the last section in group
        last_section = sections_in_group[-1]
        content = js["sections"][last_section]["content"]
        state["prev_last_sentence"] = self._extract_last_sentence(content)
        return js

    def _stitch_sections(self, outline, blocks):
        """Stitch sections together into final blog post."""
        order = ["Hook","Context","What Shipped","Twitch Clips","Why It Matters","Human Story","Wrap-Up"]
        parts = []
        for sec in order:
            if sec in blocks:
                # Clean the content before stitching
                raw_content = blocks[sec]['content'].strip()
                clean_content = self._clean_section_content(raw_content)
                
                # Generate SEO-friendly header based on content
                seo_header = self._generate_seo_header(sec, clean_content, outline)
                parts.append(f"## {seo_header}\n\n{clean_content}\n")
        content = "\n".join(parts).strip()
        return {
            "title": self._derive_title(outline, content),
            "description": self._derive_description(content),
            "tags": self._derive_tags(content),
            "content": content,
            "markdown_body": content
        }

    def _derive_title(self, outline, content):
        """Derive title from outline and content."""
        # Simple title derivation - could be enhanced
        thesis = outline.get("thesis", "")
        if thesis:
            # Extract a short title from the thesis
            words = thesis.split()[:8]  # First 8 words
            return " ".join(words).rstrip(".,!?")
        return "Daily Development Update"

    def _derive_description(self, content):
        """Derive meta description from content."""
        # Extract first paragraph or first few sentences
        first_para = content.split('\n\n')[0] if content else ""
        if len(first_para) > 150:
            first_para = first_para[:147] + "..."
        return first_para

    def _derive_tags(self, content):
        """Derive tags from content."""
        # Simple tag extraction - could be enhanced
        tags = ["development", "automation", "ai"]
        if "twitch" in content.lower():
            tags.append("streaming")
        if "github" in content.lower():
            tags.append("github")
        return tags

    def _validate_section_group(self, js, sections_in_group, uses_plan, state):
        """Validate section group quality and enforce requirements."""
        for section in sections_in_group:
            if section not in js.get("sections", {}):
                logger.warning(f"⚠️ Missing section: {section}")
                continue
                
            section_data = js["sections"][section]
            content = section_data.get("content", "")
            anchors_used = section_data.get("anchors_used", [])
            
            # Word count check
            word_count = len(content.split())
            if word_count < 400:
                logger.warning(f"⚠️ Section {section} too short: {word_count} words (min: 400)")
            
            # Anchor usage check (only warn if there are actual anchors expected)
            expected_anchors = uses_plan.get(section, [])
            if expected_anchors and not any(anchor in content for anchor in expected_anchors):
                logger.warning(f"⚠️ Section {section} missing required anchors: {expected_anchors}")
            elif not expected_anchors:
                logger.info(f"ℹ️ Section {section} has no anchor requirements (no data available)")
            
            # Continuity check for first section
            if section == sections_in_group[0] and state.get("prev_last_sentence"):
                # Check for topic overlap with previous sentence
                prev_words = set(state["prev_last_sentence"].lower().split())
                first_sentence = content.split('.')[0].lower()
                first_words = set(first_sentence.split())
                overlap = len(prev_words.intersection(first_words))
                if overlap < 2:
                    logger.warning(f"⚠️ Section {section} may lack continuity with previous content")
            
            logger.info(f"✅ Section {section}: {word_count} words, {len(anchors_used)} anchors used")

    def _needs_expansion(self, text: str, min_words: int = 450) -> bool:
        """Check if text needs expansion based on word count."""
        return len(re.findall(r"\w+", text)) < min_words

    def _validate_and_retry_section_group(self, js, sections_in_group, uses_plan, state, user, system, max_tokens, group_name):
        """Validate section group and retry if needed."""
        retry_needed = False
        retry_reasons = []
        
        for section in sections_in_group:
            if section not in js.get("sections", {}):
                logger.warning(f"⚠️ Missing section: {section}")
                continue
                
            section_data = js["sections"][section]
            content = section_data.get("content", "")
            anchors_used = section_data.get("anchors_used", [])
            
            # Word count check
            word_count = len(content.split())
            min_words = 450 if section != "Wrap-Up" else 300
            
            if word_count < min_words:
                retry_needed = True
                retry_reasons.append(f"Section {section} too short: {word_count} words (min: {min_words})")
            
            # Anchor usage check
            expected_anchors = uses_plan.get(section, [])
            if expected_anchors and not any(anchor in content for anchor in expected_anchors):
                retry_needed = True
                retry_reasons.append(f"Section {section} missing required anchors: {expected_anchors}")
        
        # Retry if needed
        if retry_needed:
            logger.warning(f"🔄 Retrying section group {group_name} due to: {', '.join(retry_reasons)}")
            fix_msg = f"REVISION REQUEST: {'; '.join(retry_reasons)}. Keep the same JSON shape; expand content only."
            retry_user = user + f"\n\n{fix_msg}"
            
            try:
                raw = self.ai_client.generate(retry_user, system, max_tokens=max_tokens)
                try:
                    js = json.loads(self._extract_result_json(raw))
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error in retry for {group_name}: {e}")
                    # Try to extract and clean the JSON more aggressively
                    json_text = self._extract_result_json(raw)
                    json_text = self._clean_json_text(json_text)
                    # If still failing, try to extract just the content fields
                    try:
                        js = json.loads(json_text)
                    except json.JSONDecodeError:
                        # Last resort: try to extract content manually
                        js = self._extract_content_manually(json_text, sections_in_group)
                logger.info(f"✅ Retry successful for section group {group_name}")
            except Exception as e:
                logger.error(f"❌ Retry failed for section group {group_name}: {e}")
                # Return original js if retry fails
        
        return js

    def _extract_content_manually(self, json_text: str, sections_in_group: List[str]) -> Dict:
        """Manually extract content from malformed JSON as last resort."""
        import re
        
        result = {"schema_version": "v1", "sections": {}}
        
        for section in sections_in_group:
            # Try to find content for this section with better pattern
            pattern = rf'"{section}":\s*{{\s*"content":\s*"([^"]*(?:\\.[^"]*)*)"'
            match = re.search(pattern, json_text, re.DOTALL)
            if match:
                content = match.group(1)
                # Clean up the content more aggressively
                content = content.replace('\\"', '"').replace('\\n', '\n')
                # Use the new cleaning method
                content = self._clean_section_content(content)
                
                result["sections"][section] = {
                    "content": content,
                    "anchors_used": [],
                    "char_count": len(content)
                }
            else:
                # Fallback: create empty section
                result["sections"][section] = {
                    "content": f"## {section}\n\n[Content extraction failed]",
                    "anchors_used": [],
                    "char_count": 0
                }
        
        return result

    def _clean_section_content(self, content: str) -> str:
        """Clean section content to remove JSON fragments and formatting issues."""
        import re
        
        # Remove JSON fragments that might be embedded in content
        content = re.sub(r',\s*anchors_used:\s*\[\]', '', content)
        content = re.sub(r',\s*char_count\s*[0-9]*', '', content)
        content = re.sub(r'\s*anchors_used:\s*\[\]', '', content)
        content = re.sub(r'\s*char_count\s*[0-9]*', '', content)
        
        # Remove more complex JSON fragments
        content = re.sub(r',\s*anchors_used:\s*\[[^\]]*\]', '', content)
        content = re.sub(r'\s*anchors_used:\s*\[[^\]]*\]', '', content)
        content = re.sub(r',\s*anchors_used\s*$', '', content)
        content = re.sub(r'\s*anchors_used\s*$', '', content)
        
        # Remove any remaining JSON-like fragments
        content = re.sub(r'\s*,\s*$', '', content)  # Remove trailing commas
        content = re.sub(r'^\s*,\s*', '', content)  # Remove leading commas
        
        # Clean up any malformed anchor references
        content = re.sub(r'\[\[([^\]]+)\]\]', r'[\1]', content)  # Fix double brackets
        
        # Remove any control characters
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        
        # Clean up extra whitespace while preserving markdown formatting
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Max 2 newlines
        # Don't normalize spaces too aggressively - preserve markdown formatting
        content = re.sub(r'[ \t]+', ' ', content)  # Normalize spaces but preserve line breaks
        content = content.strip()
        
        # Ensure proper markdown formatting
        # Fix any broken markdown links
        content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'[\1](\2)', content)
        
        # Fix malformed bullet points - add line breaks before bullets
        # Use a safer approach that preserves code blocks, inline code, and URLs
        content = self._fix_bullet_points_safely(content)
        
        # Ensure blockquotes have proper spacing
        content = re.sub(r'\n>', '\n\n>', content)
        content = re.sub(r'>\n', '>\n\n', content)
        
        # Remove meta-tags that shouldn't appear in final output
        content = re.sub(r'\[meta-aside\]', '', content)
        content = re.sub(r'\[humor-dry\]', '', content)
        content = re.sub(r'\[dev-jargon\]', '', content)
        content = re.sub(r'\[META-ASIDE\]', '', content)
        content = re.sub(r'\[HUMOR-DRY\]', '', content)
        content = re.sub(r'\[DEV-JARGON\]', '', content)
        
        # Clean up any extra spaces left by removed tags while preserving paragraph breaks
        # Normalize spaces and tabs but preserve newlines
        content = re.sub(r'[ \t]+', ' ', content)
        # Limit multiple consecutive newlines to maximum of two (preserve paragraph breaks)
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content

    def _generate_seo_header(self, section_name: str, content: str, outline: Dict) -> str:
        """Generate SEO-friendly headers based on section content and outline."""
        import re
        
        # Extract key terms from content for SEO
        content_lower = content.lower()
        
        # Section-specific header generation
        if section_name == "Hook":
            # Look for key project names, technologies, or themes
            if "automation" in content_lower:
                return "The Automation Paradox: Building Tools That Might Replace Me"
            elif "ai" in content_lower or "artificial intelligence" in content_lower:
                return "AI Development Insights: When Technology Meets Human Creativity"
            elif "blog" in content_lower or "content" in content_lower:
                return "Content Creation in the Age of AI: A Developer's Perspective"
            else:
                return "Daily Development Update: Behind the Scenes of Tech Innovation"
                
        elif section_name == "Context":
            if "project" in content_lower:
                return "Project Context: The Journey So Far"
            elif "challenge" in content_lower or "problem" in content_lower:
                return "The Challenge: Understanding the Problem Space"
            else:
                return "Setting the Stage: The Development Context"
                
        elif section_name == "What Shipped":
            if "feature" in content_lower:
                return "What Shipped: New Features and Improvements"
            elif "fix" in content_lower or "bug" in content_lower:
                return "What Shipped: Bug Fixes and Performance Improvements"
            elif "api" in content_lower:
                return "What Shipped: API Updates and Integration Improvements"
            else:
                return "What Shipped: Latest Development Updates"
                
        elif section_name == "Twitch Clips":
            if "stream" in content_lower or "live" in content_lower:
                return "Live Stream Highlights: Community Engagement and Feedback"
            else:
                return "Community Highlights: Twitch Stream Insights"
                
        elif section_name == "Why It Matters":
            if "impact" in content_lower:
                return "Why It Matters: The Broader Impact"
            elif "future" in content_lower:
                return "Why It Matters: Looking Toward the Future"
            else:
                return "Why It Matters: The Bigger Picture"
                
        elif section_name == "Human Story":
            if "experience" in content_lower or "journey" in content_lower:
                return "The Human Side: Personal Development Journey"
            elif "learning" in content_lower:
                return "The Human Side: Lessons Learned"
            else:
                return "The Human Side: Behind the Code"
                
        elif section_name == "Wrap-Up":
            if "conclusion" in content_lower or "summary" in content_lower:
                return "Wrapping Up: Key Takeaways and Next Steps"
            else:
                return "Final Thoughts: Reflections and Future Directions"
        
        # Fallback to section name if no specific match
        return section_name

    def _find_weakest_section(self, blocks: Dict) -> str:
        """Find the section with the lowest word count for expansion."""
        section_word_counts = {}
        for section_name, section_data in blocks.items():
            content = section_data.get("content", "")
            word_count = len(content.split())
            section_word_counts[section_name] = word_count
        
        if not section_word_counts:
            return "Wrap-Up"  # Default fallback
        
        weakest_section = min(section_word_counts.items(), key=lambda x: x[1])
        logger.info(f"📊 Section word counts: {section_word_counts}")
        logger.info(f"🔍 Weakest section: {weakest_section[0]} ({weakest_section[1]} words)")
        return weakest_section[0]

    def _expand_weakest_section(self, date: str, blocks: Dict, weakest_section: str, prs_rows: List, clips_rows: List) -> str:
        """Add 2 more paragraphs to the weakest section."""
        voice_prompt = self._load_voice_prompt()
        
        system = f"""
{voice_prompt}

Return JSON only inside <RESULT_JSON>...</RESULT_JSON>.
Add 2 more paragraphs of detail, humor, or reflection to the existing content.
Do not repeat sentences from the original content.
"""
        
        # Get the current content of the weakest section
        current_content = blocks.get(weakest_section, {}).get("content", "")
        
        user = f"""
DATE: {date}

SECTION_TO_EXPAND: {weakest_section}
CURRENT_CONTENT:
{current_content}

TASK:
Add exactly 2 more paragraphs (300-400 words total) to expand this section.
Focus on:
- Additional technical details or insights
- Humor or meta-commentary
- Personal reflection or broader implications
- Specific examples or anecdotes

RULES:
- Do NOT repeat any sentences from the current content
- Maintain Paul Chris Luke's voice and style
- Include at least one meta-commentary or dry humor moment naturally
- Add concrete details if possible
- Target 300-400 words for the expansion

MARKDOWN FORMATTING RULES:
- Use **bold** for technical terms, config values, and key concepts
- Use `code formatting` for file names, commands, and technical values
- Use > blockquotes for transcript excerpts and important quotes
- Break long paragraphs into 2-3 shorter paragraphs for readability
- Use bullet points (-) for technical details and lists when appropriate
- Use numbered lists (1.) for step-by-step processes
- Use *italics* for emphasis and meta-commentary
- Keep paragraphs to 3-4 sentences maximum for better scanning
- DO NOT include [meta-aside], [humor-dry], or [dev-jargon] tags in the final output
- Write meta-commentary naturally without special tags
- IMPORTANT: When using bullet points, add a blank line before the first bullet
- Example: "The features include:\n\n- Feature 1\n- Feature 2" (not "The features include: - Feature 1")

DATA:
EVENTS_JSON:
<EVENTS_JSON>
{json.dumps(prs_rows, ensure_ascii=False)}
</EVENTS_JSON>

GITHUB_URLS (use these for proper linking):
{chr(10).join([f"{row['anchor']} -> {row.get('github_url', 'No URL')}" for row in prs_rows if row.get('github_url')])}

CLIPS_JSON:
<CLIPS_JSON>
{json.dumps(clips_rows, ensure_ascii=False)}
</CLIPS_JSON>

Return JSON only inside <RESULT_JSON>…</RESULT_JSON>:
{{
  "schema_version": "v1",
  "expansion": {{
    "content": "",
    "word_count": 0
  }}
}}
"""
        
        effective_tokens = self.ai_client.get_effective_max_tokens(1000)
        raw = self.ai_client.generate(user, system, max_tokens=effective_tokens)
        try:
            js = json.loads(self._extract_result_json(raw))
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in expansion: {e}")
            json_text = self._extract_result_json(raw)
            json_text = self._clean_json_text(json_text)
            try:
                js = json.loads(json_text)
            except json.JSONDecodeError:
                # Last resort: create a simple expansion
                logger.warning("Using fallback expansion content")
                js = {
                    "schema_version": "v1",
                    "expansion": {
                        "content": f"\n\n[META-ASIDE] Sometimes the best features come from the most unexpected places. [HUMOR-DRY] Like when you're debugging at 3 AM and suddenly realize you've been solving the wrong problem entirely. This feature represents more than just technical achievement—it's a testament to the power of iteration, persistence, and the occasional stroke of genius that comes from staring at code for too long.",
                        "word_count": 0
                    }
                }
        
        expansion_content = js.get("expansion", {}).get("content", "")
        expansion_word_count = js.get("expansion", {}).get("word_count", 0)
        
        logger.info(f"📈 Expansion for {weakest_section}: {expansion_word_count} words")
        return expansion_content

    def _sanitize_ai_response_for_logging(self, ai_response: Union[str, Dict[str, Any]]) -> str:
        """Sanitize AI response for logging to avoid leaking model output or PII."""
        if isinstance(ai_response, dict):
            # If it's a dict, extract key information without content
            sanitized = {}
            for key, value in ai_response.items():
                if key in ["title", "description", "tags"]:
                    # Keep metadata but truncate if too long
                    if isinstance(value, str) and len(value) > 100:
                        sanitized[key] = value[:100] + "..."
                    else:
                        sanitized[key] = value
                elif key in ["content", "markdown_body", "response", "result"]:
                    # Truncate content fields
                    if isinstance(value, str):
                        sanitized[key] = f"[TRUNCATED: {len(value)} chars]"
                    else:
                        sanitized[key] = f"[TRUNCATED: {len(str(value))} chars]"
                else:
                    sanitized[key] = value
            return str(sanitized)
        elif isinstance(ai_response, str):
            # If it's a string, truncate and remove potential sensitive content
            if len(ai_response) > 500:
                truncated = ai_response[:500] + "..."
            else:
                truncated = ai_response
            
            # Remove potential API keys or tokens
            import re
            truncated = re.sub(r'[A-Za-z0-9]{20,}', '[REDACTED]', truncated)
            truncated = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', truncated)
            
            return truncated
        else:
            return f"[UNKNOWN_TYPE: {type(ai_response)}]"
    
    def _fix_bullet_points_safely(self, content: str) -> str:
        """
        Fix malformed bullet points while preserving code blocks, inline code, and URLs.
        
        This method splits the content into code and non-code sections, applies bullet
        fixing only to non-code sections, then reassembles the content.
        """
        import re
        
        # Split content into sections, preserving code blocks and inline code
        sections = []
        current_pos = 0
        
        # Find all fenced code blocks (```...```)
        fenced_pattern = r'```[\s\S]*?```'
        for match in re.finditer(fenced_pattern, content):
            # Add text before the code block
            if match.start() > current_pos:
                sections.append(('text', content[current_pos:match.start()]))
            # Add the code block
            sections.append(('fenced_code', match.group()))
            current_pos = match.end()
        
        # Add remaining text
        if current_pos < len(content):
            sections.append(('text', content[current_pos:]))
        
        # Process each section
        processed_sections = []
        for section_type, section_content in sections:
            if section_type == 'fenced_code':
                # Preserve fenced code blocks unchanged
                processed_sections.append(section_content)
            else:
                # Process text sections, but preserve inline code, URLs, and indented code blocks
                processed_content = self._fix_bullet_points_in_text(section_content)
                processed_sections.append(processed_content)
        
        return ''.join(processed_sections)
    
    def _fix_bullet_points_in_text(self, text: str) -> str:
        """
        Fix bullet points in text while preserving inline code, URLs, and indented code blocks.
        """
        import re
        
        # Split text into parts, preserving inline code, URLs, and indented code blocks
        parts = []
        current_pos = 0
        
        # Find inline code (`...`), URLs (http/https), and indented code blocks (4+ spaces at start of line)
        patterns = [
            (r'`[^`]*`', 'inline_code'),  # Inline code
            (r'https?://[^\s]+', 'url'),  # URLs
            (r'^    .*$', 'indented_code', re.MULTILINE),  # Indented code blocks (4+ spaces)
        ]
        
        # Collect all matches
        matches = []
        for pattern, match_type, *flags in patterns:
            pattern_flags = flags[0] if flags else 0
            for match in re.finditer(pattern, text, pattern_flags):
                matches.append((match.start(), match.end(), match_type, match.group()))
        
        # Sort matches by position
        matches.sort(key=lambda x: x[0])
        
        # Process text between matches
        for start, end, match_type, match_content in matches:
            # Add text before the match
            if start > current_pos:
                text_before = text[current_pos:start]
                processed_before = self._apply_bullet_fixes(text_before)
                parts.append(processed_before)
            
            # Add the preserved match
            parts.append(match_content)
            current_pos = end
        
        # Add remaining text
        if current_pos < len(text):
            remaining_text = text[current_pos:]
            processed_remaining = self._apply_bullet_fixes(remaining_text)
            parts.append(processed_remaining)
        
        return ''.join(parts)
    
    def _apply_bullet_fixes(self, text: str) -> str:
        """
        Apply bullet point fixes to text that doesn't contain code or URLs.
        """
        import re
        
        # Fix malformed bullet points - add line breaks before bullets
        # Only match at start of lines to avoid altering content
        text = re.sub(r'^([^`\n]*?): - ', r'\1:\n\n- ', text, flags=re.MULTILINE)
        text = re.sub(r'^([^`\n]*?)\. - ', r'\1.\n\n- ', text, flags=re.MULTILINE)
        text = re.sub(r'^([^`\n]*?)! - ', r'\1!\n\n- ', text, flags=re.MULTILINE)
        
        # Handle bullets with bold formatting
        text = re.sub(r'^([^`\n]*?): - \*\*', r'\1:\n\n- **', text, flags=re.MULTILINE)
        text = re.sub(r'^([^`\n]*?)\. - \*\*', r'\1.\n\n- **', text, flags=re.MULTILINE)
        text = re.sub(r'^([^`\n]*?)! - \*\*', r'\1!\n\n- **', text, flags=re.MULTILINE)
        
        return text
