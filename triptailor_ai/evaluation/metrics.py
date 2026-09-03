"""Metrics for comparing providers on the same scenarios.

Every metric here is computed from data the pipeline already produces.  None
of them is an LLM judgement -- an LLM grading its own plan would tell us
nothing about grounding or constraint compliance.
"""

from __future__ import annotations

from typing import Iterable

from pydantic import Field

from triptailor_ai.schemas.common import AiBaseModel
from triptailor_ai.schemas.generation import GenerationStatus, TripPlanningResult
from triptailor_ai.schemas.validation import ValidationCode

#: Error codes that mean a HARD constraint was actually violated.
HARD_CONSTRAINT_CODES: frozenset[ValidationCode] = frozenset(
    {
        ValidationCode.DIETARY_CONSTRAINT_VIOLATION,
        ValidationCode.MOBILITY_CONSTRAINT_VIOLATION,
        ValidationCode.BUDGET_EXCEEDED,
        ValidationCode.OUTSIDE_TRAVEL_PERIOD,
        ValidationCode.PLACE_CLOSED,
        ValidationCode.OUTSIDE_OPENING_HOURS,
    }
)


class ScenarioMetrics(AiBaseModel):
    """One scenario, one provider configuration."""

    scenario_id: str
    status: GenerationStatus

    #: Result parsed and validated against the schemas at all.
    schema_validity: float = 0.0
    #: Share of scheduled items whose placeId came from the candidate set.
    grounded_place_rate: float = 0.0
    #: Share of items involved in a hard-constraint violation.
    hard_constraint_violation_rate: float = 0.0
    #: Share of normalized preferences referenced by at least one item.
    preference_coverage: float = 0.0
    #: 1.0 when conflicts were surfaced iff the scenario expected them.
    conflict_transparency: float = 0.0
    #: Deterministic validator verdict.
    validation_pass_rate: float = 0.0

    item_count: int = 0
    candidate_count: int = 0
    conflict_count: int = 0
    repair_count: int = 0
    llm_retry_count: int = 0
    latency_ms: int | None = None
    error_codes: list[str] = Field(default_factory=list)
    #: Provider/system error text when ``status is FAILED``.
    #:
    #: Without this a suite run reports "3 scenarios FAILED" and nothing else,
    #: which is unusable for diagnosis -- the run that surfaced this had three
    #: consecutive transient provider failures that all passed in isolation.
    error: str | None = None
    warning_codes: list[str] = Field(default_factory=list)

    #: Human evaluation placeholder -- deliberately never auto-filled.
    plan_feasibility: float | None = None

    expectations_met: bool = True
    expectation_failures: list[str] = Field(default_factory=list)


class AggregateMetrics(AiBaseModel):
    """Mean metrics across a scenario suite, for one configuration."""

    label: str
    scenario_count: int
    schema_validity: float = 0.0
    grounded_place_rate: float = 0.0
    hard_constraint_violation_rate: float = 0.0
    preference_coverage: float = 0.0
    conflict_transparency: float = 0.0
    validation_pass_rate: float = 0.0
    expectation_pass_rate: float = 0.0
    mean_repair_count: float = 0.0
    mean_latency_ms: float = 0.0
    failed_scenarios: list[str] = Field(default_factory=list)
    provider_map: dict[str, str] = Field(default_factory=dict)


def score_result(
    result: TripPlanningResult,
    *,
    scenario_id: str,
    expects_conflict: bool = False,
) -> ScenarioMetrics:
    """Turn one generation result into comparable numbers."""

    itinerary = result.itinerary
    items = itinerary.all_items() if itinerary else []
    candidate_ids = {place.place_id for place in result.candidate_places}

    grounded = sum(1 for item in items if item.place_id in candidate_ids)
    violation_items = {
        item_id
        for issue in result.validation.errors
        if issue.code in HARD_CONSTRAINT_CODES
        for item_id in issue.item_ids
    }
    covered = {pid for item in items for pid in item.matched_preference_ids}
    total_preferences = len(result.normalized_preferences)
    conflicts = result.preference_summary.conflicts

    return ScenarioMetrics(
        scenario_id=scenario_id,
        status=result.status,
        schema_validity=1.0 if result.status is not GenerationStatus.FAILED else 0.0,
        grounded_place_rate=_ratio(grounded, len(items)),
        hard_constraint_violation_rate=_ratio(len(violation_items), len(items)),
        preference_coverage=_ratio(len(covered), total_preferences),
        conflict_transparency=1.0 if bool(conflicts) == expects_conflict else 0.0,
        validation_pass_rate=1.0 if result.validation.is_valid else 0.0,
        item_count=len(items),
        candidate_count=len(result.candidate_places),
        conflict_count=len(conflicts),
        repair_count=result.metadata.repair_attempts,
        llm_retry_count=result.metadata.total_llm_retries,
        latency_ms=result.metadata.latency_ms,
        error_codes=sorted({i.code.value for i in result.validation.errors}),
        error=(
            f"{result.error} ({result.error_detail})"
            if result.error_detail
            else result.error
        ),
        warning_codes=sorted({i.code.value for i in result.validation.warnings}),
    )


def aggregate(
    label: str,
    metrics: Iterable[ScenarioMetrics],
    *,
    provider_map: dict[str, str] | None = None,
) -> AggregateMetrics:
    entries = list(metrics)
    if not entries:
        return AggregateMetrics(label=label, scenario_count=0, provider_map=provider_map or {})

    def mean(attribute: str) -> float:
        values = [getattr(m, attribute) for m in entries if getattr(m, attribute) is not None]
        return round(sum(values) / len(values), 4) if values else 0.0

    return AggregateMetrics(
        label=label,
        scenario_count=len(entries),
        schema_validity=mean("schema_validity"),
        grounded_place_rate=mean("grounded_place_rate"),
        hard_constraint_violation_rate=mean("hard_constraint_violation_rate"),
        preference_coverage=mean("preference_coverage"),
        conflict_transparency=mean("conflict_transparency"),
        validation_pass_rate=mean("validation_pass_rate"),
        expectation_pass_rate=round(
            sum(1 for m in entries if m.expectations_met) / len(entries), 4
        ),
        mean_repair_count=mean("repair_count"),
        mean_latency_ms=mean("latency_ms"),
        failed_scenarios=[m.scenario_id for m in entries if not m.expectations_met],
        provider_map=provider_map or {},
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
