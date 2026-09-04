"""LangGraph state.

An explicit ``TypedDict`` rather than a loose ``dict``: every node declares
what it reads and writes, and mypy/IDE completion works across the graph.

Runtime dependencies (model router, retriever, validator) are **not** in the
state -- they are bound into the node closures by
:mod:`triptailor_ai.graph.builder`, which keeps the state pure data and
serialisable.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from triptailor_ai.retrieval.base import RetrievalConstraints
from triptailor_ai.schemas.generation import GenerationMetadata, GenerationStatus, NodeTrace
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.place import PlaceCandidate, TravelTimeEstimate
from triptailor_ai.schemas.preference import (
    CommonPreference,
    Conflict,
    GroupBudget,
    NormalizedPreference,
)
from triptailor_ai.schemas.trip import ParticipantInput, TripPlanningRequest
from triptailor_ai.schemas.validation import ValidationIssue, ValidationResult


def append_traces(left: list[NodeTrace], right: list[NodeTrace]) -> list[NodeTrace]:
    """Reducer: node traces accumulate instead of overwriting."""

    return [*left, *right]


class PlanningState(TypedDict, total=False):
    """Shared state for one generation run."""

    # identity
    trip_id: str
    generation_id: str
    request: TripPlanningRequest

    # preferences
    raw_preferences: list[ParticipantInput]
    normalized_preferences: list[NormalizedPreference]
    common_preferences: list[CommonPreference]
    individual_preferences: list[NormalizedPreference]
    hard_constraints: list[NormalizedPreference]
    soft_preferences: list[NormalizedPreference]
    conflicts: list[Conflict]
    consensus_summary: str | None
    group_budget: GroupBudget

    # retrieval
    retrieval_constraints: RetrievalConstraints | None
    candidate_places: list[PlaceCandidate]
    travel_times: list[TravelTimeEstimate]

    # planning
    itinerary_draft: Itinerary | None
    explanation: str | None

    # validation
    validation_result: ValidationResult | None
    validation_errors: list[ValidationIssue]
    validation_warnings: list[ValidationIssue]

    # control
    #: What the deterministic repair pass changed, for the reviewer.
    repair_changes: list[str]
    #: Business-level repair attempts consumed. Never the LLM network retries.
    retry_count: int
    max_repair_attempts: int
    status: GenerationStatus
    unresolved_issues: list[str]
    error: str | None

    # revision
    revision_instruction: str | None
    revision_target_days: list[int]

    # telemetry
    node_traces: Annotated[list[NodeTrace], append_traces]
    generation_metadata: GenerationMetadata
    provider_map: dict[str, str]


def initial_state(
    *,
    request: TripPlanningRequest,
    generation_id: str,
    max_repair_attempts: int,
) -> PlanningState:
    return PlanningState(
        trip_id=request.trip_id,
        generation_id=generation_id,
        request=request,
        raw_preferences=list(request.participants),
        normalized_preferences=[],
        common_preferences=[],
        individual_preferences=[],
        hard_constraints=[],
        soft_preferences=[],
        conflicts=[],
        consensus_summary=None,
        group_budget=GroupBudget(),
        retrieval_constraints=None,
        candidate_places=[],
        travel_times=[],
        itinerary_draft=None,
        explanation=None,
        validation_result=None,
        validation_errors=[],
        validation_warnings=[],
        repair_changes=[],
        retry_count=0,
        max_repair_attempts=max_repair_attempts,
        status=GenerationStatus.PENDING,
        unresolved_issues=[],
        error=None,
        revision_instruction=None,
        revision_target_days=[],
        node_traces=[],
        provider_map={},
    )


def state_summary(state: PlanningState) -> dict[str, Any]:
    """Compact, PII-free view of the state for logs."""

    return {
        "tripId": state.get("trip_id"),
        "generationId": state.get("generation_id"),
        "status": getattr(state.get("status"), "value", state.get("status")),
        "preferenceCount": len(state.get("normalized_preferences") or []),
        "candidateCount": len(state.get("candidate_places") or []),
        "itemCount": len((state.get("itinerary_draft") or Itinerary()).all_items()),
        "errorCount": len(state.get("validation_errors") or []),
        "warningCount": len(state.get("validation_warnings") or []),
        "retryCount": state.get("retry_count", 0),
    }
