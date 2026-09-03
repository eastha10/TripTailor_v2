"""Local Qwen provider, talking to a vLLM OpenAI-compatible server.

The model is **not** loaded in this process.  ``scripts/serve_qwen.sh`` starts
``vllm serve``; this class is a thin client against ``QWEN_BASE_URL``.

vLLM's structured-output support varies by version and by model, so the
default path is prompt-guided JSON plus the shared Pydantic validation retry.
Set ``QWEN_SUPPORTS_JSON_SCHEMA=true`` to use guided decoding instead.
"""

from __future__ import annotations

from triptailor_ai.config.settings import Settings
from triptailor_ai.providers.openai_compat import OpenAICompatibleProvider


class QwenProvider(OpenAICompatibleProvider):
    def __init__(self, *, settings: Settings, model: str | None = None) -> None:
        super().__init__(
            name="qwen",
            model=model or settings.qwen_served_model_name,
            api_key=settings.qwen_api_key or "local",
            base_url=settings.qwen_base_url,
            timeout=settings.qwen_timeout_seconds,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            max_retries=settings.max_llm_retries,
            transport_retries=settings.max_transport_retries,
            structured_method=(
                "json_schema" if settings.qwen_supports_json_schema else "prompt"
            ),
        )
