"""Dates must fall inside the travel period, match their day number, and
every travel day must actually have something planned.

A local 7B model returned a three-day trip with only day 1 filled and it came
back ``isValid: true``, because an unplanned day was merely a warning. Two
empty days out of three is not a light schedule -- it is a missing plan.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class DateRule(Rule):
    rule_id = "date"
    description = "일정 날짜가 여행 기간 내에 있고 day 번호와 일치해야 한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        period = context.request.travel_period
        expected = period.dates()

        for item in context.itinerary.all_items():
            if not period.contains(item.date):
                yield issue(
                    ValidationCode.OUTSIDE_TRAVEL_PERIOD,
                    Severity.ERROR,
                    f"{item.date} 일정이 여행 기간({period.start_date}~{period.end_date}) 밖입니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={
                        "date": item.date.isoformat(),
                        "startDate": period.start_date.isoformat(),
                        "endDate": period.end_date.isoformat(),
                    },
                    repair_hint="여행 기간 내 날짜로 옮기거나 일정을 제거하세요.",
                )
                continue

            if 1 <= item.day <= len(expected) and expected[item.day - 1] != item.date:
                yield issue(
                    ValidationCode.DAY_DATE_MISMATCH,
                    Severity.ERROR,
                    f"day {item.day}의 날짜는 {expected[item.day - 1]}이어야 하는데 {item.date}입니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={
                        "day": item.day,
                        "date": item.date.isoformat(),
                        "expectedDate": expected[item.day - 1].isoformat(),
                    },
                    repair_hint=f"date를 {expected[item.day - 1]}로 수정하세요.",
                )
            elif not 1 <= item.day <= len(expected):
                yield issue(
                    ValidationCode.DAY_DATE_MISMATCH,
                    Severity.ERROR,
                    f"day {item.day}는 여행 일수(1~{len(expected)}) 범위를 벗어납니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={"day": item.day, "dayCount": len(expected)},
                    repair_hint=f"day를 1~{len(expected)} 사이 값으로 수정하세요.",
                )

        duplicates = [
            item_id
            for item_id, count in Counter(i.item_id for i in context.itinerary.all_items()).items()
            if count > 1
        ]
        if duplicates:
            yield issue(
                ValidationCode.DUPLICATE_ITEM_ID,
                Severity.ERROR,
                f"itemId가 중복되었습니다: {', '.join(duplicates)}",
                rule_id=self.rule_id,
                item_ids=duplicates,
                evidence={"duplicateItemIds": duplicates},
                repair_hint="각 일정 항목에 고유한 itemId를 부여하세요.",
            )

        yield from self._empty_days(context, len(expected))

    def _empty_days(
        self, context: ValidationContext, day_count: int
    ) -> Iterable[ValidationIssue]:
        items = context.itinerary.all_items()
        scheduled_days = {item.day for item in items}
        empty = [d for d in range(1, day_count + 1) if d not in scheduled_days]
        if not empty:
            return

        used_places = {item.place_id for item in items}
        unused = [p for p in context.candidates if p not in used_places]
        # Same rule as elsewhere: only fail for something that can be fixed.
        fixable = len(unused) >= len(empty)

        for day in empty:
            yield issue(
                ValidationCode.EMPTY_DAY,
                Severity.ERROR if fixable else Severity.WARNING,
                f"day {day}에 배치된 일정이 없습니다.",
                rule_id=self.rule_id,
                evidence={
                    "day": day,
                    "emptyDays": empty,
                    "dayCount": day_count,
                    "unusedCandidateCount": len(unused),
                },
                repair_hint=(
                    f"day {day}에 아직 사용하지 않은 후보 장소로 최소 1개 일정을 배치하세요."
                    if fixable
                    else f"day {day}를 채울 후보 장소가 부족합니다."
                ),
            )
