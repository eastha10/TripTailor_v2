"""A festival may only be scheduled on a date it actually runs.

Without this a plan can send the group to a flower festival three months after
it ended, and every other check would pass -- the place is grounded, open, and
inside the travel period. Only the event dates say otherwise.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class EventPeriodRule(Rule):
    rule_id = "event_period"
    description = "축제/행사는 실제 운영 기간 내 날짜에만 배치되어야 한다"

    def is_applicable(self, context: ValidationContext) -> bool:
        return any(
            (place := context.place_for(item.place_id)) is not None and place.is_festival
            for item in context.itinerary.all_items()
        )

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        unverified: list[str] = []

        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is None or not place.is_festival:
                continue

            runs = place.runs_on(item.date)
            if runs is None:
                unverified.append(item.item_id)
                continue
            if runs:
                continue

            period = place.event_period
            yield issue(
                ValidationCode.OUTSIDE_EVENT_PERIOD,
                Severity.ERROR,
                f"'{place.name}'은(는) {period.start_date}~{period.end_date} 기간에만 "
                f"열리는데 {item.date}에 배치되었습니다.",
                rule_id=self.rule_id,
                item_ids=[item.item_id],
                evidence={
                    "placeId": place.place_id,
                    "date": item.date.isoformat(),
                    "eventStartDate": period.start_date.isoformat(),
                    "eventEndDate": period.end_date.isoformat(),
                },
                repair_hint=(
                    f"'{place.name}'을(를) {period.start_date}~{period.end_date} 안의 "
                    "여행 날짜로 옮기거나, 겹치는 날이 없으면 일정에서 제거하세요."
                ),
            )

        if unverified:
            yield issue(
                ValidationCode.EVENT_PERIOD_UNVERIFIED,
                Severity.WARNING,
                f"행사 기간 정보가 없어 {len(unverified)}개 일정의 개최 여부를 확인하지 못했습니다.",
                rule_id=self.rule_id,
                item_ids=unverified,
                evidence={"unverifiedItemCount": len(unverified)},
            )
