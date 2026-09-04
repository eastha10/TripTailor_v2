"""Retrieval interfaces the backend implements to plug in real data.

Nothing in this package knows about Postgres, pgvector, Kakao, Naver or Google.
The backend supplies a :class:`PlaceRetriever`; the AI module supplies the
deterministic filtering and validation around it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from triptailor_ai.schemas.common import AiBaseModel
from triptailor_ai.schemas.place import PlaceCandidate, PlaceKind, TravelTimeEstimate
from triptailor_ai.schemas.preference import NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest


class RetrievalConstraints(AiBaseModel):
    """Deterministically derived filters handed to the retriever.

    These are *metadata* filters -- dates, money, exclusions.  They are never
    resolved by embedding similarity; see ``docs/AI_ARCHITECTURE.md``.
    """

    region_name: str | None = None
    region_id: str | None = None
    #: Most restrictive per-person budget for the whole trip, in KRW.
    budget_cap_per_person: int | None = None
    #: e.g. ``["raw_fish", "contains_peanut"]`` -- from HARD dietary constraints.
    excluded_dietary_tags: list[str] = Field(default_factory=list)
    #: e.g. ``["steep_trail"]`` -- from HARD mobility constraints.
    excluded_accessibility_tags: list[str] = Field(default_factory=list)
    #: Free-text terms for the semantic half of retrieval.
    semantic_terms: list[str] = Field(default_factory=list)
    #: Places the group explicitly asked for.
    must_visit_terms: list[str] = Field(default_factory=list)
    #: Restrict the search to these kinds. ``None`` means "anything".
    #:
    #: Accommodation is requested in its own call: a retriever that ranks by
    #: activity relevance will never surface a hotel, because a hotel does not
    #: match "오름" or "카페" the way an attraction does. Asking for the two
    #: separately is the only way to get both.
    kinds: list[PlaceKind] | None = None
    #: Upper bound on candidates the caller wants back.
    limit: int = 40


@runtime_checkable
class PlaceRetriever(Protocol):
    """Source of real place candidates.

    Implementations MUST NOT invent places.  When a field is unknown they must
    leave it ``None`` and keep ``verification_status`` at ``UNVERIFIED``.
    """

    async def retrieve(
        self,
        request: TripPlanningRequest,
        normalized_preferences: list[NormalizedPreference],
        constraints: RetrievalConstraints,
    ) -> list[PlaceCandidate]:
        ...


@runtime_checkable
class TravelTimeProvider(Protocol):
    """Travel time between places.

    Returning ``minutes=None`` is the correct answer when unknown; the
    validator then emits ``TRAVEL_TIME_UNVERIFIED`` instead of pretending the
    transfer is feasible.
    """

    async def estimate(
        self, pairs: list[tuple[str, str]], places: dict[str, PlaceCandidate]
    ) -> list[TravelTimeEstimate]:
        ...
