"""
Thin Cloudflare Workers AI client for M5 surgical AI inserts.
"""

import os
import requests
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """Custom exception for AI client errors."""
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

        if not self.account_id or not self.api_token:
            raise AIClientError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")

        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"

    def generate(self, prompt: str, system: str, max_tokens: int = None) -> str:
        """Generate text using Cloudflare Workers AI with token usage tracking."""
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
            "max_tokens": max_tokens or self.default_max_tokens,
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
            logger.error(f"AI request failed: {e}")
            # Log the full response for debugging
            try:
                error_data = resp.json()
                logger.error(f"Error response: {error_data}")
            except:
                logger.error(f"Error response text: {resp.text}")
            raise AIClientError(str(e)) from e
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            raise AIClientError(str(e)) from e

    def _log_token_usage(self, response_data: dict, system: str, prompt: str) -> None:
        """Log token usage and estimated cost."""
        try:
            # Extract token usage from response
            usage = response_data.get("result", {}).get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            
            # If no usage data, estimate based on character count
            if input_tokens == 0 and output_tokens == 0:
                input_tokens = self._estimate_tokens(system + prompt)
                output_tokens = self._estimate_tokens(response_data.get("result", {}).get("response", ""))
            
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
