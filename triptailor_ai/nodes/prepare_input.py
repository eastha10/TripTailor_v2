"""Input preparation.

The original design put a DB-reading "Input Loader" here.  This repository is a
standalone AI module, so the backend does the DB read and hands over a
:class:`TripPlanningRequest`; this node validates that payload and seeds the
deterministic parts of the state.  See ``docs/AI_ARCHITECTURE.md``.
"""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes.common import node_trace
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.retrieval.service import RetrievalService
from triptailor_ai.schemas.generation import GenerationStatus


def make_prepare_input_node(
    deps: PlanningDeps,
) -> Callable[[PlanningState], PlanningState]:
    async def prepare_input(state: PlanningState) -> PlanningState:
        with node_trace("prepare_input", state) as trace:
            request = state["request"]
            budget = RetrievalService.derive_group_budget(request)

            unresolved = list(state.get("unresolved_issues") or [])
            if budget.has_band_mismatch:
                unresolved.append(
                    "참여자 예산 밴드가 서로 달라 가장 낮은 상한을 기준으로 계획했습니다."
                )
            missing_answers = [
                p.participant_id for p in request.participants if not p.source_fields()
            ]
            if missing_answers:
                unresolved.append(
                    f"{len(missing_answers)}명의 자유 응답이 비어 있어 선호 반영이 제한적입니다."
                )

            return {
                "raw_preferences": list(request.participants),
                "group_budget": budget,
                "unresolved_issues": unresolved,
                "status": GenerationStatus.NORMALIZING,
                "provider_map": deps.model_router.provider_map(),
                "node_traces": [trace.finish()],
            }

    return prepare_input
