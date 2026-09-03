"""Preference normalization prompt."""

from __future__ import annotations

from typing import Any

from triptailor_ai.prompts.blocks import render_block
from triptailor_ai.prompts.pseudonymize import Pseudonymizer
from triptailor_ai.providers.base import ChatMessage
from triptailor_ai.schemas.trip import TripPlanningRequest

NORMALIZER_PROMPT_VERSION = "normalizer/v1"

_SYSTEM = """당신은 여행 동행자들의 설문 응답을 구조화하는 분석기입니다.

절대 규칙:
1. PARTICIPANTS 블록에 실제로 적힌 내용만 사용합니다. 추측하거나 일반적인 여행 상식으로 보충하지 않습니다.
2. sourceText는 원문에서 그대로 잘라낸 문장이어야 합니다. 의역/요약 금지.
3. 하나의 문장은 하나의 preference로 만듭니다. 여러 의미가 섞여 있으면 나누되, 각 조각도 원문 그대로여야 합니다.
4. constraintType 분류 기준을 엄격히 지킵니다.
   - HARD: 명시적 알레르기, 명시적으로 '못 한다/불가능하다'고 말한 것, 실제 참여 불가능한 날짜, 휠체어 등 물리적 제약.
   - SOFT: '좋아한다', '선호한다', '힘들다', '꼭 가고 싶다' 등 강한 희망이지만 물리적 불가능은 아닌 것.
   애매하면 SOFT로 둡니다. HARD는 일정 생성을 실패시킬 수 있으므로 과도하게 붙이지 않습니다.
   단, **알레르기와 '먹을 수 없다/불가능하다'는 예외 없이 HARD**입니다. 여기서는 절대 망설이지 마세요.
   (이 두 가지는 시스템이 코드로 한 번 더 강제하지만, 모델도 정확히 분류해야 합니다.)
5. participantId는 PARTICIPANTS 블록에 있는 값(P1, P2, ...)만 사용합니다.
6. confidence는 해석의 확신도입니다. 원문이 모호하면 0.5 이하로 낮춥니다.
7. 아무것도 추출할 수 없으면 빈 배열을 반환합니다. 억지로 만들지 않습니다.

출력은 지정된 JSON 스키마만 따릅니다."""


def build_normalizer_messages(
    request: TripPlanningRequest, pseudonymizer: Pseudonymizer
) -> list[ChatMessage]:
    payload = build_participant_payload(request, pseudonymizer)
    user = "\n\n".join(
        [
            "아래 동행자 응답을 정규화된 선호 목록으로 변환하세요.",
            render_block("PARTICIPANTS", payload),
            "각 preferenceId는 '<participantId>-pref-<번호>' 형식으로 고유하게 부여하세요.",
        ]
    )
    return [ChatMessage.system(_SYSTEM), ChatMessage.user(user)]


def build_participant_payload(
    request: TripPlanningRequest, pseudonymizer: Pseudonymizer
) -> list[dict[str, Any]]:
    """Pseudonymised participant answers. Display names are never included."""

    return [
        {
            "participantId": pseudonymizer.alias(participant.participant_id),
            "fields": participant.source_fields(),
            "budgetBand": participant.budget_band.value if participant.budget_band else None,
            "accommodationType": (
                participant.accommodation_type.value
                if participant.accommodation_type
                else None
            ),
        }
        for participant in request.participants
    ]
