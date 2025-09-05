"""
Thin Cloudflare Workers AI client for M5 surgical AI inserts.
"""

import os
import requests
import logging
import tiktoken
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Model-specific token limits and context windows
MODEL_LIMITS = {
    "openai/llama-3.1-8b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,
        "tiktoken_model": "cl100k_base"  # GPT-4 tokenizer (closest approximation for Llama)
    },
    "@cf/meta/llama-3.1-8b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,
        "tiktoken_model": "cl100k_base"
    },
    "llama-3.1-8b-instruct": {
        "context_window": 128000,  # 128k tokens
        "max_output_tokens": 4096,
        "tiktoken_model": "cl100k_base"
    }
}


class AIClientError(Exception):
    """Custom exception for AI client errors."""
    pass


class TokenLimitExceededError(AIClientError):
    """Raised when input tokens exceed model limits."""
    pass


class CloudflareAIClient:
    """Minimal client for Cloudflare Workers AI."""

    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.model = os.getenv("CLOUDFLARE_AI_MODEL", "openai/llama-3.1-8b-instruct")
        self.timeout = int(os.getenv("AI_TIMEOUT_MS", "60000")) / 1000.0  # 60 seconds for longer content
        self.seed = int(os.getenv("AI_SEED", "42"))
        self.default_max_tokens = int(os.getenv("AI_MAX_TOKENS", "800"))
        
        # Token validation settings
        self.validate_tokens = os.getenv("AI_VALIDATE_TOKENS", "true").lower() == "true"
        self.max_input_tokens = int(os.getenv("AI_MAX_INPUT_TOKENS", "0"))  # 0 = use model default

        if not self.account_id or not self.api_token:
            raise AIClientError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")

        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        
        # Initialize tokenizer for the model
        self._init_tokenizer()

    def _init_tokenizer(self):
        """Initialize the appropriate tokenizer for the model."""
        try:
            model_config = MODEL_LIMITS.get(self.model, MODEL_LIMITS["openai/llama-3.1-8b-instruct"])
            self.tokenizer = tiktoken.get_encoding(model_config["tiktoken_model"])
            self.model_config = model_config
            
            # Set max input tokens if not configured
            if self.max_input_tokens == 0:
                self.max_input_tokens = model_config["context_window"] - model_config["max_output_tokens"]
                
            logger.info(f"Initialized tokenizer for {self.model}, max input tokens: {self.max_input_tokens}")
        except Exception as e:
            logger.warning(f"Failed to initialize tokenizer: {e}. Falling back to character-based estimation.")
            self.tokenizer = None
            self.model_config = MODEL_LIMITS.get(self.model, MODEL_LIMITS["openai/llama-3.1-8b-instruct"])

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken or fallback to estimation."""
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as e:
                logger.warning(f"Token counting failed: {e}. Using estimation.")
        
        # Fallback to character-based estimation
        return self._estimate_tokens(text)

    def _validate_token_limits(self, system: str, prompt: str, max_tokens: int) -> None:
        """Validate that the request doesn't exceed token limits."""
        if not self.validate_tokens:
            return
            
        input_tokens = self._count_tokens(system + prompt)
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

    def generate(self, prompt: str, system: str, max_tokens: int = None) -> str:
        """Generate text using Cloudflare Workers AI with token usage tracking."""
        max_tokens = max_tokens or self.default_max_tokens
        
        # Validate token limits before making the request
        self._validate_token_limits(system, prompt, max_tokens)
        
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
            "temperature": 0.3,
            "top_p": 0.9,
            "seed": self.seed,
        }

        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            
            # Extract token usage and log cost
            self._log_token_usage(data, system, prompt)
            
            return data["result"]["response"]
        except requests.exceptions.Timeout:
            raise AIClientError(f"Request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            status = getattr(resp, "status_code", "unknown")
            reason = getattr(resp, "reason", "")
            url = getattr(resp, "url", self.base_url)
            logger.error("AI request failed: status=%s reason=%s url=%s", status, reason, url)
            # Log sanitized error payload (avoid echoing prompts/PII)
            try:
                err = resp.json()
                safe = {k: err.get(k) for k in ("errors", "error", "message", "code") if k in err}
                logger.error("AI error (sanitized): %s", safe)
            except ValueError:
                logger.debug("AI error body (non-JSON, truncated): %s", getattr(resp, "text", "")[:256])
            raise AIClientError(str(e)) from e
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            raise AIClientError(str(e)) from e

    def _log_token_usage(self, response_data: dict, system: str, prompt: str) -> None:
        """Log token usage and estimated cost."""
        try:
            # Extract token usage from response (Cloudflare doesn't provide this)
            usage = response_data.get("result", {}).get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            
            # Cloudflare Workers AI doesn't return token usage, so we calculate it
            if input_tokens == 0 and output_tokens == 0:
                input_tokens = self._count_tokens(system + prompt)
                response_text = response_data.get("result", {}).get("response", "")
                output_tokens = self._count_tokens(response_text)
            
            # Calculate estimated cost (Cloudflare Workers AI pricing)
            # Input: ~$0.50 per 1M tokens, Output: ~$1.50 per 1M tokens
            input_cost = (input_tokens / 1_000_000) * 0.50
            output_cost = (output_tokens / 1_000_000) * 1.50
            total_cost = input_cost + output_cost
            
            logger.info(
                f"AI Token Usage - Input: {input_tokens:,} tokens, "
                f"Output: {output_tokens:,} tokens, "
                f"Estimated Cost: ${total_cost:.4f}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to log token usage: {e}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count based on character count (rough approximation)."""
        if not text:
            return 0
        # Rough approximation: 4 characters ≈ 1 token
        return max(1, len(text) // 4)
