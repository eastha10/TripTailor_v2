"""Deterministic layer around whatever ``PlaceRetriever`` the backend injects.

Responsibilities kept *out* of the retriever and *out* of the LLM:

* deriving the retrieval constraints from normalized preferences,
* post-filtering on hard constraints the retriever may have ignored,
* de-duplicating and capping the candidate set,
* collecting travel-time estimates for the pairs the plan actually uses.
"""

from __future__ import annotations

from triptailor_ai.exceptions import NoViableCandidatesError, RetrievalError
from triptailor_ai.retrieval.base import (
    PlaceRetriever,
    RetrievalConstraints,
    TravelTimeProvider,
)
from triptailor_ai.retrieval.travel_time import NullTravelTimeProvider
from triptailor_ai.schemas.place import PlaceCandidate, TravelTimeEstimate
from triptailor_ai.schemas.preference import (
    ConstraintType,
    GroupBudget,
    NormalizedPreference,
    PreferenceCategory,
)
from triptailor_ai.schemas.trip import TripPlanningRequest

#: Free-text marker -> the place tags it rules out.
#:
#: One marker can exclude several tags: "비건" rules out far more than a tag
#: literally named ``vegan``, and a place tagged ``pork`` is just as much a
#: problem as one tagged ``meat``.
DIETARY_TAG_HINTS: dict[str, tuple[str, ...]] = {
    "회": ("raw_fish",),
    "생선회": ("raw_fish",),
    "날생선": ("raw_fish",),
    "사시미": ("raw_fish",),
    "해산물": ("seafood", "raw_fish"),
    "조개": ("seafood",),
    "새우": ("seafood",),
    "갑각류": ("seafood",),
    "생선": ("seafood", "raw_fish"),
    "땅콩": ("peanut", "nuts"),
    "견과": ("nuts", "peanut"),
    "유제품": ("dairy",),
    "우유": ("dairy",),
    "치즈": ("dairy",),
    "계란": ("egg",),
    "달걀": ("egg",),
    "돼지": ("pork", "meat"),
    "소고기": ("beef", "meat"),
    "고기": ("meat", "pork", "beef"),
    "육류": ("meat", "pork", "beef"),
    "채식": ("meat", "pork", "beef", "seafood", "raw_fish"),
    "비건": ("meat", "pork", "beef", "seafood", "raw_fish", "dairy", "egg"),
    "vegan": ("meat", "pork", "beef", "seafood", "raw_fish", "dairy", "egg"),
    "vegetarian": ("meat", "pork", "beef", "seafood", "raw_fish"),
    "밀가루": ("gluten",),
    "글루텐": ("gluten",),
    "매운": ("spicy",),
}

#: Free-text markers -> accessibility tags to exclude on a HARD mobility limit.
MOBILITY_EXCLUSION_TAGS: tuple[str, ...] = (
    "steep_trail",
    "long_walk",
    "many_stairs",
    "hiking_required",
    "no_elevator",
)


