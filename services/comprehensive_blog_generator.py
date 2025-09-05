"""
Comprehensive AI blog generator.
Generates entire blog posts from raw data in a single AI call.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from .ai_client import CloudflareAIClient, AIClientError, TokenLimitExceededError

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
                logger.error(f"Failed to initialize comprehensive blog generator: {e}")
                raise
    
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
        Generate complete blog content from raw data.
        
        Args:
            date: Date in YYYY-MM-DD format
            twitch_clips: List of Twitch clip data
            github_events: List of GitHub event data
            
        Returns:
            Dictionary with title, description, tags, and markdown content
            
        Raises:
            AIClientError: If AI generation fails
        """
        if not self.ai_enabled or not self.ai_client:
            raise AIClientError("Comprehensive AI generation not available")
        
        try:
            # Prepare data for AI
            ai_data = self._prepare_ai_data(date, twitch_clips, github_events)
            
            # Generate comprehensive prompt
            system_prompt, user_prompt = self._create_comprehensive_prompt(ai_data)
            
            # Call AI with higher token limit for longer, more detailed content
            max_tokens = int(os.getenv("AI_COMPREHENSIVE_MAX_TOKENS", "8000"))
            logger.info(f"Sending comprehensive blog generation request for {date} to AI...")
            logger.info(f"System prompt length: {len(system_prompt)}")
            logger.info(f"User prompt length: {len(user_prompt)}")
            logger.info(f"Total prompt length: {len(system_prompt) + len(user_prompt)}")
            logger.info(f"Max tokens: {max_tokens}")
            # Log actual token count if available
            if hasattr(self.ai_client, '_count_tokens'):
                estimated_tokens = self.ai_client._count_tokens(system_prompt + user_prompt)
                logger.info(f"Estimated input tokens: {estimated_tokens:,}")
            else:
                logger.info(f"Estimated input tokens: {(len(system_prompt) + len(user_prompt)) // 4}")
            result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=max_tokens)
            
            # Parse AI response
            parsed_content = self._parse_ai_response(result, date)
            
            logger.info(f"Successfully generated comprehensive blog content for {date}")
            return parsed_content
            
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
            max_tokens = int(os.getenv("AI_COMPREHENSIVE_MAX_TOKENS", "8000")) // 2  # Reduce by half
            
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
        """Filter GitHub events to only include merged PullRequestEvents."""
        merged_events = []
        
        for event in events:
            # Only include PullRequestEvents that are merged
            if event.get('type') == 'PullRequestEvent':
                # Check if the PR was merged
                details = event.get('details', {})
                if details.get('merged', False):
                    merged_events.append(event)
                    logger.info(f"Including merged PR: {details.get('title', 'No title')} (PR #{details.get('number', 'No number')})")
        
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
            "key_achievements": [e.get('title', '') for e in merged_prs[:3]],  # Top 3 merged PRs
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
- **Hook**: Start with a compelling, personality-driven opening (like "August 25, 2025, will go down as the day I became a Clanker.")
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

STORY CONTEXT:
This is a day in the life of Paul Chris Luke, a developer who live-streams his coding sessions and builds AI automation tools. The irony is that he's building tools that might eventually replace parts of his own job, all while live-streaming the process and explaining the absurdity of it to his audience.

The "Clanker" reference comes from a derogatory term for AI, which becomes hilariously ironic when you're the one building AI systems. This creates a meta-commentary about the automation paradox - building tools that automate the very work you're doing.

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

EXAMPLE OF GOOD PR WRITING:
Instead of: "The first PR, #32, was a feature/clip recap pipeline analysis, which included daily recap posts generated as standard Markdown files, pull requests targeting the staging branch by default, and updated notification wording for the bot channel."

Do this: "The first major milestone of the day was PR #32: clip recap pipeline analysis, which transformed how Twitch highlights get processed inside my system. Up until now, handling clips was messy — duplicates, inconsistent formatting, and a lot of manual cleanup. With this PR, I introduced caching and deduplication that make ingestion far more efficient. On top of that, the pipeline now generates daily recap posts in Markdown, automatically creating structured updates I can share with my community. Even the bot's notifications were polished with clearer wording, making the workflow more transparent for both me and my viewers. In short, this wasn't just about technical optimization; it was about building a smoother bridge between live-streaming content and developer storytelling."

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
- Example: "But development doesn't happen in isolation. While the code merged quietly in the background, Twitch captured the human side of the work — the jams, the commentary, and yes, the irony of calling myself a Clanker."
- Use transitional phrases that connect themes across sections
- Make the flow feel like a continuous story, not separate sections

HUMAN STORY EXPANSION:
- Include tension between efficiency vs. creativity
- Explore the absurdity of "building tools that build tools"
- Add reflection on community feedback (viewer comments, PR reception)
- Include personal insights about the development process
- Connect to broader themes about automation and human creativity

LENGTH AND DETAIL REQUIREMENTS (CRITICAL):
- Target 1500-2500 words total (more manageable for API)
- Each section should be substantial and detailed (2-3 paragraphs each)
- Include specific examples, quotes, and anecdotes
- Expand on the human story and meta-commentary extensively
- Make it feel like a comprehensive, engaging read
- Don't rush through sections - give each one proper depth and development
- Use the full narrative structure with rich detail in every section

IMPORTANT: 
- Start with a personality-driven hook (like "August 25, 2025, will go down as the day I became a Clanker.")
- Include self-aware humor and meta-commentary throughout
- End with a witty, memorable closer
- Avoid generic corporate language
- Write like you're telling a story to a friend
- Focus on the narrative flow and personality, not technical formatting
- NO BULLET POINTS OR LISTS - use flowing paragraphs instead
- BE EXTENSIVE - this should be a substantial, detailed blog post

CRITICAL JSON FORMATTING REQUIREMENTS:
- All newlines in the content field must be escaped as \\n
- All quotes in the content must be escaped as \\"
- The response must be valid JSON that can be parsed
- Do not include any text outside the JSON object

Return only the JSON response as specified in the system prompt."""

        return system_prompt, user_prompt
    
    def _parse_ai_response(self, ai_response: str, date: str = None) -> Dict[str, Any]:
        """Parse AI response into structured format."""
        try:
            # Clean up the response (remove any markdown formatting if present)
            cleaned_response = ai_response.strip()
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
                    if attempt == len(parse_attempts):
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
            logger.error(f"AI Response: {ai_response}")
            
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
                raise ValueError(f"Invalid JSON response from AI: {e}")
                
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            logger.error(f"AI Response: {ai_response}")
            raise ValueError(f"Failed to parse AI response: {e}")
    
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
        
        # Use a more sophisticated regex that handles escaped quotes
        # This pattern matches strings but respects escaped quotes
        fixed_text = re.sub(r'"((?:[^"\\]|\\.)*)"', fix_newlines_in_strings, json_text)
        
        return fixed_text
    
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
