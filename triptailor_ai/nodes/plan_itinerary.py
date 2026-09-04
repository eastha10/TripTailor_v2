"""Itinerary planning (LLM, constrained to retrieved candidates)."""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes.common import (
    build_itinerary,
    consecutive_place_pairs,
    constraints_payload,
    node_trace,
    pseudonymizer_for,
)
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.prompts.planner import build_planner_messages
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.itinerary import ItineraryDraft


def make_plan_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def plan_itinerary(state: PlanningState) -> PlanningState:
        with node_trace("planner", state) as trace:
            candidates = state.get("candidate_places") or []
            provider = deps.model_router.for_node("planner")

            response = await provider.generate_structured(
                messages=build_planner_messages(
                    request=state["request"],
                    candidates=candidates,
                    preferences=state.get("normalized_preferences") or [],
                    conflicts=state.get("conflicts") or [],
                    constraints=constraints_payload(state),
                    pseudonymizer=pseudonymizer_for(state, deps.settings),
                    extra_instruction=state.get("revision_instruction"),
                    target_days=state.get("revision_target_days") or [],
                ),
                schema=ItineraryDraft,
                node_name="planner",
            )
            trace.record_provider(provider.name, provider.model, response.retry_count)

            itinerary = build_itinerary(response.value, state["request"], candidates)
            travel_times = await deps.retrieval.travel_times(
                consecutive_place_pairs(itinerary),
                {place.place_id: place for place in candidates},
            )

            return {
                "itinerary_draft": itinerary,
                "travel_times": travel_times,
                "status": GenerationStatus.VALIDATING,
                "node_traces": [trace.finish()],
            }

    return plan_itinerary
