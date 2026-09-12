import os
from typing import Any, Optional, Type
from litellm import acompletion
from litellm.exceptions import (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from pydantic import BaseModel
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

logger = structlog.get_logger(__name__)

NIM_BASE = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

RETRYABLE_EXCEPTIONS = (
    RateLimitError,
    Timeout,
    APIConnectionError,
    ServiceUnavailableError,
)

TIERS = [
    {
        "name": "tier1_gemini",
        "model": "gemini/gemini-1.5-flash",
        "api_key": os.getenv("GEMINI_API_KEY"),
        "api_base": None,
    },
    {
        "name": "tier2_nemotron_nim",
        "model": "openai/nvidia/nemotron-3.5-lightning-30b-a3b",
        "api_key": os.getenv("NVIDIA_NIM_KEY_NEMOTRON"),
        "api_base": NIM_BASE,
    },
    {
        "name": "tier3_gemma_nim",
        "model": "openai/google/gemma-4-31b-it",
        "api_key": os.getenv("NVIDIA_NIM_KEY_GEMMA"),
        "api_base": NIM_BASE,
    },
    {
        "name": "tier4_kimi_nim",
        "model": "openai/moonshotai/kimi-k3",
        "api_key": os.getenv("NVIDIA_NIM_KEY_KIMI"),
        "api_base": NIM_BASE,
    },
]

class LLMOrchestrator:
    @staticmethod
    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_random_exponential(multiplier=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _dispatch_call(tier: dict, prompt: str) -> str:
        kwargs: dict[str, Any] = {
            "model": tier["model"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict entity canonicalization system. "
                        "Respond with ONLY a raw JSON object matching the requested schema. "
                        "Do not include Markdown formatting, code blocks, or explanatory commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }
        if tier["api_base"]:
            kwargs["api_base"] = tier["api_base"]
        if tier["api_key"]:
            kwargs["api_key"] = tier["api_key"]

        response = await acompletion(**kwargs)
        return response.choices[0].message.content

    async def extract_with_fallback(
        self, prompt: str, target_schema: Type[BaseModel]
    ) -> tuple[BaseModel, str]:
        last_error: Optional[Exception] = None
        for tier in TIERS:
            if not tier["api_key"]:
                continue
            try:
                raw_json = await self._dispatch_call(tier, prompt)
                validated = target_schema.model_validate_json(raw_json)
                return validated, tier["name"]
            except Exception as exc:
                logger.warning(
                    "tier_dispatch_failed_falling_over",
                    tier=tier["name"],
                    model=tier["model"],
                    error=str(exc),
                )
                last_error = exc
                continue
        raise RuntimeError(f"All fallback tiers exhausted. Final error: {last_error}")
