"""Consensus and conflict analysis prompt."""

from __future__ import annotations

from triptailor_ai.prompts.blocks import render_block
from triptailor_ai.prompts.pseudonymize import Pseudonymizer
from triptailor_ai.providers.base import ChatMessage
from triptailor_ai.schemas.preference import NormalizedPreference

CONSENSUS_PROMPT_VERSION = "consensus/v1"

_SYSTEM = """당신은 여행 그룹의 선호를 조율하는 분석기입니다.

절대 규칙:
1. PREFERENCES 블록에 있는 preference만 참조합니다. 새로운 선호를 만들지 않습니다.
2. 충돌을 숨기지 않습니다. 한 사람의 선호를 임의로 우선하거나 '문제 없음'으로 처리하지 않습니다.
3. commonPreferences는 2명 이상이 실제로 공유하는 것만 넣습니다. participantIds에 근거가 있어야 합니다.
4. conflicts에는 반드시 involvedParticipantIds와 relatedPreferenceIds를 채웁니다.
   possibleCompromises는 양쪽 모두 수용 가능한 현실적 대안을 2개 이상 제시합니다.
5. HARD 제약이 한쪽에 걸린 충돌은 blocking=true로 표시합니다.
6. constraintType(HARD/SOFT)은 재분류하지 않습니다. 입력값이 그대로 유지됩니다.
7. summary는 2문장 이내의 한국어로 작성합니다.
8. commonPreferences와 conflicts, summary만 출력합니다. 입력 선호 목록을 그대로 다시 옮겨 적지 마세요.

출력은 지정된 JSON 스키마만 따릅니다."""


def build_consensus_messages(
    preferences: list[NormalizedPreference],
    pseudonymizer: Pseudonymizer,
) -> list[ChatMessage]:
    aliased = [
        preference.model_copy(
            update={"participant_id": pseudonymizer.alias(preference.participant_id)}
        )
        for preference in preferences
    ]
    user = "\n\n".join(
        [
            "아래 정규화된 선호 목록에서 공통점, 개인 선호, 충돌을 분석하세요.",
            render_block("PARTICIPANT_IDS", pseudonymizer.aliases),
            render_block(
                "PREFERENCES",
                [p.model_dump(by_alias=True, mode="json") for p in aliased],
            ),
        ]
    )
    return [ChatMessage.system(_SYSTEM), ChatMessage.user(user)]
