"""Optional in-process state store for revisions.

The recommended integration is **stateless**: the backend persists the
:class:`TripPlanningResult` it received and passes it back to ``revise()``.
This store exists so a single-process deployment (or the FastAPI adapter) can
revise using only a ``generationId``.  It is not a database and does not
survive a restart.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Protocol, runtime_checkable

from triptailor_ai.graph.state import PlanningState


@runtime_checkable
class GenerationStateStore(Protocol):
    """Persistence seam for graph state between generate and revise."""

    def save(self, generation_id: str, state: PlanningState) -> None: ...

    def load(self, generation_id: str) -> PlanningState | None: ...


class InMemoryGenerationStore:
    """Bounded LRU store.  Oldest generations are evicted, never unbounded."""

    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self._entries: OrderedDict[str, PlanningState] = OrderedDict()

    def save(self, generation_id: str, state: PlanningState) -> None:
        self._entries[generation_id] = state
        self._entries.move_to_end(generation_id)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def load(self, generation_id: str) -> PlanningState | None:
        state = self._entries.get(generation_id)
        if state is not None:
            self._entries.move_to_end(generation_id)
        return state

    def __len__(self) -> int:
        return len(self._entries)


class NullGenerationStore:
    """Stores nothing.  Use when the backend always passes the previous result."""

    def save(self, generation_id: str, state: PlanningState) -> None:
        return None

    def load(self, generation_id: str) -> PlanningState | None:
        return None
