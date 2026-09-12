import os
from typing import Any, Optional, Type
import json

from pydantic import BaseModel
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential
from openai import AsyncOpenAI
import httpx

logger = structlog.get_logger(__name__)

RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    Exception
)

class LLMOrchestrator:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_NIM_KEY_DEEPSEEK", "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")
        )

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_random_exponential(multiplier=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _dispatch_call(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model="deepseek-ai/deepseek-v4-pro-0813",
            messages=[
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
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    async def extract_with_fallback(
        self, prompt: str, target_schema: Type[BaseModel]
    ) -> tuple[BaseModel, str]:
        try:
            raw_json = await self._dispatch_call(prompt)
            validated = target_schema.model_validate_json(raw_json)
            return validated, "deepseek-v4-pro-0813"
        except Exception as exc:
            logger.warning(
                "llm_extraction_failed",
                model="deepseek-v4-pro-0813",
                error=str(exc),
            )
            raise RuntimeError(f"Extraction failed: {exc}")
