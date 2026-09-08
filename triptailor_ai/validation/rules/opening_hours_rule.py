"""Opening hours and closed days.

Missing data yields ``OPENING_HOURS_UNVERIFIED`` (a warning), never a silent
pass.  The reviewer can then see exactly which stops were never checked.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.common import Weekday, to_minutes
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class OpeningHoursRule(Rule):
    rule_id = "opening_hours"
    description = "영업시간/휴무일 데이터가 있으면 그 안에 일정이 들어가야 한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        unverified: list[str] = []

        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is None:
                # PlaceGroundingRule owns this failure.
                continue

            weekday = Weekday.from_weekday_index(item.date.weekday())

            if place.is_closed_on(item.date):
                yield issue(
                    ValidationCode.PLACE_CLOSED,
                    Severity.ERROR,
                    f"'{place.name}'은(는) {item.date}({weekday.value})에 휴무입니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={
                        "placeId": place.place_id,
                        "date": item.date.isoformat(),
                        "weekday": weekday.value,
                        "closedDays": [d.value for d in place.closed_days],
                        "closedDates": [d.isoformat() for d in place.closed_dates],
                    },
                    repair_hint="다른 날짜로 옮기거나 영업 중인 다른 장소로 교체하세요.",
                )
                continue

            if place.opening_hours is None:
                unverified.append(item.item_id)
                continue

            intervals = place.opening_hours.intervals_for(weekday)
            if not intervals:
                unverified.append(item.item_id)
                continue

            start, end = to_minutes(item.start_time), to_minutes(item.end_time)
            fits = any(
                to_minutes(window.open) <= start and end <= to_minutes(window.close)
                for window in intervals
            )
            if fits:
                continue

            windows = [
                f"{w.open:%H:%M}-{w.close:%H:%M}" for w in intervals
            ]
            yield issue(
                ValidationCode.OUTSIDE_OPENING_HOURS,
                Severity.ERROR,
                f"'{place.name}' 일정({item.start_time:%H:%M}~{item.end_time:%H:%M})이 "
                f"{weekday.value} 영업시간({', '.join(windows)}) 밖입니다.",
                rule_id=self.rule_id,
                item_ids=[item.item_id],
                evidence={
                    "placeId": place.place_id,
                    "weekday": weekday.value,
                    "openingWindows": windows,
                    "startTime": item.start_time.strftime("%H:%M"),
                    "endTime": item.end_time.strftime("%H:%M"),
                },
                repair_hint=(
                    f"'{place.name}' 방문 시간을 {windows[0]} 범위 안으로 조정하거나 "
                    "다른 장소로 교체하세요."
                ),
            )

        if unverified:
            yield issue(
                ValidationCode.OPENING_HOURS_UNVERIFIED,
                Severity.WARNING,
                f"영업시간 데이터가 없어 {len(unverified)}개 일정의 운영 여부를 확인하지 못했습니다.",
                rule_id=self.rule_id,
                item_ids=unverified,
                evidence={"unverifiedItemCount": len(unverified)},
                repair_hint=None,
            )
