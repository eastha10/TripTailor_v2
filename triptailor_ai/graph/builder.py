"""LangGraph assembly.

The graph is deterministic: fixed nodes, one conditional edge, one bounded
loop.  LangChain is used inside the provider layer for model calls only -- no
agent executor decides the control flow.

::

    START -> prepare_input -> normalize_preferences -> analyze_consensus
          -> retrieve_places -> plan_itinerary -> validate_itinerary
                                                    |
              valid ------------------------------> build_explanation -> END
              invalid, retries left --------------> repair_itinerary --+
                                                    ^                  |
                                                    +------------------+
              invalid, budget exhausted ----------> finalize_needs_input -> END
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from triptailor_ai.graph.routing import (
    CONSENSUS,
    EXPLAIN,
    NEEDS_INPUT,
    NORMALIZE,
    PLAN,
    PREPARE_INPUT,
    REPAIR,
    RETRIEVE,
    VALIDATE,
    route_after_validation,
)
from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes import (
    PlanningDeps,
    make_consensus_node,
    make_explanation_node,
    make_needs_input_node,
    make_plan_node,
    make_prepare_input_node,
    make_repair_node,
    make_retrieve_node,
    make_validate_node,
)

#: Entry points supported by :func:`build_planning_graph`.
ENTRY_POINTS = (PREPARE_INPUT, RETRIEVE, PLAN)


def build_planning_graph(deps: PlanningDeps, *, entry_point: str = PREPARE_INPUT) -> Any:
    """Compile the planning graph.

    ``entry_point`` selects how much work a revision re-runs:

    * ``prepare_input`` -- full generation,
    * ``retrieve_places`` -- keep preferences, search places again,
    * ``plan_itinerary`` -- keep preferences *and* candidates, re-plan only.
    """

    if entry_point not in ENTRY_POINTS:
        raise ValueError(f"entry_point must be one of {ENTRY_POINTS}, got {entry_point!r}")

    graph = StateGraph(PlanningState)

    graph.add_node(PREPARE_INPUT, make_prepare_input_node(deps))
    graph.add_node(NORMALIZE, make_normalize_node_safe(deps))
    graph.add_node(CONSENSUS, make_consensus_node(deps))
    graph.add_node(RETRIEVE, make_retrieve_node(deps))
    graph.add_node(PLAN, make_plan_node(deps))
    graph.add_node(VALIDATE, make_validate_node(deps))
    graph.add_node(REPAIR, make_repair_node(deps))
    graph.add_node(EXPLAIN, make_explanation_node(deps))
    graph.add_node(NEEDS_INPUT, make_needs_input_node(deps))

    graph.add_edge(START, entry_point)
    graph.add_edge(PREPARE_INPUT, NORMALIZE)
    graph.add_edge(NORMALIZE, CONSENSUS)
    graph.add_edge(CONSENSUS, RETRIEVE)
    graph.add_edge(RETRIEVE, PLAN)
    graph.add_edge(PLAN, VALIDATE)
    graph.add_conditional_edges(
        VALIDATE,
        route_after_validation,
        {EXPLAIN: EXPLAIN, REPAIR: REPAIR, NEEDS_INPUT: NEEDS_INPUT},
    )
    graph.add_edge(REPAIR, VALIDATE)
    graph.add_edge(EXPLAIN, END)
    graph.add_edge(NEEDS_INPUT, END)

    return graph.compile()


def make_normalize_node_safe(deps: PlanningDeps):
    """Import indirection so ``nodes`` stays free of graph imports."""

    from triptailor_ai.nodes.normalize_preferences import make_normalize_node

    return make_normalize_node(deps)


def graph_recursion_limit(max_repair_attempts: int) -> int:
    """Hard ceiling on LangGraph steps.

    The loop is already bounded by ``retry_count``; this is a second belt so a
    routing bug can never spin forever.
    """

    base_nodes = 7  # prepare, normalize, consensus, retrieve, plan, validate, explain
    return base_nodes + 2 * max(max_repair_attempts, 0) + 5
