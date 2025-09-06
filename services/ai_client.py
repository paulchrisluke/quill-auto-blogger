"""
Thin Cloudflare Workers AI client for M5 surgical AI inserts.
"""

import os
import requests
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

import tiktoken

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Model-specific token limits, context windows, and pricing
MODEL_LIMITS = {
    "openai/llama-3.1-8b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,
        "tiktoken_model": "cl100k_base",  # GPT-4 tokenizer (closest approximation for Llama)
        "parameters": "8B",  # 8 billion parameters
        "cost_per_million_tokens": 0.15,  # $0.15 per million tokens (3.1B-8B parameter range)
        "display_name": "Llama 3.1 8B Instruct"
    },
    "@cf/meta/llama-3.1-8b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,
        "tiktoken_model": "cl100k_base",
        "parameters": "8B",
        "cost_per_million_tokens": 0.15,
        "display_name": "Llama 3.1 8B Instruct (CF)"
    },
    "llama-3.1-8b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,
        "tiktoken_model": "cl100k_base",
        "parameters": "8B",
        "cost_per_million_tokens": 0.15,
        "display_name": "Llama 3.1 8B Instruct"
    },
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 8192,  # 8k tokens - 2x the output limit!
        "tiktoken_model": "cl100k_base",
        "parameters": "70B",
        "cost_per_million_tokens": 0.60,  # Higher cost for 70B model
        "display_name": "Llama 3.3 70B Instruct (Fast)"
    },
    "@cf/meta/llama-3.1-70b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,  # 4k tokens - same as 8B but better quality
        "tiktoken_model": "cl100k_base",
        "parameters": "70B",
        "cost_per_million_tokens": 0.60,  # Higher cost for 70B model
        "display_name": "Llama 3.1 70B Instruct"
    },
    "@cf/meta/llama-4-scout-17b-16e-instruct": {
        "context_window": 131000,  # 131k tokens - larger context window
        "max_output_tokens": 4096,  # 4k tokens - same limit but better quality
        "tiktoken_model": "cl100k_base",
        "parameters": "17B",
        "cost_per_million_tokens": 0.27,  # Lower cost than 70B model
        "display_name": "Llama 4 Scout 17B Instruct"
    }
}


class AIClientError(Exception):
    """Custom exception for AI client errors."""
    pass


class TokenLimitExceededError(AIClientError):
    """Raised when input tokens exceed model limits."""
    pass


class AIResponseError(AIClientError):
    """Raised when AI response is invalid or malformed."""
    pass


