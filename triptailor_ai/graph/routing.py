"""Conditional edges.

Routing is rule-based on purpose.  Letting a model decide "should we repair or
give up?" would make the loop unbounded and the behaviour untestable.
"""

from __future__ import annotations

from triptailor_ai.graph.state import PlanningState

#: Node names, kept in one place so builder and routing cannot drift.
PREPARE_INPUT = "prepare_input"
NORMALIZE = "normalize_preferences"
CONSENSUS = "analyze_consensus"
RETRIEVE = "retrieve_places"
PLAN = "plan_itinerary"
VALIDATE = "validate_itinerary"
REPAIR = "repair_itinerary"
EXPLAIN = "build_explanation"
NEEDS_INPUT = "finalize_needs_input"


def route_after_validation(state: PlanningState) -> str:
    """valid -> explain; invalid and budget left -> repair; otherwise stop."""

    result = state.get("validation_result")
    if result is not None and result.is_valid:
        return EXPLAIN

    attempts = state.get("retry_count", 0)
    budget = state.get("max_repair_attempts", 0)
    if attempts < budget:
        return REPAIR
    return NEEDS_INPUT
