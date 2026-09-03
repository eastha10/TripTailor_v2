"""Terminal node for a run that could not be repaired within its budget."""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.logging_utils import log_event
from triptailor_ai.nodes.common import node_trace
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.schemas.generation import GenerationStatus


def make_needs_input_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def finalize_needs_input(state: PlanningState) -> PlanningState:
        with node_trace("finalize_needs_input", state) as trace:
            errors = state.get("validation_errors") or []
            unresolved = list(state.get("unresolved_issues") or [])
            unresolved.append(
                f"자동 수정 {state.get('retry_count', 0)}회 후에도 해결되지 않은 "
                f"제약 위반이 {len(errors)}건 남아 있습니다. 조건 조정이 필요합니다."
            )
            unresolved.extend(f"[{issue.code.value}] {issue.message}" for issue in errors)
            unresolved.extend(
                f"[{warning.code.value}] {warning.message}"
                for warning in state.get("validation_warnings") or []
            )

            log_event(
                "generation.needs_input",
                generationId=state.get("generation_id"),
                tripId=state.get("trip_id"),
                retryCount=state.get("retry_count", 0),
                errorCodes=sorted({i.code.value for i in errors}),
            )

            return {
                "unresolved_issues": list(dict.fromkeys(unresolved)),
                "status": GenerationStatus.NEEDS_INPUT,
                "node_traces": [trace.finish()],
            }

    return finalize_needs_input
