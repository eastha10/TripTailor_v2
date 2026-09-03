"""Candidate place retrieval (no LLM).

The only place real-world data enters the pipeline.  Everything downstream is
constrained to what this node returns.
"""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes.common import node_trace
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.schemas.common import VerificationStatus
from triptailor_ai.schemas.generation import GenerationStatus


def make_retrieve_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def retrieve_places(state: PlanningState) -> PlanningState:
        with node_trace("retrieve_places", state) as trace:
            candidates, constraints = await deps.retrieval.retrieve(
                state["request"], state.get("normalized_preferences") or []
            )

            unresolved = list(state.get("unresolved_issues") or [])
            unresolved.extend(_data_quality_notes(candidates))

            return {
                "candidate_places": candidates,
                "retrieval_constraints": constraints,
                "unresolved_issues": unresolved,
                "status": GenerationStatus.PLANNING,
                "node_traces": [trace.finish()],
            }

    return retrieve_places


def _data_quality_notes(candidates) -> list[str]:  # noqa: ANN001
    """Surface thin candidate data instead of letting the plan look confident."""

    notes: list[str] = []
    if len(candidates) < 6:
        notes.append(
            f"검색된 후보 장소가 {len(candidates)}건뿐이라 일정 다양성이 제한될 수 있습니다."
        )
    missing_hours = sum(1 for c in candidates if c.opening_hours is None)
    if missing_hours:
        notes.append(
            f"후보 장소 {missing_hours}건에 영업시간 정보가 없어 운영 여부를 검증하지 못합니다."
        )
    stale = sum(1 for c in candidates if c.verification_status is VerificationStatus.STALE)
    if stale:
        notes.append(f"후보 장소 {stale}건의 데이터가 오래되었습니다(STALE).")
    return notes
