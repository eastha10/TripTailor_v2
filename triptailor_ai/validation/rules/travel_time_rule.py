"""Gaps between consecutive stops must cover the known travel time.

Without a travel-time provider this rule reports every transfer as
``TRAVEL_TIME_UNVERIFIED``.  That is the point: an unrouted plan is not a
validated plan.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.common import to_minutes
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class TravelTimeRule(Rule):
    rule_id = "travel_time"
    description = "연속된 일정 사이 여유 시간이 실제 이동시간 이상이어야 한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        buffer_minutes = context.settings.travel_time_buffer_minutes
        unverified: list[str] = []

        for day in context.itinerary.days:
            ordered = sorted(day.items, key=lambda i: (i.start_time, i.sequence))
            for previous, current in zip(ordered, ordered[1:]):
                estimate = context.travel_times.get((previous.place_id, current.place_id))
                available = to_minutes(current.start_time) - to_minutes(previous.end_time)

                if estimate is None or estimate.minutes is None:
                    unverified.append(current.item_id)
                    continue

                required = estimate.minutes + buffer_minutes
                if available >= required:
                    continue

                yield issue(
                    ValidationCode.INSUFFICIENT_TRAVEL_TIME,
                    Severity.ERROR,
                    f"day {day.day}: '{previous.place_name}' → '{current.place_name}' 이동에 "
                    f"{estimate.minutes}분(+여유 {buffer_minutes}분)이 필요한데 "
                    f"{available}분만 있습니다.",
                    rule_id=self.rule_id,
                    item_ids=[previous.item_id, current.item_id],
                    evidence={
                        "day": day.day,
                        "travelMinutes": estimate.minutes,
                        "bufferMinutes": buffer_minutes,
                        "availableMinutes": available,
                        "shortfallMinutes": required - available,
                        "verificationStatus": estimate.verification_status.value,
                    },
                    repair_hint=(
                        f"'{current.place_name}' 시작을 최소 {required - available}분 뒤로 "
                        "미루거나 더 가까운 장소로 교체하세요."
                    ),
                )

        if unverified:
            yield issue(
                ValidationCode.TRAVEL_TIME_UNVERIFIED,
                Severity.WARNING,
                f"이동시간 데이터가 없어 {len(unverified)}개 구간의 이동 가능 여부를 확인하지 못했습니다.",
                rule_id=self.rule_id,
                item_ids=unverified,
                evidence={"unverifiedSegmentCount": len(unverified)},
            )
