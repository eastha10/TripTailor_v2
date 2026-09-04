"""Generation lifecycle + the result envelope returned to the backend."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import Field

from triptailor_ai.schemas.common import AiBaseModel
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.preference import (
    CommonPreference,
    Conflict,
    NormalizedPreference,
)
from triptailor_ai.schemas.trip import TripPlanningRequest
from triptailor_ai.schemas.validation import ValidationResult


class GenerationStatus(str, Enum):
    """Status of one AI generation run.

    Intentionally *separate* from
    :class:`~triptailor_ai.schemas.trip.TripStatus`: a trip stays ``PLANNING``
    across many generation attempts.
    """

    PENDING = "PENDING"
    NORMALIZING = "NORMALIZING"
    ANALYZING = "ANALYZING"
    RETRIEVING = "RETRIEVING"
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    NEEDS_INPUT = "NEEDS_INPUT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES = {
    GenerationStatus.NEEDS_INPUT,
    GenerationStatus.NEEDS_REVIEW,
    GenerationStatus.APPROVED,
    GenerationStatus.FAILED,
}


class NodeTrace(AiBaseModel):
    """Per-node execution record, for logging and model comparison."""

    node: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = None
    llm_retry_count: int = 0
    ok: bool = True
    error: str | None = None


class GenerationMetadata(AiBaseModel):
    generation_id: str
    trip_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    #: Business-level repair loops consumed (distinct from LLM network retries).
    repair_attempts: int = 0
    max_repair_attempts: int = 0
    total_llm_retries: int = 0
    validation_error_count: int = 0
    validation_warning_count: int = 0
    candidate_place_count: int = 0
    node_traces: list[NodeTrace] = Field(default_factory=list)
    #: node -> "provider:model", so an evaluation run can be attributed.
    provider_map: dict[str, str] = Field(default_factory=dict)
    #: Set when the run was produced by ``revise()``.
    revision_of: str | None = None
    revision_instruction: str | None = None

    @property
    def latency_ms(self) -> int | None:
        if self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class PreferenceSummary(AiBaseModel):
    """What ``GET /preference-summary`` should surface to the group."""

    common_preferences: list[CommonPreference] = Field(default_factory=list)
    hard_constraints: list[NormalizedPreference] = Field(default_factory=list)
    soft_preferences: list[NormalizedPreference] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    summary: str | None = None


class TripPlanningResult(AiBaseModel):
    """Everything the backend needs to persist and render one generation."""

    generation_id: str
    trip_id: str
    status: GenerationStatus
    itinerary: Itinerary | None = None
    validation: ValidationResult = Field(default_factory=ValidationResult)
    preference_summary: PreferenceSummary = Field(default_factory=PreferenceSummary)
    #: Candidates the plan drew from -- kept so ``revise()`` can skip retrieval.
    candidate_places: list[PlaceCandidate] = Field(default_factory=list)
    normalized_preferences: list[NormalizedPreference] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    metadata: GenerationMetadata
    #: The originating request, echoed back so a stateless backend can call
    #: ``revise()`` with nothing but the persisted result.
    request: TripPlanningRequest | None = None
    #: What the deterministic repair pass changed, in plain Korean. Safe to
    #: show a reviewer verbatim: "'X' 중복 -> 'Y'으로 교체".
    repair_changes: list[str] = Field(default_factory=list)
    #: Set only when ``status is FAILED``; safe, provider-neutral text.
    #: Displayable: it never contains provider internals or credentials.
    error: str | None = None
    #: Operator-facing cause (exception type + message) for the same failure.
    #:
    #: Kept apart from ``error`` because the two have different audiences: a
    #: rate limit and a dead endpoint read identically in ``error``, which made
    #: an evaluation run undiagnosable, but "connection pool exhausted" has no
    #: business reaching an end user. Log it; do not render it.
    error_detail: str | None = None


class RevisionRequest(AiBaseModel):
    """A natural-language change request from the trip owner."""

    generation_id: str
    instruction: str
    #: Optional narrowing hint from the UI, e.g. ``[2]`` for "day 2 only".
    target_days: list[int] = Field(default_factory=list)
    #: Force a fresh place search even when the planner-only route would do.
    force_retrieval: bool = False