class RetrievalService:
    """Turns preferences into candidates, deterministically filtered."""

    def __init__(
        self,
        retriever: PlaceRetriever,
        *,
        travel_time_provider: TravelTimeProvider | None = None,
        max_candidates: int = 40,
    ) -> None:
        self.retriever = retriever
        self.travel_time_provider: TravelTimeProvider = (
            travel_time_provider or NullTravelTimeProvider()
        )
        self.max_candidates = max_candidates

    # ---- constraint derivation ------------------------------------------
    @staticmethod
    def derive_group_budget(request: TripPlanningRequest) -> GroupBudget:
        """Group cap = the most restrictive participant's upper bound.

        Planning above the lowest band would put a participant over budget, so
        the minimum is the only defensible group-level hard cap.
        """

        bands = [
            (p.participant_id, p.budget_band)
            for p in request.participants
            if p.budget_band is not None
        ]
        if not bands:
            return GroupBudget()
        caps = {pid: band.upper_bound_krw for pid, band in bands}
        lowest = min(caps.values())
        return GroupBudget(
            per_person_cap_krw=lowest,
            limiting_participant_ids=sorted(p for p, c in caps.items() if c == lowest),
            has_band_mismatch=len({band for _, band in bands}) > 1,
        )

    @staticmethod
    def derive_constraints(
        request: TripPlanningRequest,
        preferences: list[NormalizedPreference],
        *,
        limit: int = 40,
    ) -> RetrievalConstraints:
        budget = RetrievalService.derive_group_budget(request)

        excluded_dietary: list[str] = []
        excluded_accessibility: list[str] = []
        semantic_terms: list[str] = []
        must_visit: list[str] = []

        for pref in preferences:
            if pref.category is PreferenceCategory.AVAILABILITY:
                continue
            if pref.constraint_type is ConstraintType.HARD:
                if pref.category is PreferenceCategory.DIETARY:
                    excluded_dietary.extend(dietary_tags_from(pref.source_text))
                elif pref.category is PreferenceCategory.MOBILITY:
                    excluded_accessibility.extend(MOBILITY_EXCLUSION_TAGS)
            if pref.category is PreferenceCategory.MUST_VISIT:
                must_visit.append(pref.value)
            semantic_terms.extend(pref.tags)
            if pref.category in (
                PreferenceCategory.ACTIVITY,
                PreferenceCategory.FOOD,
                PreferenceCategory.ATMOSPHERE,
                PreferenceCategory.MUST_VISIT,
            ):
                semantic_terms.append(pref.value)

        return RetrievalConstraints(
            region_name=request.region.name,
            region_id=request.region.region_id,
            budget_cap_per_person=budget.per_person_cap_krw,
            excluded_dietary_tags=sorted(set(excluded_dietary)),
            excluded_accessibility_tags=sorted(set(excluded_accessibility)),
            semantic_terms=list(dict.fromkeys(t for t in semantic_terms if t))[:40],
            must_visit_terms=list(dict.fromkeys(must_visit))[:10],
            limit=limit,
        )

    # ---- retrieval --------------------------------------------------------
    async def retrieve(
        self,
        request: TripPlanningRequest,
        preferences: list[NormalizedPreference],
        constraints: RetrievalConstraints | None = None,
    ) -> tuple[list[PlaceCandidate], RetrievalConstraints]:
        resolved = constraints or self.derive_constraints(
            request, preferences, limit=self.max_candidates
        )
        try:
            candidates = await self.retriever.retrieve(request, preferences, resolved)
        except RetrievalError:
            raise
        except Exception as exc:  # noqa: BLE001 - wrap third-party retrievers
            raise RetrievalError(
                "place retriever failed",
                details={"cause": f"{type(exc).__name__}: {exc}"[:300]},
            ) from exc

        filtered = self.apply_hard_filters(candidates, resolved)
        if not filtered:
            reason = (
                "hard-constraint filtering removed every candidate"
                if candidates
                else "the retriever returned no places for this region"
            )
            raise NoViableCandidatesError(
                f"no usable place candidates: {reason}",
                details={
                    "retrieved": len(candidates),
                    "reason": reason,
                    "excludedDietaryTags": resolved.excluded_dietary_tags,
                    "excludedAccessibilityTags": resolved.excluded_accessibility_tags,
                },
            )
        return filtered[: self.max_candidates], resolved

    @staticmethod
    def apply_hard_filters(
        candidates: list[PlaceCandidate], constraints: RetrievalConstraints
    ) -> list[PlaceCandidate]:
        """Drop candidates that violate a hard constraint; de-duplicate by id.

        Applied even when the retriever claims to have filtered already: the
        AI module must not depend on an injected implementation being correct.
        """

        banned_dietary = {t.lower() for t in constraints.excluded_dietary_tags}
        banned_access = {t.lower() for t in constraints.excluded_accessibility_tags}

        seen: set[str] = set()
        kept: list[PlaceCandidate] = []
        for place in candidates:
            if place.place_id in seen:
                continue
            seen.add(place.place_id)
            if {t.lower() for t in place.dietary_tags} & banned_dietary:
                continue
            if {t.lower() for t in place.accessibility} & banned_access:
                continue
            kept.append(place)
        return kept

    # ---- travel times ------------------------------------------------------
    async def travel_times(
        self, pairs: list[tuple[str, str]], places: dict[str, PlaceCandidate]
    ) -> list[TravelTimeEstimate]:
        if not pairs:
            return []
        return await self.travel_time_provider.estimate(pairs, places)


def dietary_tags_from(text: str) -> list[str]:
    """Place tags ruled out by one free-text dietary statement."""

    lowered = text.lower()
    excluded: list[str] = []
    for marker, tags in DIETARY_TAG_HINTS.items():
        if marker.lower() in lowered:
            excluded.extend(tags)
    return sorted(set(excluded))
