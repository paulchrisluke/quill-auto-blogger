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
        self.timeout = int(os.getenv("AI_TIMEOUT_MS", "15000")) / 1000.0  # seconds
        self.seed = int(os.getenv("AI_SEED", "42"))
        self.default_max_tokens = int(os.getenv("AI_MAX_TOKENS", "800"))

        if not self.account_id or not self.api_token:
            raise AIClientError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")

        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"

    def generate(self, prompt: str, system: str, max_tokens: int = None) -> str:
        """Generate text using Cloudflare Workers AI."""
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
            return data["result"]["response"]
        except requests.exceptions.Timeout:
            raise AIClientError(f"Request timed out after {self.timeout}s")
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            raise AIClientError(str(e)) from e