class CloudflareAIClient:
    """Minimal client for Cloudflare Workers AI."""

    def __init__(self) -> None:
        self.account_id: Optional[str] = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token: Optional[str] = os.getenv("CLOUDFLARE_API_TOKEN")
        self.model: str = os.getenv("CLOUDFLARE_AI_MODEL", "openai/llama-3.1-8b-instruct")
        self.timeout: float = int(os.getenv("AI_TIMEOUT_MS", "120000")) / 1000.0  # 120 seconds for 70B model
        self.seed: int = int(os.getenv("AI_SEED", "42"))
        self.default_max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "800"))
        
        # Token validation settings
        self.validate_tokens: bool = os.getenv("AI_VALIDATE_TOKENS", "true").lower() == "true"
        self.max_input_tokens: int = int(os.getenv("AI_MAX_INPUT_TOKENS", "0"))  # 0 = use model default

        if not self.account_id or not self.api_token:
            raise AIClientError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")

        self.base_url: str = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        
        # Initialize tokenizer for the model
        self._init_tokenizer()

    def _init_tokenizer(self) -> None:
        """Initialize the appropriate tokenizer for the model."""
        model_config = MODEL_LIMITS.get(self.model, MODEL_LIMITS["openai/llama-3.1-8b-instruct"])
        self.tokenizer = tiktoken.get_encoding(model_config["tiktoken_model"])
        self.model_config: Dict[str, Any] = model_config
        
        # Calculate model limit and clamp max_input_tokens
        model_limit = max(0, model_config["context_window"] - model_config["max_output_tokens"])
        
        if self.max_input_tokens == 0:
            # Use model limit if not configured
            self.max_input_tokens = model_limit
        else:
            # Clamp to model limit to prevent exceeding context window
            original_value = self.max_input_tokens
            self.max_input_tokens = min(self.max_input_tokens, model_limit)
            if original_value != self.max_input_tokens:
                logger.info(f"Clamped max_input_tokens from {original_value} to {self.max_input_tokens} (model limit)")
            
        logger.info(f"Initialized tokenizer for {self.model}, max input tokens: {self.max_input_tokens}")

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        if self.tokenizer is None:
            # Fallback to character-based estimation when tiktoken fails
            return len(text) // 4
        return len(self.tokenizer.encode(text))

    def _validate_token_limits(self, system: str, prompt: str, max_tokens: int) -> None:
        """Validate that the request doesn't exceed token limits."""
        if not self.validate_tokens:
            return
        
        # Ensure max_tokens is a positive integer
        if max_tokens <= 0:
            raise TokenLimitExceededError(f"max_tokens must be positive, got: {max_tokens}")
        
        # Count input tokens with clear separator for better estimation
        input_text = system + "\n\n" + prompt
        input_tokens = self._count_tokens(input_text)
        total_tokens = input_tokens + max_tokens
        
        if input_tokens > self.max_input_tokens:
            raise TokenLimitExceededError(
                f"Input tokens ({input_tokens:,}) exceed model limit ({self.max_input_tokens:,})"
            )
        
        if total_tokens > self.model_config["context_window"]:
            raise TokenLimitExceededError(
                f"Total tokens ({total_tokens:,}) exceed context window ({self.model_config['context_window']:,})"
            )
        
        if max_tokens > self.model_config["max_output_tokens"]:
            raise TokenLimitExceededError(
                f"Output tokens ({max_tokens:,}) exceed model limit ({self.model_config['max_output_tokens']:,})"
            )
        
        logger.info(f"Token validation passed - Input: {input_tokens:,}, Max output: {max_tokens:,}, Total: {total_tokens:,}")

    def generate(self, prompt: str, system: str, max_tokens: Optional[int] = None) -> str:
        """Generate text using Cloudflare Workers AI with comprehensive logging."""
        max_tokens = max_tokens or self.default_max_tokens
        
        # Validate token limits before making the request
        self._validate_token_limits(system, prompt, max_tokens)
        
        # Record start time for response time tracking
        start_time = time.time()
        request_timestamp = datetime.now().isoformat()
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": 0.15,  # Llama 4 Scout default
            "top_p": 0.9,
            "seed": self.seed,
        }

        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Extract token usage and log comprehensive details
            self._log_token_usage(data, system, prompt, response_time, request_timestamp)
            
            # Handle different response formats
            if "result" in data and "response" in data["result"]:
                # Old format
                return data["result"]["response"]
            elif "response" in data:
                # New format with JSON schema
                return data["response"]
            else:
                # Sanitize response data for logging (avoid leaking model output)
                sanitized_data = self._sanitize_response_for_logging(data)
                logger.error("Unexpected response format from AI service: %s", sanitized_data)
                raise AIResponseError("Unexpected response format from AI service")
        except requests.exceptions.Timeout:
            response_time = time.time() - start_time
            logger.error(f"AI request timed out after {self.timeout}s (actual: {response_time:.2f}s)")
            raise AIClientError(f"Request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            response_time = time.time() - start_time
            status = getattr(resp, "status_code", "unknown")
            reason = getattr(resp, "reason", "")
            url = getattr(resp, "url", self.base_url)
            logger.error("AI request failed: status=%s reason=%s url=%s response_time=%.2fs", 
                        status, reason, url, response_time)
            # Log sanitized error payload (avoid echoing prompts/PII)
            try:
                err = resp.json()
                safe = {k: err.get(k) for k in ("errors", "error", "message", "code") if k in err}
                logger.error("AI error (sanitized): %s", safe)
            except ValueError:
                # Truncate error body to avoid leaking sensitive data
                error_text = getattr(resp, "text", "")
                sanitized_text = self._sanitize_error_text(error_text)
                logger.debug("AI error body (non-JSON, sanitized): %s", sanitized_text)
            raise AIClientError(f"HTTP {status}: {reason}") from e
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("Unexpected error in AI request: %s (response_time=%.2fs)", e, response_time)
            raise AIClientError(f"Unexpected error: {e}")

    def _log_token_usage(self, response_data: dict, system: str, prompt: str, 
                        response_time: float, request_timestamp: str) -> None:
        """Log comprehensive AI usage details including model, tokens, response time, and cost."""
        try:
            # Extract token usage from response (Cloudflare doesn't provide this)
            usage = response_data.get("result", {}).get("usage", {}) or response_data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            
            # Cloudflare Workers AI doesn't return token usage, so we calculate it
            if input_tokens == 0 and output_tokens == 0:
                input_tokens = self._count_tokens(system + "\n\n" + prompt)
                # Handle both old and new response formats
                response_text = (response_data.get("result", {}).get("response", "") or 
                               response_data.get("response", ""))
                output_tokens = self._count_tokens(response_text)
            
            # Get model information and pricing
            model_info = self.model_config
            model_name = model_info.get("display_name", self.model)
            model_params = model_info.get("parameters", "Unknown")
            cost_per_million = model_info.get("cost_per_million_tokens", 0.15)
            
            # Calculate cost based on actual Cloudflare Workers AI pricing
            # Cloudflare uses blended pricing (input + output combined)
            total_tokens = input_tokens + output_tokens
            total_cost = (total_tokens / 1_000_000) * cost_per_million
            
            # Log comprehensive usage information
            logger.info(
                f"AI_USAGE - Model: {model_name} ({model_params}) | "
                f"Input: {input_tokens:,} tokens | Output: {output_tokens:,} tokens | "
                f"Total: {total_tokens:,} tokens | Response Time: {response_time:.2f}s | "
                f"Cost: ${total_cost:.4f} | Timestamp: {request_timestamp}"
            )
            
            # Also log in a more structured format for easier parsing
            logger.info(
                f"AI_USAGE_STRUCTURED - "
                f"model={self.model} display_name={model_name} parameters={model_params} "
                f"input_tokens={input_tokens} output_tokens={output_tokens} total_tokens={total_tokens} "
                f"response_time={response_time:.3f} cost={total_cost:.6f} "
                f"cost_per_million={cost_per_million} timestamp={request_timestamp}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to log token usage: {e}")

    def _sanitize_response_for_logging(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize response data for logging to avoid leaking model output or PII."""
        sanitized = {}
        for key, value in data.items():
            if key in ["response", "result", "content", "text", "output"]:
                # Truncate and mask actual content
                if isinstance(value, str):
                    sanitized[key] = f"[TRUNCATED: {len(value)} chars]"
                elif isinstance(value, dict) and "response" in value:
                    sanitized[key] = {"response": f"[TRUNCATED: {len(str(value['response']))} chars]"}
                else:
                    sanitized[key] = f"[TRUNCATED: {len(str(value))} chars]"
            elif key in ["errors", "error", "message", "code", "status"]:
                # Keep error information but sanitize content
                if isinstance(value, str):
                    sanitized[key] = self._sanitize_error_text(value)
                else:
                    sanitized[key] = value
            else:
                sanitized[key] = value
        return sanitized

    def _sanitize_error_text(self, text: str) -> str:
        """Sanitize error text to remove potential PII or sensitive data."""
        if not text:
            return ""
        
        # Truncate to reasonable length
        if len(text) > 256:
            text = text[:256] + "..."
        
        # Remove potential API keys, tokens, or other sensitive patterns
        import re
        # Remove potential API keys (common patterns)
        text = re.sub(r'[A-Za-z0-9]{20,}', '[REDACTED]', text)
        # Remove potential email addresses
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', text)
        # Remove potential URLs with sensitive paths
        text = re.sub(r'https?://[^\s]+', '[URL_REDACTED]', text)
        
        return text

