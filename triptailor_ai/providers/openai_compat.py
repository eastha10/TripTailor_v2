"""Shared implementation for OpenAI-compatible chat endpoints.

Both the hosted OpenAI API and a locally served Qwen (vLLM
``--api-server``) speak the same wire protocol, so they share one adapter.
What differs is *how much* structured-output support we may assume, which is
why :attr:`OpenAICompatibleProvider.structured_method` exists.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from triptailor_ai.exceptions import ConfigurationError
from triptailor_ai.providers.base import (
    ChatMessage,
    ModelProvider,
    PlainText,
    StructuredOutputRejected,
)

StructuredMethod = Literal["function_calling", "json_schema", "json_mode", "prompt"]

_JSON_INSTRUCTION = (
    "반드시 아래 JSON Schema를 만족하는 JSON 객체 **하나만** 출력하세요.\n"
    "코드펜스, 설명, 주석을 붙이지 마세요.\n\nJSON Schema:\n{schema}"
)


def to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    mapping = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
    return [mapping[m.role](content=m.content) for m in messages]


class OpenAICompatibleProvider(ModelProvider):
    """Chat provider backed by ``langchain_openai.ChatOpenAI``."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
        max_retries: int = 2,
        transport_retries: int = 4,
        structured_method: StructuredMethod = "function_calling",
        http_async_client: Any | None = None,
    ) -> None:
        super().__init__(model=model, max_retries=max_retries)
        self.name = name
        self.structured_method: StructuredMethod = structured_method
        self._client = self._build_client(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            transport_retries=transport_retries,
            http_async_client=http_async_client,
        )

    @staticmethod
    def _build_client(
        *,
        model: str,
        api_key: str,
        base_url: str | None,
        timeout: float,
        temperature: float,
        max_output_tokens: int | None,
        transport_retries: int = 4,
        http_async_client: Any | None = None,
    ) -> Any:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ConfigurationError(
                "langchain-openai is required for OpenAI/Qwen providers; "
                'install with: pip install -e ".[dev]"'
            ) from exc

        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": api_key,
            "timeout": timeout,
            "temperature": temperature,
            # The SDK backs off on 429/5xx here; schema correction is a
            # separate loop in ModelProvider. Conflating them means a rate
            # limit gets reported as a malformed answer, or as a dead provider.
            "max_retries": transport_retries,
        }
        if base_url:
            kwargs["base_url"] = base_url
        if max_output_tokens:
            kwargs["max_tokens"] = max_output_tokens
        if http_async_client is not None:
            # Lets a caller supply its own transport (proxy, custom timeouts,
            # or an in-process ASGI transport so the wire path is testable).
            kwargs["http_async_client"] = http_async_client
        return ChatOpenAI(**kwargs)

    async def _complete(
        self,
        *,
        messages: list[ChatMessage],
        schema: type[BaseModel],
        node_name: str,
    ) -> str | BaseModel | dict[str, Any]:
        if schema is PlainText:
            response = await self._client.ainvoke(to_langchain_messages(messages))
            return _content_to_text(response.content)

        if self.structured_method == "prompt":
            return await self._prompted_json(messages, schema)

        try:
            structured = self._client.with_structured_output(
                schema, method=self.structured_method
            )
            return await structured.ainvoke(to_langchain_messages(messages))
        except NotImplementedError:
            # This model/endpoint has no native structured output.
            return await self._prompted_json(messages, schema)
        except ValueError as exc:
            # LangChain's OutputParserException and pydantic's ValidationError
            # are both ValueError subclasses; transport failures
            # (openai.APIError) are not. So this catches "the model answered
            # badly" without swallowing "we could not reach the provider".
            raise StructuredOutputRejected(
                f"native structured output failed schema binding: {exc}"[:500]
            ) from exc

    async def _prompted_json(
        self, messages: list[ChatMessage], schema: type[BaseModel]
    ) -> str:
        """Fallback for servers without native structured output.

        The base class still validates the result against ``schema``, so this
        path is no less safe -- only less efficient.
        """

        instruction = _JSON_INSTRUCTION.format(
            schema=json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
        payload = [*messages, ChatMessage.system(instruction)]
        response = await self._client.ainvoke(to_langchain_messages(payload))
        return _content_to_text(response.content)


def _content_to_text(content: Any) -> str:
    """Flatten LangChain's str | list[dict] content shape into plain text."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts) or json.dumps(content, ensure_ascii=False, default=str)
    return str(content)
