"""Itinerary planning prompt.

The hard rule enforced here in words -- and again, deterministically, by
:class:`~triptailor_ai.validation.rules.place_grounding_rule.PlaceGroundingRule`
-- is that only ``placeId`` values from ``CANDIDATE_PLACES`` may be scheduled.
"""

from __future__ import annotations

from typing import Any

from triptailor_ai.prompts.blocks import render_block
from triptailor_ai.prompts.pseudonymize import Pseudonymizer
from triptailor_ai.providers.base import ChatMessage
from triptailor_ai.schemas.common import Weekday
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.preference import Conflict, NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest

PLANNER_PROMPT_VERSION = "planner/v1"

_SYSTEM = """당신은 여행 일정을 설계하는 플래너입니다.

절대 규칙:
1. CANDIDATE_PLACES 블록에 있는 placeId만 사용합니다. 기억이나 상식으로 새로운 장소를 만들지 않습니다.
   목록에 없는 장소를 쓰면 그 일정은 폐기됩니다.
2. placeName은 CANDIDATE_PLACES의 name과 정확히 같아야 합니다.
3. CONSTRAINTS의 하드 제약은 반드시 지킵니다.
   - excludedDietaryTags를 가진 장소는 배치 금지
   - excludedAccessibilityTags를 가진 장소는 배치 금지
   - budgetCapPerPerson: 1인 예상 비용 합계가 이 값을 넘으면 안 됩니다
4. 영업시간(openingHours)이 있는 장소는 그 시간 안에 배치합니다. 휴무일(closedDays)에는 배치하지 않습니다.
   요일은 TRIP 블록의 days[].weekday를 사용합니다.
5. 같은 날 일정끼리 시간이 겹치면 안 되고, 장소 간 이동 여유를 최소 20분 이상 둡니다.
6. date는 TRIP 블록의 days[].date를 그대로 사용하고, day 번호와 일치시킵니다.
7. 하루 일정의 구조를 반드시 지킵니다.
   - 오전(09:00~11:30) 1개
   - **점심(11:30~14:00) 식사 장소 1개 — 필수**
   - 오후(14:00~18:00) 1~2개
   - **저녁(18:00~20:30) 식사 장소 1개 — 필수**
   점심과 저녁 식사는 모든 날짜에 반드시 배치합니다. 하루를 오후에만 채우지 마세요.
8. 같은 장소를 두 번 배치하지 않습니다.
9. reason에는 어떤 동행자 선호를 반영했는지 한국어로 한 문장 적고,
   matchedPreferenceIds에는 실제로 반영한 preferenceId만 넣습니다.
10. 반영하지 못한 선호는 unmetPreferences에 preferenceId로 정직하게 남깁니다. 숨기지 않습니다.
11. estimatedCostPerPerson은 CANDIDATE_PLACES의 값을 그대로 씁니다. 값이 없으면 null로 둡니다.

출력은 지정된 JSON 스키마만 따릅니다."""


def build_planner_messages(
    *,
    request: TripPlanningRequest,
    candidates: list[PlaceCandidate],
    preferences: list[NormalizedPreference],
    conflicts: list[Conflict],
    constraints: dict[str, Any],
    pseudonymizer: Pseudonymizer,
    extra_instruction: str | None = None,
    target_days: list[int] | None = None,
) -> list[ChatMessage]:
    sections = [
        "아래 정보를 바탕으로 실행 가능한 여행 일정을 설계하세요.",
        render_block("TRIP", build_trip_block(request)),
        render_block("CONSTRAINTS", constraints),
        render_block(
            "PREFERENCES",
            [
                p.model_copy(update={"participant_id": pseudonymizer.alias(p.participant_id)})
                .model_dump(by_alias=True, mode="json")
                for p in preferences
            ],
        ),
        render_block(
            "CONFLICTS",
            [
                c.model_copy(
                    update={
                        "involved_participant_ids": [
                            pseudonymizer.alias(i) for i in c.involved_participant_ids
                        ]
                    }
                ).model_dump(by_alias=True, mode="json")
                for c in conflicts
            ],
        ),
        render_block("CANDIDATE_PLACES", build_candidate_block(candidates)),
    ]
    if extra_instruction:
        sections.append(
            "사용자의 수정 요청입니다. 다른 제약을 지키면서 이 요청을 최우선으로 반영하세요.\n"
            + render_block(
                "INSTRUCTION",
                {"text": extra_instruction, "targetDays": target_days or []},
            )
        )
    return [ChatMessage.system(_SYSTEM), ChatMessage.user("\n\n".join(sections))]


def build_trip_block(request: TripPlanningRequest) -> dict[str, Any]:
    return {
        "region": request.region.name,
        "participantCount": len(request.participants),
        "startDate": request.travel_period.start_date.isoformat(),
        "endDate": request.travel_period.end_date.isoformat(),
        "days": [
            {
                "day": index,
                "date": value.isoformat(),
                "weekday": Weekday.from_weekday_index(value.weekday()).value,
            }
            for index, value in enumerate(request.travel_period.dates(), start=1)
        ],
    }


def build_candidate_block(candidates: list[PlaceCandidate]) -> list[dict[str, Any]]:
    """Trim candidates to the fields the planner may actually reason about."""

    fields = {
        "placeId",
        "name",
        "categories",
        "tags",
        "description",
        "openingHours",
        "closedDays",
        "closedDates",
        "estimatedStayMinutes",
        "estimatedCostPerPerson",
        "accessibility",
        "dietaryTags",
        "imageUrl",
        "sourceIds",
        "confidence",
    }
    payload: list[dict[str, Any]] = []
    for place in candidates:
        dumped = place.model_dump(by_alias=True, mode="json")
        payload.append({k: v for k, v in dumped.items() if k in fields})
    return payload
