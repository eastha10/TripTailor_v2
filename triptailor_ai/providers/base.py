"""Provider-neutral structured generation.

Graph nodes only ever see :class:`ModelProvider`.  They do not know whether the
text came from OpenAI, from a local Qwen served by vLLM, or from the fake
in-process provider used in tests.

The schema-validation retry loop lives here, once, so every provider inherits
identical guarantees: whatever comes back has passed Pydantic validation, or a
:class:`StructuredOutputError` was raised.
"""

from __future__ import annotations

import abc
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from triptailor_ai.exceptions import ProviderUnavailableError, StructuredOutputError

T = TypeVar("T", bound=BaseModel)

Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class ChatMessage:
    """A provider-neutral chat message."""

    role: Role
    content: str

    @classmethod
    def system(cls, content: str) -> "ChatMessage":
        return cls("system", content)

    @classmethod
    def user(cls, content: str) -> "ChatMessage":
        return cls("user", content)

    @classmethod
    def assistant(cls, content: str) -> "ChatMessage":
        return cls("assistant", content)


class StructuredOutputRejected(Exception):
    """The model answered, but the answer could not be bound to the schema.

    Distinct from :class:`ProviderUnavailableError`: the provider *worked*, the
    output was simply wrong. Providers raise this so the shared retry loop in
    :meth:`ModelProvider.generate_structured` can correct the model, which is
    what makes ``MAX_LLM_RETRIES`` mean the same thing on every provider --
    including the ones that bind the schema themselves.
    """

    def __init__(self, message: str, *, raw_text: str = "") -> None:
        super().__init__(message)
        self.raw_text = raw_text


@dataclass(slots=True)
class ProviderResponse(Generic[T]):
    """A validated structured result plus the telemetry the graph logs."""

    value: T
    provider: str
    model: str
    latency_ms: int
    retry_count: int = 0
    raw_text: str | None = None
    notes: list[str] = field(default_factory=list)


