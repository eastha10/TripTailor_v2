"""In-process provider used for offline development, CI and evaluation baselines.

It never touches the network.  Two modes, checked in order:

1. **Scripted** -- payloads queued per node via ``script(...)``.  Used to force
   specific failure modes (bad placeId, opening-hour violation, a repair that
   never converges).
2. **Heuristic** -- rule-based logic in
   :mod:`triptailor_ai.providers.fake_logic`, driven by the same labelled
   prompt blocks the real prompts emit.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Callable

from pydantic import BaseModel

from triptailor_ai.prompts.blocks import extract_block
from triptailor_ai.providers.base import ChatMessage, ModelProvider
from triptailor_ai.providers.fake_logic import (
    fake_consensus,
    fake_normalize,
    fake_plan,
    fake_repair,
)
from triptailor_ai.schemas.itinerary import ItineraryDraft
from triptailor_ai.schemas.preference import (
    ConsensusAnalysis,
    NormalizedPreference,
    NormalizedPreferenceSet,
)

Handler = Callable[[list[ChatMessage], type[BaseModel]], Any]


class FakeModelProvider(ModelProvider):
    """Deterministic offline provider."""

    name = "fake"

    def __init__(
        self,
        *,
        model: str = "fake-1",
        max_retries: int = 2,
        scripts: dict[str, list[Any]] | None = None,
        handlers: dict[str, Handler] | None = None,
    ) -> None:
        super().__init__(model=model, max_retries=max_retries)
        self._scripts: dict[str, deque[Any]] = defaultdict(deque)
        for node, payloads in (scripts or {}).items():
            self._scripts[node].extend(payloads)
        self._handlers: dict[str, Handler] = dict(handlers or {})
        #: node -> number of calls, so tests can assert on the repair loop.
        self.call_counts: dict[str, int] = defaultdict(int)
        self.last_messages: dict[str, list[ChatMessage]] = {}

    # ---- scripting API ---------------------------------------------------
    def script(self, node_name: str, *payloads: Any) -> "FakeModelProvider":
        """Queue responses for ``node_name``; consumed one per call."""

        self._scripts[node_name].extend(payloads)
        return self

    def always(self, node_name: str, handler: Handler) -> "FakeModelProvider":
        """Register a per-call handler for ``node_name``."""

        self._handlers[node_name] = handler
        return self

    # ---- provider contract ------------------------------------------------
    async def _complete(
        self,
        *,
        messages: list[ChatMessage],
        schema: type[BaseModel],
        node_name: str,
    ) -> str | BaseModel | dict[str, Any]:
        self.call_counts[node_name] += 1
        self.last_messages[node_name] = list(messages)

        if self._scripts.get(node_name):
            payload = self._scripts[node_name].popleft()
            return payload() if callable(payload) else payload

        handler = self._handlers.get(node_name)
        if handler is not None:
            return handler(messages, schema)

        return self._heuristic(messages, schema, node_name)

    # ---- heuristic dispatch ------------------------------------------------
    def _heuristic(
        self, messages: list[ChatMessage], schema: type[BaseModel], node_name: str
    ) -> BaseModel | str:
        prompt = "\n\n".join(m.content for m in messages)

        if node_name == "normalizer":
            return fake_normalize(extract_block(prompt, "PARTICIPANTS") or [])

        if node_name == "consensus":
            prefs = [
                NormalizedPreference.model_validate(p)
                for p in extract_block(prompt, "PREFERENCES") or []
            ]
            ids = extract_block(prompt, "PARTICIPANT_IDS") or []
            return fake_consensus(prefs, [str(i) for i in ids])

        if node_name == "planner":
            return fake_plan(
                trip=extract_block(prompt, "TRIP") or {},
                candidates=extract_block(prompt, "CANDIDATE_PLACES") or [],
                constraints=extract_block(prompt, "CONSTRAINTS") or {},
                preferences=extract_block(prompt, "PREFERENCES") or [],
                instruction=extract_block(prompt, "INSTRUCTION"),
            )

        if node_name == "repair":
            return fake_repair(
                trip=extract_block(prompt, "TRIP") or {},
                itinerary_items=extract_block(prompt, "ITINERARY") or [],
                issues=extract_block(prompt, "ISSUES") or [],
                candidates=extract_block(prompt, "CANDIDATE_PLACES") or [],
                constraints=extract_block(prompt, "CONSTRAINTS") or {},
            )

        if node_name == "explanation":
            return self._explanation(prompt)

        return self._empty_instance(schema)

    @staticmethod
    def _explanation(prompt: str) -> str:
        items = extract_block(prompt, "ITINERARY") or []
        names = [str(i.get("placeName")) for i in items][:4]
        joined = ", ".join(names) if names else "일정 없음"
        return (
            f"동행자들의 공통 선호를 반영해 {joined} 등을 중심으로 일정을 구성했습니다. "
            "(offline fake explanation)"
        )

    @staticmethod
    def _empty_instance(schema: type[BaseModel]) -> BaseModel | str:
        """Best-effort schema-valid stub for schemas without a heuristic."""

        try:
            return schema()
        except Exception:  # noqa: BLE001 - required fields missing
            return json.dumps({})


def default_fake_provider(**kwargs: Any) -> FakeModelProvider:
    return FakeModelProvider(**kwargs)


__all__ = [
    "ConsensusAnalysis",
    "FakeModelProvider",
    "ItineraryDraft",
    "NormalizedPreferenceSet",
    "default_fake_provider",
]
