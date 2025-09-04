"""
AI-assisted content generation for M5 surgical inserts.
Handles caching, prompts, fallbacks, and output sanitization.
"""

import ast
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from .ai_client import CloudflareAIClient, AIClientError

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class AIInsertsService:
    """Service for generating AI-assisted content inserts."""
    
    def __init__(self):
        self.ai_enabled = os.getenv("AI_POLISH_ENABLED", "false").lower() == "true"
        self.cache_dir = Path("blogs/.cache/m5")
        self.ai_client = None
        self.voice_prompt = self._load_voice_prompt()
        
        if self.ai_enabled:
            try:
                self.ai_client = CloudflareAIClient()
                logger.info("AI client initialized successfully")
            except AIClientError as e:
                logger.warning(f"Failed to initialize AI client: {e}")
                self.ai_enabled = False
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
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
                logger.warning(f"Voice prompt file not found: {voice_prompt_path}")
                return ""
        except Exception as e:
            logger.error(f"Failed to load voice prompt: {e}")
            return ""
    
    def make_seo_description(
        self, 
        date: str, 
        inputs: Dict[str, Any],
        force_ai: bool = False
    ) -> str:
        """
        Generate SEO description (1-2 sentences).
        
        Args:
            date: Date in YYYY-MM-DD format
            inputs: Dictionary with title, tags_csv, lead, story_titles_csv
            
        Returns:
            SEO description string (≤220 chars)
        """
        cache_key = self._compute_cache_key("seo_description", inputs)
        cached_result = self._get_cached_result(date, cache_key)
        
        if cached_result and not force_ai:
            return cached_result
        
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = (
                    f"{self.voice_prompt}\n\n"
                    "Write a keyword-rich SEO description (1–3 sentences) in Paul Chris Luke's voice. "
                    "Include technical keywords like 'AI blog automation', 'schema-driven SEO', 'Twitch transcription', 'content deduplication', 'developer devlog'. "
                    "Aim for 120-180 characters."
                    "Return plain text only."
                )
                
                user_prompt = (
                    f"Title: {inputs.get('title', '')}\n"
                    f"Tags: {inputs.get('tags_csv', '')}\n"
                    f"Lead: {inputs.get('lead', '')}\n"
                    f"Stories: {inputs.get('story_titles_csv', '')}\n"
                    f"Goal: 1–3 sentences with technical keywords, 120-180 chars. Plain text only."
                )
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=100)
                sanitized = self._sanitize_text(result, max_length=160, ensure_period=True)
                
                # Fix incomplete sentences that end with dangling words
                sanitized = self._fix_incomplete_sentences(sanitized)
                
                # Ensure proper length for SEO (150-160 chars) without ellipses
                sanitized = self._clamp_seo_description(sanitized)
                
                if sanitized:
                    self._cache_result(date, cache_key, sanitized)
                    return sanitized
                    
            except AIClientError as e:
                logger.warning(f"AI generation failed for SEO description: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error in SEO description generation: {e}")
        
        # Fallback
        fallback = self._fallback_seo_description(inputs)
        return fallback
    
    def punch_up_title(
        self, 
        date: str, 
        title: str,
        force_ai: bool = False
    ) -> Optional[str]:
        """
        Generate improved title (25-70 chars).
        
        Args:
            date: Date in YYYY-MM-DD format
            title: Current title
            
        Returns:
            Improved title or None if fallback should be used
        """
        cache_key = self._compute_cache_key("title_punchup", {"title": title})
        cached_result = self._get_cached_result(date, cache_key)
        
        if cached_result and not force_ai:
            return cached_result
        
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = (
                    f"{self.voice_prompt}\n\n"
                    "Create an SEO-optimized title that describes the main features shipped today in Paul Chris Luke's voice. "
                    "Focus on technical keywords like 'AI', 'Content Generation', 'Schema', 'Automation', 'Blog Generation'. "
                    "Aim for 25-70 characters. "
                    "Return only the title."
                )
                
                user_prompt = f"Current title: {title}\n\nCreate a descriptive title that highlights the main features shipped today. Include technical keywords for better SEO. Aim for 25-70 characters."
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=60)
                sanitized = self._sanitize_text(result, max_length=70, ensure_period=False, strip_period=True)
                
                # Ensure minimum length for SEO
                if sanitized and len(sanitized) < 25:
                    # Pad with additional context if too short
                    sanitized = f"PCL Labs: {sanitized}"
                    if len(sanitized) > 70:
                        sanitized = sanitized[:67] + "..."
                
                if sanitized:
                    if self._validate_title_guardrails(sanitized, title):
                        self._cache_result(date, cache_key, sanitized)
                        return sanitized
                    else:
                        # Guardrail validation failed, return None to use fallback
                        return None
                    
            except AIClientError as e:
                logger.warning(f"AI generation failed for title punch-up: {e}")
        
        # Fallback: keep original
        return None
    
    def make_story_micro_intro(
        self, 
        date: str, 
        story_inputs: Dict[str, Any],
        force_ai: bool = False
    ) -> str:
        """
        Generate micro-intro for a story (10-35 words).
        
        Args:
            date: Date in YYYY-MM-DD format
            story_inputs: Dictionary with title, why, highlights_csv
            
        Returns:
            Micro-intro string (≤160 chars)
        """
        cache_key = self._compute_cache_key("story_micro_intro", story_inputs)
        cached_result = self._get_cached_result(date, cache_key)
        
        if cached_result and not force_ai:
            return cached_result
        
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = (
                    "Write two sentences explaining why this change matters. "
                    "No emojis. No marketing speak. Plain text only."
                )
                
                user_prompt = (
                    f"Title: {story_inputs.get('title', '')}\n"
                    f"Why: {story_inputs.get('why', '')}\n"
                    f"Highlights: {story_inputs.get('highlights_csv', '')}\n"
                    f"Goal: Two sentences, Plain text only."
                )
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=80)
                sanitized = self._sanitize_text(result, max_length=160, ensure_period=True)
                
                if sanitized:
                        self._cache_result(date, cache_key, sanitized)
                        return sanitized
                    
            except AIClientError as e:
                logger.error(f"AI generation failed for story micro-intro: {e}")
                # Fall back to simple description
                return self._fallback_story_micro_intro(story_inputs)
        
        # No AI available - use fallback
        logger.warning(f"AI not available for story micro-intro, using fallback: {story_inputs}")
        return self._fallback_story_micro_intro(story_inputs)

    def make_story_comprehensive_intro(
        self, 
        date: str, 
        story_inputs: Dict[str, Any],
        force_ai: bool = False
    ) -> str:
        """
        Generate comprehensive intro for a story (3-5 sentences explaining what, why, and benefits).
        
        Args:
            date: Date in YYYY-MM-DD format
            story_inputs: Dictionary with title, why, highlights_csv
            
        Returns:
            Story intro string
        """
        cache_key = self._compute_cache_key("story_comprehensive_intro", story_inputs)
        cached_result = self._get_cached_result(date, cache_key)
        
        if cached_result and not force_ai:
            return cached_result
        
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = (
                    "You are Paul Chris Luke. Write a 3-5 sentence story intro explaining: 1) What this feature does, "
                    "2) Why it matters, and 3) How it helps. Use your voice: thoughtful, technical but accessible. Return plain text only."
                )
                
                user_prompt = (
                    f"Title: {story_inputs.get('title', '')}\n"
                    f"Why: {story_inputs.get('why', '')}\n"
                    f"Highlights: {story_inputs.get('highlights_csv', '')}\n"
                    f"Write a 3-5 sentence intro explaining what, why, and benefits."
                )
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=600)
                sanitized = self._sanitize_text(result, max_length=None, ensure_period=True)
                
                # Enforce 2-4 sentence constraint
                if sanitized:
                    sentence_count = len([s for s in sanitized.split('.') if s.strip()])
                    if 2 <= sentence_count <= 4:
                        self._cache_result(date, cache_key, sanitized)
                        return sanitized
                    else:
                        logger.warning(f"Comprehensive intro sentence count {sentence_count} not in range 2-4, using fallback")
                        return self._fallback_story_comprehensive_intro(story_inputs)
                    
            except AIClientError as e:
                logger.error(f"AI generation failed for story comprehensive intro: {e}")
                # Fall back to simple description
                return self._fallback_story_comprehensive_intro(story_inputs)
        
        # No AI available - use fallback
        logger.warning(f"AI not available for story comprehensive intro, using fallback: {story_inputs}")
        return self._fallback_story_comprehensive_intro(story_inputs)

    def _fallback_story_micro_intro(self, story_inputs: Dict[str, Any]) -> str:
        """Generate fallback story micro intro."""
        title = story_inputs.get('title', '')
        why = story_inputs.get('why', '')
        
        if why:
            intro = f"{title}: {why}".strip()
        else:
            intro = title
        
        # Ensure it ends with period and fits length
        if not intro.endswith('.'):
            intro += '.'
        
        # Clamp to 160 chars
        if len(intro) > 160:
            intro = intro[:157] + '...'
        
        return intro

    def _fallback_story_comprehensive_intro(self, story_inputs: Dict[str, Any]) -> str:
        """Generate fallback story comprehensive intro."""
        title = story_inputs.get('title', '')
        why = story_inputs.get('why', '')
        highlights = story_inputs.get('highlights_csv', '').split(',')[:3]
        
        if why:
            intro = f"{title}: {why}".strip()
        else:
            intro = title
            
        if highlights:
            highlights_part = ", ".join(highlights).strip()
            if intro:
                intro += f" This feature improves {highlights_part}."
            else:
                intro = f"This feature improves {highlights_part}."
        
        # No character limit needed for body content
        return intro
    
    def _compute_cache_key(self, operation: str, inputs: Dict[str, Any]) -> str:
        """Compute stable cache key from operation and inputs."""
        # Create compact JSON representation with fallback for non-serializable values
        compact_json = json.dumps(inputs, separators=(',', ':'), sort_keys=True, default=str)
        # Include operation and model for cache separation
        model = getattr(self.ai_client, "model", "unknown") if self.ai_client else "fallback"
        key_data = f"{operation}:{model}:{compact_json}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def _validate_cache_date(self, date: str) -> Path:
        """Validate date format and return safe cache path."""
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            raise ValueError(f"Invalid date format: {date}. Expected YYYY-MM-DD")
        return self.cache_dir / date
    
    def _get_cached_result(self, date: str, cache_key: str) -> Optional[str]:
        """Get cached result if available."""
        try:
            date_cache_dir = self._validate_cache_date(date)
            cache_file = date_cache_dir / f"{cache_key}.txt"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return f.read().strip()
                except (OSError, UnicodeDecodeError) as e:
                    logger.warning(f"Failed to read cache file {cache_file}: {e}")
        except ValueError as e:
            logger.warning(f"Invalid date format for cache: {e}")
        return None
    
    def _cache_result(self, date: str, cache_key: str, result: str) -> None:
        """Cache successful AI result."""
        try:
            date_cache_dir = self._validate_cache_date(date)
            date_cache_dir.mkdir(exist_ok=True)
            
            cache_file = date_cache_dir / f"{cache_key}.txt"
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    f.write(result)
            except OSError as e:
                logger.warning(f"Failed to write cache file {cache_file}: {e}")
        except ValueError as e:
            logger.warning(f"Invalid date format for cache: {e}")
    
    def _sanitize_text(
        self, 
        text: str, 
        max_length: Optional[int] = None, 
        ensure_period: bool = True,
        strip_period: bool = False
    ) -> str:
        """
        Sanitize AI-generated text.
        
        Args:
            text: Raw AI output
            
        Returns:
            Sanitized text or empty string if invalid
        """
        if not text:
            return ""
        
        # Strip whitespace and quotes
        cleaned = text.strip().strip('"\'`')
        
        # Strip HTML tags and unescape entities
        import html
        import re
        cleaned = re.sub(r'<[^>]+>', '', cleaned)  # Remove HTML tags
        cleaned = html.unescape(cleaned)  # Unescape HTML entities
        
        # Remove markdown formatting
        cleaned = cleaned.replace('*', '').replace('_', '').replace('`', '')
        
        # Remove trailing commas and other punctuation (but preserve periods)
        cleaned = cleaned.rstrip(',;: ')
        
        # Collapse multiple whitespace
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove trailing comma if it exists (before adding period)
        if cleaned.endswith(','):
            cleaned = cleaned[:-1]
        
        # Remove comma-period combination
        if cleaned.endswith(',.'):
            cleaned = cleaned[:-2]
        
        # Check length BEFORE adding period to avoid overflow
        if max_length is not None:
            # Reserve space for period if needed
            budget = max_length - (1 if ensure_period and not cleaned.endswith('.') else 0)
            
            if len(cleaned) > budget:
                # Truncate at word boundary within budget
                words = cleaned.split()
                truncated = ""
                for word in words:
                    # Calculate length with space, but avoid leading space
                    test_length = len(truncated + (" " if truncated else "") + word)
                    if test_length <= budget:
                        truncated += (" " if truncated else "") + word
                    else:
                        break
                
                if truncated:
                    cleaned = truncated
                else:
                    return ""  # Can't fit even one word
        
        # Handle period based on requirements
        if strip_period and cleaned.endswith('.'):
            cleaned = cleaned[:-1]
        elif ensure_period and not cleaned.endswith('.'):
            cleaned += '.'
        
        return cleaned
    
    def _validate_title_guardrails(self, new_title: str, original_title: str) -> bool:
        """Validate that new title meets guardrail requirements."""
        # Check length constraints (25-70 chars for SEO)
        if len(new_title) < 25 or len(new_title) > 70:
            return False
        
        return True
    
    def _fallback_seo_description(self, inputs: Dict[str, Any]) -> str:
        """Generate fallback SEO description."""
        lead = inputs.get('lead', '')
        title = inputs.get('title', '')
        story_titles = inputs.get('story_titles_csv', '').split(',')[:2]
        
        if lead:
            fallback = lead
        else:
            story_part = ', '.join(story_titles).strip()
            if story_part:
                fallback = f"{title} — {story_part}."
            else:
                fallback = title
        
        # Clamp to 220 chars
        if len(fallback) > 220:
            fallback = fallback[:217] + "..."
        
        return fallback
    

    def make_holistic_intro(self, date: str, inputs: Dict[str, Any], force_ai: bool = False) -> str:
        """Generate holistic intro paragraph in Paul Chris Luke's voice."""
        cache_key = self._compute_cache_key("holistic_intro", inputs)
        cached_result = self._get_cached_result(date, cache_key)
        if cached_result and not force_ai:
            return cached_result
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = f"{self.voice_prompt}\n\nWrite a 3-4 sentence intro explaining today's work theme and how features connect. Naturally weave in technical keywords like 'AI blog automation', 'schema-driven SEO', 'Twitch transcription', 'content pipeline', 'developer workflow' when relevant. Follow the voice style above: poetic but grounded, with edgy humor and philosophical reflection. Return plain text only."
                user_prompt = f"Title: {inputs.get('title', '')} Stories: {inputs.get('story_titles_csv', '')} Write a holistic intro explaining today's theme and how features connect."
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=800)
                sanitized = self._sanitize_text(result, max_length=None, ensure_period=True)
                if sanitized:
                    self._cache_result(date, cache_key, sanitized)
                    return sanitized
            except AIClientError as e:
                logger.warning(f"AI generation failed for holistic intro: {e}")
        return self._fallback_holistic_intro(inputs)

    def suggest_tags(self, date: str, inputs: Dict[str, Any], force_ai: bool = False) -> List[str]:
        """Suggest relevant tags from content analysis."""
        cache_key = self._compute_cache_key("tag_suggestions", inputs)
        cached_result = self._get_cached_result(date, cache_key)
        if cached_result and not force_ai:
            try:
                # Try JSON first, fall back to ast.literal_eval for legacy formats
                return json.loads(cached_result)
            except (ValueError, json.JSONDecodeError, SyntaxError) as e:
                try:
                    return ast.literal_eval(cached_result)
                except (ValueError, SyntaxError) as e2:
                    logger.warning(f"Failed to parse cached tag suggestions: {e2}")
                    pass
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = "You are a content analyst. Extract 3-5 relevant long-tail keywords from the content. Focus on intent-driven phrases like 'AI blog automation', 'schema-driven SEO', 'Twitch transcription', 'content deduplication', 'developer devlog', 'automated content generation'. Return only a comma-separated list, no explanations or formatting."
                user_prompt = f"Title: {inputs.get('title', '')} Tags: {inputs.get('tags_csv', '')} Lead: {inputs.get('lead', '')} Stories: {inputs.get('story_titles_csv', '')} Goal: Extract 3-5 relevant long-tail keywords as comma-separated values, prioritizing intent-driven phrases and technical terms."
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=100)
                sanitized = self._sanitize_text(result, max_length=100, ensure_period=False)
                if sanitized:
                    tags = [tag.strip().lower() for tag in sanitized.split(',') if tag.strip()]
                    existing_tags = set([t for t in (s.strip().lower() for s in inputs.get('tags_csv', '').split(',')) if t])
                    filtered_tags = [tag for tag in tags if tag not in existing_tags and len(tag) > 2]
                    if filtered_tags:
                        # Cache the sliced list (≤5) with ensure_ascii=False for Unicode
                        tags_to_cache = filtered_tags[:5]
                        self._cache_result(date, cache_key, json.dumps(tags_to_cache, ensure_ascii=False))
                        return tags_to_cache
            except AIClientError as e:
                logger.warning(f"AI generation failed for tag suggestions: {e}")
        return self._fallback_tag_suggestions(inputs)

    def _fallback_holistic_intro(self, inputs: Dict[str, Any]) -> str:
        """Generate fallback holistic intro."""
        lead = inputs.get('lead', '')
        story_titles = inputs.get('story_titles_csv', '').split(',')[:2]
        
        if lead and story_titles:
            story_part = ', '.join(story_titles).strip()
            fallback = f"{lead} Today's work marks a turning point for this project — moving from building infrastructure to building the content engine itself. I shipped two big features: a schema and backend pipeline for generating and managing content at scale, and an AI-powered blog generator that can draft and enrich posts automatically. Together, these upgrades lay the foundation for a system that doesn't just capture development work but actively turns it into polished, production-ready content."
        else:
            fallback = "Today's work marks a turning point for this project — moving from building infrastructure to building the content engine itself. I shipped two big features: a schema and backend pipeline for generating and managing content at scale, and an AI-powered blog generator that can draft and enrich posts automatically. Together, these upgrades lay the foundation for a system that doesn't just capture development work but actively turns it into polished, production-ready content."
        
        # No character limit needed for body content
        return fallback

    def _fallback_tag_suggestions(self, inputs: Dict[str, Any]) -> List[str]:
        """Generate fallback tag suggestions."""
        story_titles = inputs.get('story_titles_csv', '').lower()
        existing_tags = set(inputs.get('tags_csv', '').lower().split(','))
        potential_tags = []
        if 'ai' in story_titles:
            potential_tags.append('ai')
        if 'blog' in story_titles:
            potential_tags.append('blog')
        if 'content' in story_titles:
            potential_tags.append('content')
        if 'api' in story_titles:
            potential_tags.append('api')
        if 'automation' in story_titles:
            potential_tags.append('automation')
        return [tag for tag in potential_tags if tag not in existing_tags][:3]

    def make_wrap_up(self, date: str, inputs: Dict[str, Any], force_ai: bool = False) -> str:
        """Generate wrap-up paragraph that ties the day's work together."""
        cache_key = self._compute_cache_key("wrap_up", inputs)
        cached_result = self._get_cached_result(date, cache_key)
        if cached_result and not force_ai:
            return cached_result
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = "You are Paul Chris Luke. Write a 2-3 sentence wrap-up explaining how today's features work together and what they enable. Use your voice: thoughtful, technical but accessible. Return plain text only."
                user_prompt = f"Title: {inputs.get('title', '')} Stories: {inputs.get('story_titles_csv', '')} Write a wrap-up explaining how today's features connect and what they enable."
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=600)
                sanitized = self._sanitize_text(result, max_length=None, ensure_period=True)
                if sanitized:
                    self._cache_result(date, cache_key, sanitized)
                    return sanitized
            except AIClientError as e:
                logger.warning(f"AI generation failed for wrap-up: {e}")
        return self._fallback_wrap_up(inputs)

    def _fallback_wrap_up(self, inputs: Dict[str, Any]) -> str:
        """Generate fallback wrap-up."""
        story_titles = inputs.get('story_titles_csv', '').split(',')[:2]
        if story_titles:
            story_part = ' and '.join(story_titles).strip()
            fallback = f"Today's work focused on {story_part}. Together these features move the project forward."
        else:
            fallback = "Today's development work adds new capabilities to the platform."
        return fallback
    
    def _fix_incomplete_sentences(self, text: str) -> str:
        """Fix incomplete sentences that end with dangling words."""
        if not text:
            return text
        
        # Common dangling words that indicate incomplete sentences (longer patterns first)
        dangling_words = ['for for.', 'with with.', 'to to.', 'with.', 'to.', 'while.', 'for.', 'and.', 'or.', 'but.', 'so.', 'yet.', 'enhanced.', 'improved.', 'optimized.']
        
        # First check for repeated words at the end (like "for for")
        words = text.split()
        fixed_repeated = False
        if len(words) >= 2:
            # Remove periods for comparison
            last_word = words[-1].rstrip('.')
            second_last_word = words[-2].rstrip('.')
            if last_word == second_last_word:
                # Remove the last repeated word and add period
                text = ' '.join(words[:-1]) + '.'
                fixed_repeated = True
        
        # Then check if text ends with any dangling word (but don't add text if we just fixed repeated words)
        for dangling in dangling_words:
            if text.endswith(dangling):
                # Remove the dangling word and period
                text = text[:-len(dangling)]
                # Clean up any trailing punctuation
                text = text.rstrip(',;: ')
                # Add a proper ending only if it's a single dangling word and we didn't just fix repeated words
                if len(dangling.split()) == 1 and not fixed_repeated:  # Single word like "for." not "for for."
                    text += ' for better performance.'
                break
        
        return text
    
    def _clamp_seo_description(self, text: str) -> str:
        """Clamp SEO description to 150-160 chars without ellipses."""
        if not text:
            return text
        
        # If we just fixed an incomplete sentence, don't truncate further
        if text.endswith('for better performance.'):
            return text
        
        # Target 150 chars for optimal SEO (broader range 120-180)
        target_length = 150
        
        if len(text) <= target_length:
            return text
        
        # Truncate at word boundary within target length
        words = text.split()
        truncated = ""
        for word in words:
            test_length = len(truncated + (" " if truncated else "") + word)
            if test_length <= target_length:
                truncated += (" " if truncated else "") + word
            else:
                break
        
        # Ensure it ends with a period
        if truncated and not truncated.endswith('.'):
            truncated += '.'
        
        return truncated
