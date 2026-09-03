"""Shared node plumbing: tracing, constraint payloads, itinerary assembly."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.logging_utils import log_event
from triptailor_ai.prompts import PROMPT_VERSIONS, Pseudonymizer
from triptailor_ai.retrieval.base import RetrievalConstraints
from triptailor_ai.schemas.generation import NodeTrace
from triptailor_ai.schemas.itinerary import Itinerary, ItineraryDay, ItineraryDraft, ItineraryItem
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.trip import TripPlanningRequest


class TraceCollector:
    """Builds one :class:`NodeTrace` per node execution."""

    def __init__(self, node: str) -> None:
        self.trace = NodeTrace(node=node, prompt_version=PROMPT_VERSIONS.get(node))
        self._started = time.perf_counter()

    def record_provider(self, provider: str, model: str, retry_count: int = 0) -> None:
        self.trace.provider = provider
        self.trace.model = model
        self.trace.llm_retry_count = retry_count

    def finish(self, *, ok: bool = True, error: str | None = None) -> NodeTrace:
        self.trace.latency_ms = int((time.perf_counter() - self._started) * 1000)
        self.trace.ok = ok
        self.trace.error = error
        return self.trace


@contextmanager
def node_trace(node: str, state: PlanningState) -> Iterator[TraceCollector]:
    collector = TraceCollector(node)
    log_event(
        "node.start",
        level=logging.DEBUG,
        node=node,
        generationId=state.get("generation_id"),
        tripId=state.get("trip_id"),
    )
    try:
        yield collector
    finally:
        log_event(
            "node.end",
            level=logging.DEBUG,
            node=node,
            generationId=state.get("generation_id"),
            tripId=state.get("trip_id"),
            latencyMs=collector.trace.latency_ms,
            provider=collector.trace.provider,
            model=collector.trace.model,
            promptVersion=collector.trace.prompt_version,
            llmRetryCount=collector.trace.llm_retry_count,
            ok=collector.trace.ok,
        )


def pseudonymizer_for(state: PlanningState, settings) -> Pseudonymizer:  # noqa: ANN001
    return Pseudonymizer.for_request(
        state["request"], enabled=settings.pseudonymize_participants
    )


def constraints_payload(state: PlanningState) -> dict[str, Any]:
    """The deterministic constraint block shared by planner and repair prompts."""

    constraints: RetrievalConstraints | None = state.get("retrieval_constraints")
    budget = state.get("group_budget")
    return {
        "budgetCapPerPerson": budget.per_person_cap_krw if budget else None,
        "limitingParticipantIds": budget.limiting_participant_ids if budget else [],
        "excludedDietaryTags": constraints.excluded_dietary_tags if constraints else [],
        "excludedAccessibilityTags": (
            constraints.excluded_accessibility_tags if constraints else []
        ),
        "mustVisitTerms": constraints.must_visit_terms if constraints else [],
        "hardConstraints": [
            p.model_dump(by_alias=True, mode="json")
            for p in state.get("hard_constraints") or []
        ],
    }


def build_itinerary(
    draft: ItineraryDraft,
    request: TripPlanningRequest,
    candidates: list[PlaceCandidate],
) -> Itinerary:
    """Turn a flat draft into a day-grouped itinerary.

    Structural hygiene only -- de-duplicating ids, sorting, recomputing cost
    roll-ups.  Constraint violations are left intact for the validator to
    report; silently "fixing" them here would hide model failures.
    """

    by_place = {place.place_id: place for place in candidates}
    seen_ids: set[str] = set()
    items: list[ItineraryItem] = []

    for index, item in enumerate(sorted(draft.items, key=lambda i: (i.day, i.start_time)), 1):
        item_id = item.item_id or f"item-{index}"
        while item_id in seen_ids:
            item_id = f"{item_id}-{index}"
        seen_ids.add(item_id)

        place = by_place.get(item.place_id)
        items.append(
            item.model_copy(
                update={
                    "item_id": item_id,
                    "sequence": index,
                    # Backfill only from grounded candidate data, never invented.
                    "image_url": item.image_url or (place.image_url if place else None),
                    "source_ids": item.source_ids or (place.source_ids if place else []),
                }
            )
        )

    by_day: dict[int, list[ItineraryItem]] = {}
    for item in items:
        by_day.setdefault(item.day, []).append(item)

    days = [
        ItineraryDay(
            day=day,
            date=entries[0].date,
            items=entries,
            title=draft.day_titles.get(day),
        )
        for day, entries in sorted(by_day.items())
    ]

    itinerary = Itinerary(days=days, unmet_preferences=list(draft.unmet_preferences))
    itinerary.recompute_costs(len(request.participants))
    return itinerary


def consecutive_place_pairs(itinerary: Itinerary) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for day in itinerary.days:
        ordered = sorted(day.items, key=lambda i: (i.start_time, i.sequence))
        pairs.extend(
            (previous.place_id, current.place_id)
            for previous, current in zip(ordered, ordered[1:])
        )
    return list(dict.fromkeys(pairs))
