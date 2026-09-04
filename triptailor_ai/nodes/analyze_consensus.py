"""Common preferences, individual preferences and conflicts (LLM + reconciliation).

The model proposes; deterministic code reconciles.  Constraint types are never
re-derived from the model's answer -- they stay exactly as the normalizer
recorded them, so a later prompt cannot quietly downgrade an allergy.
"""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes.common import node_trace, pseudonymizer_for
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.prompts.consensus import build_consensus_messages
from triptailor_ai.prompts.pseudonymize import Pseudonymizer
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.preference import (
    CommonPreference,
    Conflict,
    ConsensusAnalysis,
    ConsensusDraft,
    NormalizedPreference,
)


def make_consensus_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def analyze_consensus(state: PlanningState) -> PlanningState:
        with node_trace("consensus", state) as trace:
            preferences: list[NormalizedPreference] = state["normalized_preferences"]
            pseudonymizer = pseudonymizer_for(state, deps.settings)
            provider = deps.model_router.for_node("consensus")

            if not preferences:
                return {
                    "common_preferences": [],
                    "individual_preferences": [],
                    "conflicts": [],
                    "consensus_summary": "정규화된 선호가 없어 공통점을 분석하지 못했습니다.",
                    "status": GenerationStatus.RETRIEVING,
                    "node_traces": [trace.finish()],
                }

            response = await provider.generate_structured(
                messages=build_consensus_messages(preferences, pseudonymizer),
                schema=ConsensusDraft,
                node_name="consensus",
            )
            trace.record_provider(provider.name, provider.model, response.retry_count)
            analysis = _reconcile(response.value, preferences, pseudonymizer)
            analysis = _add_derived_conflicts(analysis, state)

            return {
                "common_preferences": analysis.common_preferences,
                "individual_preferences": analysis.individual_preferences,
                # Recomputed from the normalizer's output, not the model's.
                "hard_constraints": [p for p in preferences if p.is_hard],
                "soft_preferences": [p for p in preferences if not p.is_hard],
                "conflicts": analysis.conflicts,
                "consensus_summary": analysis.summary,
                "status": GenerationStatus.RETRIEVING,
                "node_traces": [trace.finish()],
            }

    return analyze_consensus


def _reconcile(
    draft: ConsensusDraft,
    preferences: list[NormalizedPreference],
    pseudonymizer: Pseudonymizer,
) -> ConsensusAnalysis:
    """Assemble the full analysis, discarding claims about ids that do not exist."""

    by_id = {p.preference_id: p for p in preferences}
    total = len({p.participant_id for p in preferences}) or 1

    common: list[CommonPreference] = []
    for entry in draft.common_preferences:
        participant_ids = sorted(set(pseudonymizer.restore_id_list(entry.participant_ids)))
        preference_ids = [pid for pid in entry.preference_ids if pid in by_id]
        if len(participant_ids) < 2:
            continue
        common.append(
            entry.model_copy(
                update={
                    "participant_ids": participant_ids,
                    "preference_ids": preference_ids,
                    # Recomputed: support is arithmetic, not an LLM judgement.
                    "support_ratio": round(len(participant_ids) / total, 3),
                }
            )
        )

    conflicts: list[Conflict] = []
    for conflict in draft.conflicts:
        participant_ids = sorted(
            set(pseudonymizer.restore_id_list(conflict.involved_participant_ids))
        )
        preference_ids = [pid for pid in conflict.related_preference_ids if pid in by_id]
        if not participant_ids and not preference_ids:
            continue
        blocking = conflict.blocking or any(by_id[pid].is_hard for pid in preference_ids)
        conflicts.append(
            conflict.model_copy(
                update={
                    "involved_participant_ids": participant_ids,
                    "related_preference_ids": preference_ids,
                    "blocking": blocking,
                }
            )
        )

    covered = {pid for entry in common for pid in entry.preference_ids}
    individual = [p for p in preferences if p.preference_id not in covered]

    return ConsensusAnalysis(
        common_preferences=common,
        conflicts=conflicts,
        individual_preferences=individual,
        # Never re-derived from the model: an allergy must not be able to
        # lose its HARD classification in a later prompt.
        hard_constraints=[p for p in preferences if p.is_hard],
        soft_preferences=[p for p in preferences if not p.is_hard],
        summary=draft.summary,
    )


def _add_derived_conflicts(
    analysis: ConsensusAnalysis, state: PlanningState
) -> ConsensusAnalysis:
    """Add conflicts the system can prove, whether or not the model saw them.

    A budget-band mismatch is arithmetic on enum values -- there is nothing to
    interpret. Leaving it to the model meant Qwen2.5-7B silently dropped it on
    a three-band group, so the reviewer never learned that the plan had been
    capped to the lowest participant's ceiling.
    """

    budget = state.get("group_budget")
    if budget is None or not budget.has_band_mismatch:
        return analysis
    if any(c.conflict_id == "derived-budget-band" for c in analysis.conflicts):
        return analysis

    bands = {
        p.participant_id: p.budget_band.value
        for p in state["request"].participants
        if p.budget_band is not None
    }
    band_preferences = [
        p.preference_id
        for p in state.get("normalized_preferences") or []
        if p.source_field == "budgetBand"
    ]
    cap = budget.per_person_cap_krw

    return analysis.model_copy(
        update={
            "conflicts": [
                *analysis.conflicts,
                Conflict(
                    conflict_id="derived-budget-band",
                    involved_participant_ids=sorted(bands),
                    related_preference_ids=band_preferences,
                    reason=(
                        "참여자별 예산 밴드가 서로 다릅니다"
                        + (f" (1인 {cap:,}원 기준으로 계획됨)." if cap else ".")
                    ),
                    possible_compromises=[
                        "가장 낮은 상한에 맞춘 기본 일정 + 선택 비용 항목 분리",
                        "고가 활동은 희망자만 참여하는 자유시간으로 배치",
                    ],
                    blocking=False,
                ),
            ]
        }
    )