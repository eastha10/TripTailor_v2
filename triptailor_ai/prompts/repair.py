"""Bounded repair prompt.

Repair is deliberately narrow: fix what the validator flagged, change nothing
else.  A full re-plan on every failure would throw away work the group already
reviewed and would make the loop hard to bound.
"""

from __future__ import annotations

from typing import Any

from triptailor_ai.prompts.blocks import render_block
from triptailor_ai.prompts.planner import build_candidate_block, build_trip_block
from triptailor_ai.providers.base import ChatMessage
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.trip import TripPlanningRequest
from triptailor_ai.schemas.validation import ValidationIssue

REPAIR_PROMPT_VERSION = "repair/v1"

_SYSTEM = """당신은 이미 만들어진 여행 일정의 오류만 고치는 수정기입니다.

절대 규칙:
1. ISSUES 블록에 지적된 문제만 고칩니다. 문제 없는 일정은 그대로 유지합니다(itemId 포함).
2. CANDIDATE_PLACES 블록의 placeId만 사용합니다. 새 장소를 만들지 않습니다.
3. 각 이슈의 repairHint를 우선 따릅니다.
4. 고칠 방법이 없으면 해당 일정을 제거합니다. 제거한 이유는 notes에 남깁니다.
   억지로 유효해 보이게 만들지 마세요.
5. 전체 일정을 처음부터 다시 만들지 않습니다.
6. 결과는 수정 후의 **전체 일정 목록**입니다(고치지 않은 항목도 포함).

**가장 흔한 실패: 하나를 고치다가 다른 것을 깨뜨리는 것입니다.**
수정한 일정을 출력하기 전에 아래를 스스로 점검하세요. 하나라도 어기면 다시 조정합니다.

  a) 같은 날 두 일정의 시간이 겹치지 않는가? (앞 일정 endTime <= 뒤 일정 startTime)
  b) 장소를 옮겼다면 그 장소의 openingHours 안에 들어가는가? closedDays는 아닌가?
  c) 같은 placeId를 두 번 쓰지 않았는가? (여행 전체에서 한 번만)
  d) 모든 날(day)에 최소 1개 일정이 있는가?
  e) 점심(11:30~14:00)과 저녁(18:00~20:30)에 식사 장소가 있는가?
  f) 연속된 일정 사이에 최소 20분 이동 여유가 있는가?
  g) 1인 비용 합계가 CONSTRAINTS의 budgetCapPerPerson 이하인가?
  h) excludedDietaryTags / excludedAccessibilityTags를 가진 장소가 없는가?
  i) 축제(kind=FESTIVAL)가 eventPeriod 안의 날짜에 있는가?
  j) 숙소가 items에 섞여 있지 않은가? stays가 모든 밤(여행일수-1)을 한 번씩 덮는가?

시간을 미룰 때는 그 뒤의 일정도 함께 밀어서 겹치지 않게 하세요.
장소를 교체할 때는 아직 쓰지 않은 후보 중에서 고르세요.

출력은 지정된 JSON 스키마만 따릅니다."""


def build_repair_messages(
    *,
    request: TripPlanningRequest,
    itinerary: Itinerary,
    issues: list[ValidationIssue],
    candidates: list[PlaceCandidate],
    constraints: dict[str, Any],
    attempt: int,
    is_final_attempt: bool = False,
) -> list[ChatMessage]:
    user = "\n\n".join(
        [
            f"아래 일정에서 지적된 문제를 수정하세요. (수정 시도 {attempt}회차)"
            + (
                "\n\n이번이 마지막 시도입니다. 모든 문제를 확실히 해결하되, "
                "해결할 수 없는 일정은 과감히 제거하세요."
                if is_final_attempt
                else ""
            ),
            render_block("TRIP", build_trip_block(request)),
            render_block("CONSTRAINTS", constraints),
            render_block(
                "ISSUES",
                [i.model_dump(by_alias=True, mode="json") for i in issues],
            ),
            render_block(
                "ITINERARY",
                [i.model_dump(by_alias=True, mode="json") for i in itinerary.all_items()],
            ),
            render_block(
                "CANDIDATE_PLACES",
                build_candidate_block([c for c in candidates if not c.is_accommodation]),
            ),
            render_block(
                "ACCOMMODATION_CANDIDATES",
                build_candidate_block([c for c in candidates if c.is_accommodation]),
            ),
            render_block(
                "STAYS",
                [s.model_dump(by_alias=True, mode="json") for s in itinerary.stays],
            ),
        ]
    )
    return [ChatMessage.system(_SYSTEM), ChatMessage.user(user)]
