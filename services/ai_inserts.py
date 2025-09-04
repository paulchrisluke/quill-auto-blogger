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
        
        if self.ai_enabled:
            try:
                self.ai_client = CloudflareAIClient()
                logger.info("AI client initialized successfully")
            except AIClientError as e:
                logger.warning(f"Failed to initialize AI client: {e}")
                self.ai_enabled = False
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
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
                    "You are editing a published devlog. Write a keyword-rich SEO description (1–2 sentences). "
                    "Include technical terms like 'APIs', 'background jobs', 'drafting', 'enriching', 'publishing', 'automation'. "
                    "No marketing fluff. No emojis. Keep it factual and helpful. "
                    "Return plain text only. <= 220 characters."
                )
                
                user_prompt = (
                    f"Title: {inputs.get('title', '')}\n"
                    f"Tags: {inputs.get('tags_csv', '')}\n"
                    f"Lead: {inputs.get('lead', '')}\n"
                    f"Stories: {inputs.get('story_titles_csv', '')}\n"
                    f"Goal: 1–2 sentence description with technical keywords, <= 220 chars. Plain text only."
                )
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=100)
                sanitized = self._sanitize_text(result, max_length=220, ensure_period=True)
                
                if sanitized:
                    self._cache_result(date, cache_key, sanitized)
                    return sanitized
                    
            except AIClientError as e:
                logger.warning(f"AI generation failed for SEO description: {e}")
        
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
        Generate improved title (≤80 chars, must include "Daily Devlog").
        
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
                    "Create an SEO-optimized title that describes the main features shipped today. "
                    "Focus on technical keywords like 'AI', 'Content Generation', 'Schema', 'Automation', 'Blog Generation'. "
                    "Make it descriptive and engaging for developers. Keep under 80 chars. Return only the title."
                )
                
                user_prompt = f"Current title: {title}\n\nCreate a descriptive title that highlights the main features shipped today. Include technical keywords for better SEO."
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=60)
                sanitized = self._sanitize_text(result, max_length=80, ensure_period=False)
                
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
        Generate micro-intro for a story (15-28 words).
        
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
                    "Write one sentence explaining why this change matters. 15–28 words. "
                    "No emojis. No marketing speak. Plain text only."
                )
                
                user_prompt = (
                    f"Title: {story_inputs.get('title', '')}\n"
                    f"Why: {story_inputs.get('why', '')}\n"
                    f"Highlights: {story_inputs.get('highlights_csv', '')}\n"
                    f"Goal: One sentence, 15–28 words. Plain text only."
                )
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=80)
                sanitized = self._sanitize_text(result, max_length=160, ensure_period=True)
                
                if sanitized:
                    self._cache_result(date, cache_key, sanitized)
                    return sanitized
                    
            except AIClientError as e:
                logger.error(f"AI generation failed for story micro-intro: {e}")
                raise RuntimeError(f"AI generation failed for story micro-intro: {e}")
        
        # No fallback - AI must work
        logger.error(f"AI generation failed for story micro-intro: {story_inputs}")
        raise RuntimeError(f"AI generation failed for story micro-intro. Inputs: {story_inputs}")

    def make_story_comprehensive_intro(
        self, 
        date: str, 
        story_inputs: Dict[str, Any],
        force_ai: bool = False
    ) -> str:
        """
        Generate comprehensive intro for a story (3 sentences explaining what, why, and benefits).
        
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
                    "You are Paul Chris Luke. Write a 3-sentence story intro explaining: 1) What this feature does, "
                    "2) Why it matters, and 3) How it helps. Use your voice: thoughtful, technical but accessible. Return plain text only."
                )
                
                user_prompt = (
                    f"Title: {story_inputs.get('title', '')}\n"
                    f"Why: {story_inputs.get('why', '')}\n"
                    f"Highlights: {story_inputs.get('highlights_csv', '')}\n"
                    f"Write a 3-sentence intro explaining what, why, and benefits."
                )
                
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=600)
                sanitized = self._sanitize_text(result, max_length=None, ensure_period=True)
                
                if sanitized:
                    self._cache_result(date, cache_key, sanitized)
                    return sanitized
                    
            except AIClientError as e:
                logger.error(f"AI generation failed for story comprehensive intro: {e}")
                raise RuntimeError(f"AI generation failed for story comprehensive intro: {e}")
        
        # No fallback - AI must work
        logger.error(f"AI generation failed for story comprehensive intro: {story_inputs}")
        raise RuntimeError(f"AI generation failed for story comprehensive intro. Inputs: {story_inputs}")

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
        # Create compact JSON representation
        compact_json = json.dumps(inputs, separators=(',', ':'), sort_keys=True)
        # Include operation and model for cache separation
        model = self.ai_client.model if self.ai_client else "fallback"
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
        ensure_period: bool = True
    ) -> str:
        """
        Sanitize AI-generated text.
        
        Args:
            text: Raw AI output
            max_length: Maximum allowed length (None for no limit)
            ensure_period: Whether to ensure text ends with a period
            
        Returns:
            Sanitized text or empty string if invalid
        """
        if not text:
            return ""
        
        # Strip whitespace and quotes
        cleaned = text.strip().strip('"\'`')
        
        # Remove markdown formatting
        cleaned = cleaned.replace('*', '').replace('_', '').replace('`', '')
        
        # Collapse multiple whitespace
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Ensure period if required
        if ensure_period and not cleaned.endswith('.'):
            cleaned += '.'
        
        # Check length
        if max_length is not None and len(cleaned) > max_length:
            # Truncate at word boundary
            words = cleaned.split()
            truncated = ""
            for word in words:
                # Calculate length with space, but avoid leading space
                test_length = len(truncated + (" " if truncated else "") + word)
                if test_length <= max_length:
                    truncated += (" " if truncated else "") + word
                else:
                    break
            
            if truncated:
                if ensure_period and not truncated.endswith('.'):
                    truncated += '.'
                cleaned = truncated
            else:
                return ""  # Can't fit even one word
        
        return cleaned
    
    def _validate_title_guardrails(self, new_title: str, original_title: str) -> bool:
        """Validate that new title meets guardrail requirements."""
        # Only check length - allow AI to be creative with titles
        if len(new_title) > 80:
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
    
    def _fallback_story_micro_intro(self, story_inputs: Dict[str, Any]) -> str:
        """Generate fallback story micro-intro."""
        title = story_inputs.get('title', '')
        why = story_inputs.get('why', '')
        
        fallback = f"{title}: {why}".strip()
        
        # Clamp to 160 chars and ensure period
        if len(fallback) > 160:
            fallback = fallback[:157] + "..."
        
        if not fallback.endswith('.'):
            fallback += '.'
        
        return fallback

    def make_holistic_intro(self, date: str, inputs: Dict[str, Any], force_ai: bool = False) -> str:
        """Generate holistic intro paragraph in Paul Chris Luke's voice."""
        cache_key = self._compute_cache_key("holistic_intro", inputs)
        cached_result = self._get_cached_result(date, cache_key)
        if cached_result and not force_ai:
            return cached_result
        if self.ai_enabled and self.ai_client:
            try:
                system_prompt = "You are Paul Chris Luke. Write a 3-4 sentence intro explaining today's work theme and how features connect. Use your voice: thoughtful, technical but accessible. Return plain text only."
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
                system_prompt = "You are a content analyst. Extract 3-5 relevant keywords from the content. Focus on technical terms like 'ai', 'content generation', 'blog automation', 'scalability', 'automation'. Return only a comma-separated list, no explanations or formatting."
                user_prompt = f"Title: {inputs.get('title', '')} Tags: {inputs.get('tags_csv', '')} Lead: {inputs.get('lead', '')} Stories: {inputs.get('story_titles_csv', '')} Goal: Extract 3-5 relevant keywords as comma-separated values, prioritizing technical terms."
                result = self.ai_client.generate(user_prompt, system_prompt, max_tokens=100)
                sanitized = self._sanitize_text(result, max_length=100, ensure_period=False)
                if sanitized:
                    tags = [tag.strip().lower() for tag in sanitized.split(',') if tag.strip()]
                    existing_tags = set([t for t in (s.strip().lower() for s in inputs.get('tags_csv', '').split(',')) if t])
                    filtered_tags = [tag for tag in tags if tag not in existing_tags and len(tag) > 2]
                    if filtered_tags:
                        self._cache_result(date, cache_key, str(filtered_tags))
                        return filtered_tags[:5]
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
