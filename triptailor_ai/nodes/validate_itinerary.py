"""Deterministic validation (no LLM)."""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.logging_utils import log_event
from triptailor_ai.nodes.common import node_trace
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.itinerary import Itinerary


def make_validate_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def validate_itinerary(state: PlanningState) -> PlanningState:
        with node_trace("validate_itinerary", state) as trace:
            itinerary: Itinerary = state.get("itinerary_draft") or Itinerary()

            result = deps.validator.validate(
                request=state["request"],
                itinerary=itinerary,
                candidates=state.get("candidate_places") or [],
                hard_constraints=state.get("hard_constraints") or [],
                travel_times=state.get("travel_times") or [],
                group_budget=state.get("group_budget"),
            )

            log_event(
                "validation.result",
                generationId=state.get("generation_id"),
                tripId=state.get("trip_id"),
                isValid=result.is_valid,
                errorCount=result.error_count,
                warningCount=result.warning_count,
                errorCodes=sorted({i.code.value for i in result.errors}),
                checkedRules=result.checked_rules,
                skippedRules=result.skipped_rules,
                retryCount=state.get("retry_count", 0),
            )

            return {
                "validation_result": result,
                "validation_errors": result.errors,
                "validation_warnings": result.warnings,
                "status": (
                    GenerationStatus.VALIDATING if result.is_valid else GenerationStatus.REPAIRING
                ),
                "node_traces": [trace.finish()],
            }

    return validate_itinerary
