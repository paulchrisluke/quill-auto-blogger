"""
Thin Cloudflare Workers AI client for M5 surgical AI inserts.
"""

import os
import json
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """Custom exception for AI client errors."""
    pass


class CloudflareAIClient:
    """Thin client for Cloudflare Workers AI."""
    
    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.model = os.getenv("CLOUDFLARE_AI_MODEL", "openai/llama-3.1-8b-instruct")
        self.timeout_ms = int(os.getenv("AI_TIMEOUT_MS", "6000"))
        self.seed = int(os.getenv("AI_SEED", "42"))
        self.default_max_tokens = int(os.getenv("AI_MAX_TOKENS", "800"))
        
        if not self.account_id or not self.api_token:
            raise AIClientError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")
        
        # Use standard Cloudflare Workers AI API (same as transcription service)
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
    
    def generate(
        self, 
        prompt: str, 
        system: str, 
        max_tokens: int = None
    ) -> str:
        """
        Generate text using Cloudflare Workers AI.
        
        Args:
            prompt: User prompt
            system: System instruction
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text string
            
        Raises:
            AIClientError: On API errors or timeouts
        """
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        # Use provided max_tokens or default from environment
        if max_tokens is None:
            max_tokens = self.default_max_tokens
            
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "top_p": 0.9,
            "seed": self.seed
        }
        
        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout_ms / 1000.0  # Convert to seconds
            )
            
            if response.status_code != 200:
                raise AIClientError(f"API request failed with status {response.status_code}: {response.text}")
            
            # Safely parse JSON response
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}. Raw response: {response.text}")
                raise AIClientError("Invalid JSON response from API")
            
            # Check for API success indicators
            if data.get("success") is False:
                error_msg = data.get("errors", "Unknown API error")
                logger.error(f"API returned unsuccessful response: {error_msg}. Full response: {data}")
                raise AIClientError("API returned unsuccessful response")
            
            # Check for expected response structure
            if "result" not in data or "response" not in data["result"]:
                logger.error(f"Unexpected API response format. Full response: {data}")
                raise AIClientError("Unexpected API response format")
            
            return data["result"]["response"]
            
        except requests.exceptions.Timeout:
            raise AIClientError(f"Request timed out after {self.timeout_ms}ms")
        except requests.exceptions.RequestException as e:
            raise AIClientError(f"Request failed: {e}") from e
        except (KeyError, ValueError) as e:
            raise AIClientError(f"Failed to parse response: {e}") from e
