"""Two stops on the same day may not occupy the same clock time."""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.common import to_minutes
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class OverlapRule(Rule):
    rule_id = "overlap"
    description = "같은 날 일정의 시간대가 겹치면 안 된다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        for day in context.itinerary.days:
            ordered = sorted(day.items, key=lambda i: (i.start_time, i.end_time))
            for previous, current in zip(ordered, ordered[1:]):
                overlap = to_minutes(previous.end_time) - to_minutes(current.start_time)
                if overlap <= 0:
                    continue
                yield issue(
                    ValidationCode.SCHEDULE_OVERLAP,
                    Severity.ERROR,
                    f"day {day.day}에서 '{previous.place_name}'과 '{current.place_name}'의 "
                    f"시간이 {overlap}분 겹칩니다.",
                    rule_id=self.rule_id,
                    item_ids=[previous.item_id, current.item_id],
                    evidence={
                        "day": day.day,
                        "overlapMinutes": overlap,
                        "shortfallMinutes": overlap,
                        "previousEnd": previous.end_time.strftime("%H:%M"),
                        "currentStart": current.start_time.strftime("%H:%M"),
                    },
                    repair_hint=(
                        f"'{current.place_name}'의 시작 시각을 "
                        f"{previous.end_time:%H:%M} 이후로 옮기세요."
                    ),
                )
