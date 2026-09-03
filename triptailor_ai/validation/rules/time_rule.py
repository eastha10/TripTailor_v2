"""startTime must precede endTime."""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.common import minutes_between
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class TimeRangeRule(Rule):
    rule_id = "time_range"
    description = "각 일정의 startTime < endTime 이어야 한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        for item in context.itinerary.all_items():
            duration = minutes_between(item.start_time, item.end_time)
            if duration > 0:
                continue
            yield issue(
                ValidationCode.INVALID_TIME_RANGE,
                Severity.ERROR,
                f"'{item.place_name}'의 시간이 잘못되었습니다 "
                f"({item.start_time:%H:%M} ~ {item.end_time:%H:%M}).",
                rule_id=self.rule_id,
                item_ids=[item.item_id],
                evidence={
                    "startTime": item.start_time.strftime("%H:%M"),
                    "endTime": item.end_time.strftime("%H:%M"),
                    "durationMinutes": duration,
                },
                repair_hint="endTime을 startTime 이후로 수정하세요. 자정을 넘기는 일정은 지원하지 않습니다.",
            )
