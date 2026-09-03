"""In-memory retriever over a fixed list of candidates.

Used by tests, examples and evaluation.  The scoring is a transparent keyword
overlap -- a stand-in for the vector search a production retriever would run,
not a claim to be one.
"""

from __future__ import annotations

from triptailor_ai.retrieval.base import RetrievalConstraints
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.preference import NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest


class InMemoryPlaceRetriever:
    """Keyword-scored retriever over a pre-loaded candidate list."""

    def __init__(self, places: list[PlaceCandidate]) -> None:
        self._places = list(places)

    @property
    def places(self) -> list[PlaceCandidate]:
        return list(self._places)

    async def retrieve(
        self,
        request: TripPlanningRequest,
        normalized_preferences: list[NormalizedPreference],
        constraints: RetrievalConstraints,
    ) -> list[PlaceCandidate]:
        region = (constraints.region_name or request.region.name or "").strip()
        terms = [t for t in (*constraints.semantic_terms, *constraints.must_visit_terms) if t]

        scored: list[tuple[float, PlaceCandidate]] = []
        for place in self._places:
            if region and place.region and region not in place.region:
                continue
            scored.append((self._score(place, terms), place))

        scored.sort(key=lambda pair: (-pair[0], pair[1].place_id))
        best = max((s for s, _ in scored), default=0.0) or 1.0

        # Return copies. Scoring is per-request, so writing ``confidence`` onto
        # the stored objects would leak one request's ranking into the next and
        # race between concurrent generations.
        return [
            place.model_copy(update={"confidence": round(min(score / best, 1.0), 3)})
            for score, place in scored[: constraints.limit]
        ]

    @staticmethod
    def _score(place: PlaceCandidate, terms: list[str]) -> float:
        haystack = " ".join(
            [
                place.name,
                place.description or "",
                *place.categories,
                *place.tags,
            ]
        ).lower()
        hits = sum(1 for term in terms if term.lower() in haystack)
        # Small tiebreaker so places with verified data sort first.
        bonus = 0.1 if place.opening_hours is not None else 0.0
        return hits + bonus
