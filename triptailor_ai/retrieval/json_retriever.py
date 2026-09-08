"""Retriever backed by a JSON file of place candidates.

Intended for demos, fixtures and evaluation datasets.  The file contents are
whatever the operator put there -- this class makes no claim that they are
real, current, or verified.
"""

from __future__ import annotations

import json
from pathlib import Path

from triptailor_ai.exceptions import RetrievalError
from triptailor_ai.retrieval.base import RetrievalConstraints
from triptailor_ai.retrieval.in_memory import InMemoryPlaceRetriever
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.preference import NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest


class JsonPlaceRetriever:
    """Loads ``[{PlaceCandidate}, ...]`` or ``{"places": [...]}`` from disk."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._delegate = InMemoryPlaceRetriever(load_places(self.path))

    @property
    def places(self) -> list[PlaceCandidate]:
        return self._delegate.places

    async def retrieve(
        self,
        request: TripPlanningRequest,
        normalized_preferences: list[NormalizedPreference],
        constraints: RetrievalConstraints,
    ) -> list[PlaceCandidate]:
        return await self._delegate.retrieve(request, normalized_preferences, constraints)


def load_places(path: str | Path) -> list[PlaceCandidate]:
    file_path = Path(path)
    if not file_path.exists():
        raise RetrievalError(
            f"place file not found: {file_path}", details={"path": str(file_path)}
        )
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalError(
            f"place file is not valid JSON: {file_path}", details={"cause": str(exc)}
        ) from exc

    raw = payload.get("places", []) if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise RetrievalError(
            "place file must contain a list of places or {'places': [...]}"
        )
    return [PlaceCandidate.model_validate(entry) for entry in raw]