class ModelProvider(abc.ABC):
    """Base class implementing parse-validate-retry on top of ``_complete``."""

    #: ``"openai"`` / ``"qwen"`` / ``"fake"``.
    name: str = "base"

    def __init__(self, *, model: str, max_retries: int = 2) -> None:
        self.model = model
        self.max_retries = max_retries

    # ---- to be implemented by concrete providers ------------------------
    @abc.abstractmethod
    async def _complete(
        self,
        *,
        messages: list[ChatMessage],
        schema: type[T],
        node_name: str,
    ) -> str | T | dict[str, Any]:
        """Produce one completion.

        May return a already-validated model (native structured output), a
        dict, or raw text -- the base class normalises all three.
        """

    # ---- public API ------------------------------------------------------
    async def generate_structured(
        self,
        *,
        messages: list[ChatMessage],
        schema: type[T],
        node_name: str,
    ) -> ProviderResponse[T]:
        """Return schema-valid output or raise :class:`StructuredOutputError`."""

        conversation = list(messages)
        started = time.perf_counter()
        last_error: str | None = None
        last_text: str | None = None

        for attempt in range(self.max_retries + 1):
            try:
                raw = await self._invoke(conversation, schema, node_name)
                value = self._coerce(raw, schema)
            except StructuredOutputRejected as exc:
                # The provider bound the schema itself and the model failed it.
                last_error = str(exc)[:300]
                last_text = exc.raw_text
                if attempt == self.max_retries:
                    break
                conversation = [*conversation, *_repair_turn(last_text, last_error, schema)]
                continue
            except (PydanticValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = _short_error(exc)
                last_text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
                if attempt == self.max_retries:
                    break
                conversation = [*conversation, *_repair_turn(last_text, last_error, schema)]
                continue

            return ProviderResponse(
                value=value,
                provider=self.name,
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                retry_count=attempt,
                raw_text=raw if isinstance(raw, str) else None,
            )

        raise StructuredOutputError(
            f"{self.name}:{self.model} failed to produce valid {schema.__name__} for "
            f"node '{node_name}' after {self.max_retries + 1} attempts",
            details={
                "node": node_name,
                "schema": schema.__name__,
                "lastError": last_error,
                "attempts": self.max_retries + 1,
            },
        )

    async def generate_text(
        self,
        *,
        messages: list[ChatMessage],
        node_name: str,
    ) -> ProviderResponse[Any]:
        """Free-text generation (used only by the explanation node)."""

        started = time.perf_counter()
        raw = await self._invoke(list(messages), PlainText, node_name)
        text = raw if isinstance(raw, str) else str(raw)
        return ProviderResponse(
            value=PlainText(text=text),
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw_text=text,
        )

    async def aclose(self) -> None:  # pragma: no cover - overridden where needed
        """Release provider resources.  No-op by default."""

    # ---- internals -------------------------------------------------------
    async def _invoke(
        self,
        conversation: list[ChatMessage],
        schema: type[T],
        node_name: str,
    ) -> str | T | dict[str, Any]:
        try:
            return await self._complete(
                messages=conversation, schema=schema, node_name=node_name
            )
        except (ProviderUnavailableError, StructuredOutputRejected):
            # Both are already meaningful; wrapping them would lose that.
            raise
        except Exception as exc:  # noqa: BLE001 - deliberately wrapping
            raise ProviderUnavailableError(
                f"{self.name} provider call failed for node '{node_name}'",
                details={
                    "node": node_name,
                    "provider": self.name,
                    "model": self.model,
                    # Type + message only: never the raw object, never headers.
                    "cause": f"{type(exc).__name__}: {exc}"[:500],
                },
            ) from exc

    @staticmethod
    def _coerce(raw: str | T | dict[str, Any], schema: type[T]) -> T:
        if isinstance(raw, schema):
            return raw
        if isinstance(raw, BaseModel):
            return schema.model_validate(raw.model_dump())
        if isinstance(raw, dict):
            return schema.model_validate(raw)
        payload = extract_json(str(raw))
        return schema.model_validate(payload)


class PlainText(BaseModel):
    """Envelope for free-text generation (no schema constraint)."""

    text: str = ""


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model response.

    Handles bare JSON, ```json fences, and prose wrapped around the payload.
    Never uses ``eval``.
    """

    stripped = text.strip()
    if not stripped:
        raise ValueError("empty model response")

    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    span = _find_balanced_span(stripped)
    if span is None:
        raise ValueError("no JSON object or array found in model response")
    return json.loads(stripped[span[0] : span[1]])


def _find_balanced_span(text: str) -> tuple[int, int] | None:
    """Locate the outermost balanced ``{...}`` / ``[...]`` region."""

    openers = {"{": "}", "[": "]"}
    start = next((i for i, ch in enumerate(text) if ch in openers), None)
    if start is None:
        return None

    opener = text[start]
    closer = openers[opener]
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return start, index + 1
    return None


def _repair_turn(
    raw_text: str, error: str, schema: type[BaseModel]
) -> list[ChatMessage]:
    """Build the corrective turn appended before a structured-output retry."""

    turns: list[ChatMessage] = []
    if raw_text.strip():
        # Only echo the bad answer back when we actually captured it; a
        # provider that bound the schema internally may not expose the text.
        turns.append(ChatMessage.assistant(raw_text[:4000]))
    turns.append(
        ChatMessage.user(
            "이전 응답이 요구된 JSON 스키마를 만족하지 않았습니다.\n"
            f"검증 오류: {error}\n\n"
            f"아래 스키마를 정확히 따르는 JSON 객체 **하나만** 다시 출력하세요. "
            "설명, 주석, 코드펜스 없이 JSON만 출력합니다.\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)[:6000]
        )
    )
    return turns


def _short_error(exc: Exception) -> str:
    if isinstance(exc, PydanticValidationError):
        parts = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()[:5]
        ]
        return "; ".join(parts)
    return f"{type(exc).__name__}: {exc}"[:300]
