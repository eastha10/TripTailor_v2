"""Explanation prompt: why this plan, in the group's own terms."""

from __future__ import annotations

from triptailor_ai.prompts.blocks import render_block
from triptailor_ai.prompts.pseudonymize import Pseudonymizer
from triptailor_ai.providers.base import ChatMessage
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.preference import ConsensusAnalysis

EXPLANATION_PROMPT_VERSION = "explanation/v1"

_SYSTEM = """당신은 완성된 여행 일정을 동행자들에게 설명하는 역할입니다.

절대 규칙:
1. ITINERARY와 CONSENSUS 블록에 있는 사실만 사용합니다. 없는 장소나 근거를 만들지 않습니다.
2. 동행자는 P1, P2와 같은 표기로만 지칭합니다.
3. 충돌(conflicts)과 반영하지 못한 선호(unmetPreferences)가 있으면 반드시 언급합니다. 숨기지 않습니다.
4. 3~5문장의 한국어 평문으로 작성합니다. 목록, 마크다운, 코드펜스를 쓰지 않습니다."""


def build_explanation_messages(
    *,
    itinerary: Itinerary,
    consensus: ConsensusAnalysis,
    pseudonymizer: Pseudonymizer,
    unresolved_issues: list[str],
) -> list[ChatMessage]:
    user = "\n\n".join(
        [
            "아래 일정이 왜 이렇게 구성되었는지 동행자에게 설명하세요.",
            render_block(
                "ITINERARY",
                [i.model_dump(by_alias=True, mode="json") for i in itinerary.all_items()],
            ),
            render_block(
                "CONSENSUS",
                {
                    "commonPreferences": [
                        c.model_copy(
                            update={
                                "participant_ids": [
                                    pseudonymizer.alias(p) for p in c.participant_ids
                                ]
                            }
                        ).model_dump(by_alias=True, mode="json")
                        for c in consensus.common_preferences
                    ],
                    "conflicts": [
                        c.model_copy(
                            update={
                                "involved_participant_ids": [
                                    pseudonymizer.alias(p)
                                    for p in c.involved_participant_ids
                                ]
                            }
                        ).model_dump(by_alias=True, mode="json")
                        for c in consensus.conflicts
                    ],
                    "unmetPreferences": itinerary.unmet_preferences,
                    "unresolvedIssues": unresolved_issues,
                },
            ),
        ]
    )
    return [ChatMessage.system(_SYSTEM), ChatMessage.user(user)]
