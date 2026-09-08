"""Free text -> traceable normalized preferences (LLM + safety enforcement).

The model proposes a HARD/SOFT split, but two categories are too dangerous to
leave to a probabilistic call: an allergy and a physical impossibility. A real
run of ``gpt-4o-mini`` classified "갑각류 알레르기가 있어서 해산물은 먹을 수
없어요" as HARD in one call and let a seafood restaurant through in another --
same prompt, same text. A 90%-correct allergy classifier is not an allergy
classifier.

So those two are decided in code, after the model answers.
"""

from __future__ import annotations

from typing import Callable

from triptailor_ai.graph.state import PlanningState
from triptailor_ai.nodes.common import node_trace, pseudonymizer_for
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.prompts.normalizer import build_normalizer_messages
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.preference import (
    ConstraintType,
    NormalizedPreference,
    NormalizedPreferenceSet,
    PreferenceCategory,
    Priority,
)
from triptailor_ai.schemas.trip import TripPlanningRequest


def make_normalize_node(deps: PlanningDeps) -> Callable[[PlanningState], PlanningState]:
    async def normalize_preferences(state: PlanningState) -> PlanningState:
        with node_trace("normalizer", state) as trace:
            request: TripPlanningRequest = state["request"]
            pseudonymizer = pseudonymizer_for(state, deps.settings)
            provider = deps.model_router.for_node("normalizer")

            response = await provider.generate_structured(
                messages=build_normalizer_messages(request, pseudonymizer),
                schema=NormalizedPreferenceSet,
                node_name="normalizer",
            )
            trace.record_provider(provider.name, provider.model, response.retry_count)

            preferences = pseudonymizer.restore(response.value.preferences)
            preferences = _deduplicate_ids(preferences)
            preferences, notes = _verify_traceability(preferences, request)
            preferences, safety_notes = enforce_safety_constraints(preferences)
            notes.extend(safety_notes)

            return {
                "normalized_preferences": preferences,
                "hard_constraints": [p for p in preferences if p.is_hard],
                "soft_preferences": [p for p in preferences if not p.is_hard],
                "unresolved_issues": [*(state.get("unresolved_issues") or []), *notes],
                "status": GenerationStatus.ANALYZING,
                "node_traces": [trace.finish()],
            }

    return normalize_preferences


def _deduplicate_ids(preferences: list[NormalizedPreference]) -> list[NormalizedPreference]:
    seen: set[str] = set()
    result: list[NormalizedPreference] = []
    for preference in preferences:
        preference_id = preference.preference_id
        suffix = 1
        while preference_id in seen:
            suffix += 1
            preference_id = f"{preference.preference_id}-{suffix}"
        seen.add(preference_id)
        result.append(preference.model_copy(update={"preference_id": preference_id}))
    return result


def _verify_traceability(
    preferences: list[NormalizedPreference], request: TripPlanningRequest
) -> tuple[list[NormalizedPreference], list[str]]:
    """Flag preferences whose ``source_text`` is not in the participant's answer.

    Structured-field preferences (budgetBand, accommodationType) are exempt --
    their source text *is* the enum value.  Anything else that cannot be found
    in the original answer is a paraphrase at best, so its confidence is
    lowered and the run reports it rather than trusting it silently.
    """

    answers = {
        participant.participant_id: " ".join(participant.source_fields().values())
        for participant in request.participants
    }
    structured_fields = {"budgetBand", "accommodationType"}

    checked: list[NormalizedPreference] = []
    untraceable = 0
    for preference in preferences:
        if preference.source_field in structured_fields:
            checked.append(preference)
            continue
        haystack = answers.get(preference.participant_id, "")
        if preference.source_text and preference.source_text in haystack:
            checked.append(preference)
            continue
        untraceable += 1
        checked.append(
            preference.model_copy(
                update={"confidence": min(preference.confidence, 0.3)}
            )
        )

    notes: list[str] = []
    if untraceable:
        notes.append(
            f"{untraceable}건의 선호가 원문에서 그대로 확인되지 않아 신뢰도를 낮췄습니다. "
            "검토가 필요합니다."
        )
    return checked, notes


#: Text that always means an allergy, whatever the model decided.
ALLERGY_MARKERS: tuple[str, ...] = ("알레르기", "알러지", "알레지", "allergy", "allergic")

#: Text that always means a physical impossibility, not a preference.
IMPOSSIBILITY_MARKERS: tuple[str, ...] = (
    "먹을 수 없",
    "못 먹",
    "못먹",
    "먹지 못",
    "불가능",
    "휠체어",
    "목발",
    "거동이 불편",
)

#: Impossibility markers that specifically concern moving around.
_MOBILITY_MARKERS: tuple[str, ...] = ("휠체어", "목발", "거동이 불편", "걷", "보행", "계단")

#: Impossibility markers that specifically concern food.
_FOOD_MARKERS: tuple[str, ...] = ("먹", "식사", "음식", "채식", "비건")


def enforce_safety_constraints(
    preferences: list[NormalizedPreference],
) -> tuple[list[NormalizedPreference], list[str]]:
    """Force HARD on allergies and stated impossibilities.

    Upgrades only -- a HARD classification from the model is never softened
    here. Every change is reported so a reviewer can see that the system, not
    the model, made the call.
    """

    enforced: list[NormalizedPreference] = []
    upgrades: list[str] = []

    for preference in preferences:
        text = preference.source_text.lower()
        category = preference.category
        reason: str | None = None

        if any(marker in text for marker in ALLERGY_MARKERS):
            category = PreferenceCategory.DIETARY
            reason = "알레르기"
        elif any(marker in text for marker in IMPOSSIBILITY_MARKERS):
            if any(m in text for m in _MOBILITY_MARKERS):
                category = PreferenceCategory.MOBILITY
                reason = "이동 불가"
            elif any(m in text for m in _FOOD_MARKERS):
                category = PreferenceCategory.DIETARY
                reason = "섭취 불가"

        if reason is None or (
            preference.is_hard and preference.category is category
        ):
            enforced.append(preference)
            continue

        upgrades.append(
            f"'{preference.source_text[:30]}' -> {reason}({category.value})"
        )
        enforced.append(
            preference.model_copy(
                update={
                    "category": category,
                    "constraint_type": ConstraintType.HARD,
                    "priority": Priority.HIGH,
                    "confidence": max(preference.confidence, 0.9),
                }
            )
        )

    notes: list[str] = []
    if upgrades:
        notes.append(
            f"안전 규칙에 따라 {len(upgrades)}건을 HARD 제약으로 확정했습니다: "
            + "; ".join(upgrades[:5])
        )
    return enforced, notes
