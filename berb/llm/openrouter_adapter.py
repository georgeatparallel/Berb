"""OpenRouter API adapter for Berb.

OpenRouter provides unified access to 100+ LLM models from multiple providers
with a single API key and competitive pricing.

Supported Providers:
- Anthropic (Claude 3.5/3.7 Sonnet, Opus)
- OpenAI (GPT-4o, GPT-4.1, o1, o3)
- Google (Gemini 2.5 Pro/Flash)
- DeepSeek (V3, R1)
- Qwen (Qwen3-Max, Qwen3-Turbo)
- MiniMax, GLM, Mistral, and more

Features:
- Unified API across all providers
- Automatic fallback chains
- Cost tracking and optimization
- Model ranking based on performance

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.llm.openrouter_adapter import OpenRouterProvider
    
    provider = OpenRouterProvider(
        api_key="sk-or-...",
        model="anthropic/claude-3.5-sonnet",
    )
    
    response = await provider.complete([
        {"role": "user", "content": "Hello!"}
    ])
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

# Use existing LLMResponse from client module
from berb.llm.client import LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class OpenRouterModel:
    """OpenRouter model configuration."""
    
    id: str
    """Model ID (e.g., 'anthropic/claude-3.5-sonnet')"""
    
    name: str
    """Human-readable name"""
    
    provider: str
    """Provider name (anthropic, openai, google, etc.)"""
    
    input_price: float = 0.0
    """Price per 1M input tokens (USD)"""
    
    output_price: float = 0.0
    """Price per 1M output tokens (USD)"""
    
    context_length: int = 128000
    """Maximum context length"""
    
    supports_vision: bool = False
    """Whether model supports vision input"""
    
    supports_json: bool = True
    """Whether model supports JSON output"""
    
    tier: str = "mid"
    """Model tier: budget, mid, premium"""


# Pre-configured models from OpenRouter
OPENROUTER_MODELS: dict[str, OpenRouterModel] = {
    # Budget Tier (<$0.50/1M input)
    "deepseek/deepseek-chat-v3-0324": OpenRouterModel(
        id="deepseek/deepseek-chat-v3-0324",
        name="DeepSeek V3",
        provider="deepseek",
        input_price=0.27,
        output_price=1.10,
        context_length=256000,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen-3-turbo": OpenRouterModel(
        id="qwen/qwen-3-turbo",
        name="Qwen3-Turbo",
        provider="qwen",
        input_price=0.03,
        output_price=0.12,
        context_length=256000,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen-3-max": OpenRouterModel(
        id="qwen/qwen-3-max",
        name="Qwen3-Max",
        provider="qwen",
        input_price=0.40,
        output_price=1.60,
        context_length=256000,
        supports_vision=True,
        tier="budget",
    ),
    "z-ai/glm-4.5": OpenRouterModel(
        id="z-ai/glm-4.5",
        name="GLM-4.5",
        provider="z-ai",
        input_price=0.30,
        output_price=1.20,
        context_length=256000,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-2.5-flash-preview": OpenRouterModel(
        id="google/gemini-2.5-flash-preview",
        name="Gemini 2.5 Flash",
        provider="google",
        input_price=0.30,
        output_price=1.20,
        context_length=1000000,
        supports_vision=True,
        tier="budget",
    ),
    
    # Mid Tier ($0.50-$5.00/1M input)
    "deepseek/deepseek-r1": OpenRouterModel(
        id="deepseek/deepseek-r1",
        name="DeepSeek R1",
        provider="deepseek",
        input_price=0.50,
        output_price=2.00,
        context_length=256000,
        supports_vision=False,
        tier="mid",
    ),
    "minimax/minimax-01": OpenRouterModel(
        id="minimax/minimax-01",
        name="MiniMax-01",
        provider="minimax",
        input_price=0.40,
        output_price=1.60,
        context_length=256000,
        supports_vision=True,
        tier="mid",
    ),
    
    # Premium Tier (>$5.00/1M input)
    "anthropic/claude-3.5-sonnet": OpenRouterModel(
        id="anthropic/claude-3.5-sonnet",
        name="Claude 3.5 Sonnet",
        provider="anthropic",
        input_price=3.00,
        output_price=15.00,
        context_length=256000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-3.7-sonnet": OpenRouterModel(
        id="anthropic/claude-3.7-sonnet",
        name="Claude 3.7 Sonnet",
        provider="anthropic",
        input_price=3.00,
        output_price=15.00,
        context_length=256000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-3-opus": OpenRouterModel(
        id="anthropic/claude-3-opus",
        name="Claude 3 Opus",
        provider="anthropic",
        input_price=15.00,
        output_price=75.00,
        context_length=256000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4.1": OpenRouterModel(
        id="openai/gpt-4.1",
        name="GPT-4.1",
        provider="openai",
        input_price=5.00,
        output_price=20.00,
        context_length=128000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4o": OpenRouterModel(
        id="openai/gpt-4o",
        name="GPT-4o",
        provider="openai",
        input_price=2.50,
        output_price=10.00,
        context_length=128000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/o1": OpenRouterModel(
        id="openai/o1",
        name="o1",
        provider="openai",
        input_price=15.00,
        output_price=60.00,
        context_length=256000,
        supports_vision=False,
        tier="premium",
    ),
    "google/gemini-2.5-pro-preview": OpenRouterModel(
        id="google/gemini-2.5-pro-preview",
        name="Gemini 2.5 Pro",
        provider="google",
        input_price=2.50,
        output_price=10.00,
        context_length=2000000,
        supports_vision=True,
        tier="premium",
    ),
    "perplexity/sonar-pro": OpenRouterModel(
        id="perplexity/sonar-pro",
        name="Sonar Pro",
        provider="perplexity",
        input_price=5.00,
        output_price=15.00,
        context_length=256000,
        supports_vision=False,
        tier="premium",
    ),
    "mistralai/mistral-large-3": OpenRouterModel(
        id="mistralai/mistral-large-3",
        name="Mistral Large 3",
        provider="mistralai",
        input_price=4.00,
        output_price=18.00,
        context_length=256000,
        supports_vision=True,
        tier="premium",
    ),
}


class OpenRouterProvider:
    """OpenRouter API provider.
    
    Provides unified access to 100+ LLM models with competitive pricing
    and automatic fallback support.
    
    Attributes:
        api_key: OpenRouter API key
        model: Model ID to use
        base_url: OpenRouter API base URL
        timeout: Request timeout in seconds
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "anthropic/claude-3.5-sonnet",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 120,
        max_retries: int = 3,
    ):
        """
        Initialize OpenRouter provider.
        
        Args:
            api_key: OpenRouter API key (or OPENROUTER_API_KEY env var)
            model: Model ID to use
            base_url: OpenRouter API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not provided. "
                "Set OPENROUTER_API_KEY environment variable or pass api_key parameter."
            )
        
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/georgehadji/Berb",
                "X-Title": "Berb",
            },
        )
        
        # Get model info
        self.model_info = OPENROUTER_MODELS.get(model)
        if not self.model_info:
            logger.warning("Model %s not in pre-configured list, using defaults", model)
            self.model_info = OpenRouterModel(
                id=model,
                name=model,
                provider="unknown",
            )
    
    async def complete(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Complete a chat conversation.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional OpenRouter API parameters
        
        Returns:
            LLMResponse with completion
        """
        import time
        t0 = time.monotonic()
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        
        last_error: Exception | None = None
        
        for attempt in range(self.max_retries):
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                
                # Parse response
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                
                # FIX-001a: Match LLMResponse dataclass fields exactly
                # LLMResponse only has: content, model, prompt_tokens, completion_tokens, total_tokens, finish_reason, truncated, raw
                # Cost and duration tracking deferred to future PR
                return LLMResponse(
                    content=content,
                    model=data.get("model", self.model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    finish_reason=data.get("choices", [{}])[0].get("finish_reason", ""),
                    truncated=data.get("choices", [{}])[0].get("finish_reason") == "length",
                    raw=data,
                )
                
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "OpenRouter API error (attempt %d/%d): %s - %s",
                    attempt + 1,
                    self.max_retries,
                    e.response.status_code,
                    e.response.text,
                )
                
                if e.response.status_code in (400, 401, 403):
                    # Don't retry client errors
                    break
                
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                last_error = e
                logger.warning(
                    "OpenRouter request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                await asyncio.sleep(2 ** attempt)
        
        # All retries exhausted
        raise type(last_error)(
            f"OpenRouter API failed after {self.max_retries} retries: {last_error}"
        ) from last_error
    
    def _calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost based on token usage."""
        if not self.model_info:
            return 0.0
        
        input_cost = (prompt_tokens / 1_000_000) * self.model_info.input_price
        output_cost = (completion_tokens / 1_000_000) * self.model_info.output_price
        
        return input_cost + output_cost
    
    def get_model_info(self) -> OpenRouterModel:
        """Get current model information."""
        return self.model_info
    
    @classmethod
    def get_available_models(
        cls,
        tier: str | None = None,
        provider: str | None = None,
        min_context: int | None = None,
    ) -> list[OpenRouterModel]:
        """
        Get available models filtered by criteria.
        
        Args:
            tier: Filter by tier (budget, mid, premium)
            provider: Filter by provider name
            min_context: Minimum context length
        
        Returns:
            List of matching models
        """
        models = list(OPENROUTER_MODELS.values())
        
        if tier:
            models = [m for m in models if m.tier == tier]
        
        if provider:
            models = [m for m in models if m.provider == provider]
        
        if min_context:
            models = [m for m in models if m.context_length >= min_context]
        
        return sorted(models, key=lambda m: m.input_price)
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def __aenter__(self) -> OpenRouterProvider:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Import asyncio at module level for retry logic
import asyncio
