"""Bounded repair of a plan the validator rejected.

Two stages, in order:

1. **Mechanical** -- duplicates, out-of-hours stops, overlaps, wrong dates.
   These are arithmetic and lookup, so they are settled in code. A real run had
   15 of 40 scenarios fail because ``gpt-4o-mini`` could not clear exactly
   these inside the repair budget.
2. **LLM** -- whatever survives stage 1, which is the part that needs judgement:
   what to drop when the budget is blown, which preference to sacrifice.

If stage 1 clears everything, stage 2 is skipped entirely and the attempt costs
no tokens at all.

``retry_count`` is incremented here, and only here. It is a *business* counter
distinct from the LLM network/parse retries inside the provider.
"""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes.common import (
    build_itinerary,
    consecutive_place_pairs,
    constraints_payload,
    node_trace,
)
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.nodes.mechanical_repair import mechanical_repair
from triptailor_ai.prompts.repair import build_repair_messages
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.itinerary import Itinerary, ItineraryDraft
from triptailor_ai.schemas.validation import Severity


def make_repair_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def repair_itinerary(state: PlanningState) -> PlanningState:
        with node_trace("repair", state) as trace:
            attempt = state.get("retry_count", 0) + 1
            itinerary: Itinerary = state.get("itinerary_draft") or Itinerary()
            candidates = state.get("candidate_places") or []
            errors = state.get("validation_errors") or []
            request = state["request"]

            # ---- stage 1: fix what does not need a model -------------------
            itinerary, changes = mechanical_repair(
                itinerary=itinerary,
                issues=errors,
                candidates=candidates,
                travel_period=request.travel_period,
                constraints=state.get("retrieval_constraints"),
                participant_count=len(request.participants),
            )

            remaining = _revalidate(deps, state, itinerary)
            if not remaining:
                # Everything cleared without an LLM call.
                travel_times = await deps.retrieval.travel_times(
                    consecutive_place_pairs(itinerary),
                    {place.place_id: place for place in candidates},
                )
                trace.trace.provider = "mechanical"
                trace.trace.model = "deterministic"
                return {
                    "itinerary_draft": itinerary,
                    "travel_times": travel_times,
                    "retry_count": attempt,
                    "status": GenerationStatus.VALIDATING,
                    "repair_changes": changes,
                    "node_traces": [trace.finish()],
                }

            # ---- stage 2: the judgement calls ------------------------------
            provider = deps.model_router.for_node("repair")

            response = await provider.generate_structured(
                messages=build_repair_messages(
                    request=state["request"],
                    itinerary=itinerary,
                    issues=remaining,
                    candidates=candidates,
                    constraints=constraints_payload(state),
                    attempt=attempt,
                    is_final_attempt=attempt >= state.get("max_repair_attempts", 0),
                ),
                schema=ItineraryDraft,
                node_name="repair",
            )
            trace.record_provider(provider.name, provider.model, response.retry_count)

            # The repair prompt returns the whole plan; unmet preferences are
            # carried over because repair is not asked to re-derive them.
            draft = response.value.model_copy(
                update={
                    "unmet_preferences": (
                        response.value.unmet_preferences or itinerary.unmet_preferences
                    ),
                    # A repair that returns no stays has almost certainly just
                    # forgotten them -- the prompt asks for the whole plan back.
                    # Losing every night silently is far worse than keeping a
                    # stay the model meant to drop, which the validator sees.
                    "stays": response.value.stays or itinerary.stays,
                }
            )
            repaired = build_itinerary(draft, request, candidates)
            travel_times = await deps.retrieval.travel_times(
                consecutive_place_pairs(repaired),
                {place.place_id: place for place in candidates},
            )

            return {
                "itinerary_draft": repaired,
                "travel_times": travel_times,
                "retry_count": attempt,
                "status": GenerationStatus.VALIDATING,
                "repair_changes": changes,
                "node_traces": [trace.finish()],
            }

    return repair_itinerary


def _revalidate(deps: PlanningDeps, state: PlanningState, itinerary: Itinerary):
    """Which errors survived the mechanical pass."""

    result = deps.validator.validate(
        request=state["request"],
        itinerary=itinerary,
        candidates=state.get("candidate_places") or [],
        hard_constraints=state.get("hard_constraints") or [],
        travel_times=state.get("travel_times") or [],
        group_budget=state.get("group_budget"),
    )
    return [i for i in result.errors if i.severity is Severity.ERROR]
