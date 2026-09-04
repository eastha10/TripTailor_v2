"""Narrative explanation + terminal NEEDS_REVIEW status (LLM, text only).

A valid plan is never auto-approved: the trip owner reviews it.
"""

from __future__ import annotations

from typing import Callable

from triptailor_ai.exceptions import TripTailorAIError
from triptailor_ai.graph.state import PlanningState
from triptailor_ai.logging_utils import log_event
from triptailor_ai.nodes.common import node_trace, pseudonymizer_for
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.prompts.explanation import build_explanation_messages
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.preference import ConsensusAnalysis


def make_explanation_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def build_explanation(state: PlanningState) -> PlanningState:
        with node_trace("explanation", state) as trace:
            itinerary: Itinerary = state.get("itinerary_draft") or Itinerary()
            consensus = ConsensusAnalysis(
                common_preferences=state.get("common_preferences") or [],
                conflicts=state.get("conflicts") or [],
                summary=state.get("consensus_summary"),
            )
            unresolved = _collect_unresolved(state)
            provider = deps.model_router.for_node("explanation")

            summary: str | None = None
            try:
                response = await provider.generate_text(
                    messages=build_explanation_messages(
                        itinerary=itinerary,
                        consensus=consensus,
                        pseudonymizer=pseudonymizer_for(state, deps.settings),
                        unresolved_issues=unresolved,
                    ),
                    node_name="explanation",
                )
                trace.record_provider(provider.name, provider.model, response.retry_count)
                summary = response.value.text.strip() or None
            except TripTailorAIError as exc:
                # A missing narrative must not discard an otherwise valid plan.
                trace.finish(ok=False, error=exc.code)
                log_event("explanation.failed", error=exc.code, message=exc.message)

            enriched = itinerary.model_copy(
                update={"summary": summary, "unresolved_issues": unresolved}
            )

            return {
                "itinerary_draft": enriched,
                "explanation": summary,
                "unresolved_issues": unresolved,
                "status": GenerationStatus.NEEDS_REVIEW,
                "node_traces": [trace.finish()],
            }

    return build_explanation


def _collect_unresolved(state: PlanningState) -> list[str]:
    """Merge run notes, blocking conflicts and validation warnings.

    Everything the reviewer needs in order to decide, in one list.
    """

    issues = list(state.get("unresolved_issues") or [])
    issues.extend(
        f"충돌 미해결: {conflict.reason}"
        for conflict in state.get("conflicts") or []
        if conflict.blocking
    )
    issues.extend(
        f"[{warning.code.value}] {warning.message}"
        for warning in state.get("validation_warnings") or []
    )
    return list(dict.fromkeys(issues))
