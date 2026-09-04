"""Day-shape checks: meals and workload.

One evening left free is a plan.  *Every* evening left free is a planning
failure -- and a real model does exactly that if you only ask it nicely in the
prompt, so the check has to be deterministic rather than trusting compliance.

The escalation is deliberately conditional: a systematically missing meal is an
ERROR only when the candidate set actually contains somewhere to eat. If the
data cannot support a dinner, failing the plan would just spin the repair loop
against a wall, so it stays a warning.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.common import to_minutes
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue




class DailyLoadRule(Rule):
    rule_id = "daily_load"
    description = "하루 일정량과 식사 시간대 확보 여부를 경고한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        settings = context.settings

        for day in context.itinerary.days:
            if not day.items:
                continue

            scheduled = sum(i.duration_minutes for i in day.items if i.duration_minutes > 0)
            if scheduled > settings.max_daily_scheduled_minutes:
                yield issue(
                    ValidationCode.EXCESSIVE_DAILY_LOAD,
                    Severity.WARNING,
                    f"day {day.day}의 일정 시간이 {scheduled // 60}시간 {scheduled % 60}분으로 과합니다.",
                    rule_id=self.rule_id,
                    item_ids=[i.item_id for i in day.items],
                    evidence={
                        "day": day.day,
                        "scheduledMinutes": scheduled,
                        "limitMinutes": settings.max_daily_scheduled_minutes,
                    },
                    repair_hint=f"day {day.day}에서 일정 1~2개를 줄이세요.",
                )

            if len(day.items) > settings.max_items_per_day:
                yield issue(
                    ValidationCode.EXCESSIVE_DAILY_LOAD,
                    Severity.WARNING,
                    f"day {day.day}에 일정이 {len(day.items)}개로 너무 많습니다.",
                    rule_id=self.rule_id,
                    item_ids=[i.item_id for i in day.items],
                    evidence={"day": day.day, "itemCount": len(day.items)},
                    repair_hint=f"day {day.day}의 일정을 {settings.max_items_per_day}개 이하로 줄이세요.",
                )

        yield from self._meal_coverage(context)
        yield from self._stay_durations(context)

    def _meal_coverage(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        settings = context.settings
        days = [day for day in context.itinerary.days if day.items]
        if not days:
            return

        meal_candidates = [
            place for place in context.candidates.values() if self._is_meal_place(place)
        ]

        for label, window in (
            ("점심", settings.lunch_window_minutes),
            ("저녁", settings.dinner_window_minutes),
        ):
            missing = [day for day in days if not self._covers(day.items, window)]
            if not missing:
                continue

            missing_days = [day.day for day in missing]
            systematic = len(missing) == len(days)
            fixable = bool(meal_candidates)

            if systematic and fixable:
                # Not a stylistic choice: the plan simply has no meals.
                yield issue(
                    ValidationCode.MISSING_MEAL_SLOT,
                    Severity.ERROR,
                    f"모든 날({', '.join(f'day {d}' for d in missing_days)})에 "
                    f"{label} 시간대 일정이 없습니다. 식사가 빠진 일정입니다.",
                    rule_id=self.rule_id,
                    evidence={
                        "meal": label,
                        "affectedDays": missing_days,
                        "dayCount": len(days),
                        "systematic": True,
                        "windowMinutes": list(window),
                        "mealCandidateCount": len(meal_candidates),
                    },
                    repair_hint=(
                        f"각 날짜의 {label} 시간대"
                        f"({window[0] // 60:02d}:{window[0] % 60:02d}~"
                        f"{window[1] // 60:02d}:{window[1] % 60:02d})에 "
                        "식당/카페 후보를 하나씩 배치하세요. 사용 가능한 후보 예: "
                        + ", ".join(p.name for p in meal_candidates[:5])
                    ),
                )
                continue

            for day in missing:
                yield issue(
                    ValidationCode.MISSING_MEAL_SLOT,
                    Severity.WARNING,
                    f"day {day.day}에 {label} 시간대 일정이 없습니다.",
                    rule_id=self.rule_id,
                    evidence={
                        "day": day.day,
                        "meal": label,
                        "systematic": systematic,
                        "mealCandidateCount": len(meal_candidates),
                        "windowMinutes": list(window),
                    },
                    repair_hint=f"day {day.day}의 {label} 시간대에 식사 일정을 추가하세요.",
                )

    @staticmethod
    def _stay_durations(context: ValidationContext) -> Iterable[ValidationIssue]:
        """Scheduled time wildly exceeding the place's own estimate.

        A model with nothing better to do will stretch stops to fill the day --
        four hours at a barbecue restaurant, for instance. The candidate data
        already carries ``estimatedStayMinutes``, so this is checkable rather
        than a matter of taste. Warning only: the estimate is a guide, and a
        group really may linger.
        """

        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is None or not place.estimated_stay_minutes:
                continue
            scheduled = item.duration_minutes
            expected = place.estimated_stay_minutes
            if scheduled <= max(expected * 2, expected + 60):
                continue
            yield issue(
                ValidationCode.IMPLAUSIBLE_STAY_DURATION,
                Severity.WARNING,
                f"'{place.name}'에 {scheduled // 60}시간 {scheduled % 60}분을 배정했습니다. "
                f"권장 체류 시간은 {expected}분입니다.",
                rule_id="daily_load",
                item_ids=[item.item_id],
                evidence={
                    "placeId": place.place_id,
                    "scheduledMinutes": scheduled,
                    "estimatedStayMinutes": expected,
                },
                repair_hint=(
                    f"'{place.name}' 체류를 {expected}분 수준으로 줄이고 "
                    "남는 시간에 다른 일정을 배치하세요."
                ),
            )

    @staticmethod
    def _is_meal_place(place) -> bool:  # noqa: ANN001 - PlaceCandidate
        return place.is_meal_place

    @staticmethod
    def _covers(items, window: tuple[int, int]) -> bool:  # noqa: ANN001
        start, end = window
        return any(
            to_minutes(item.start_time) < end and to_minutes(item.end_time) > start
            for item in items
        )
