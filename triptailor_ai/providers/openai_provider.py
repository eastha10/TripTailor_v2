"""Hosted OpenAI provider.

The model name is never hard-coded in logic: it comes from ``OPENAI_MODEL`` or
a per-node override.  The API key is read from settings and never logged.
"""

from __future__ import annotations

from triptailor_ai.config.settings import Settings
from triptailor_ai.providers.openai_compat import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, *, settings: Settings, model: str | None = None) -> None:
        super().__init__(
            name="openai",
            model=model or settings.openai_model,
            api_key=settings.require_openai_key(),
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout_seconds,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            max_retries=settings.max_llm_retries,
            transport_retries=settings.max_transport_retries,
            structured_method=settings.openai_structured_method,
        )
