"""Accommodation is a night, and every night has exactly one of them.

Modelled as an ordinary stop, a hotel could be scheduled three times on one
afternoon and not at all on the night in between -- nothing in the other rules
would object, because as a *stop* it is perfectly valid.

The checks here are conditional in the same way as the rest: a missing night is
an ERROR only when the candidate set actually contains somewhere to sleep.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class AccommodationRule(Rule):
    rule_id = "accommodation"
    description = "숙박은 stop이 아니라 박 단위이며, 모든 밤을 정확히 한 번씩 덮어야 한다"

    def is_applicable(self, context: ValidationContext) -> bool:
        return bool(context.itinerary.all_items()) or bool(context.itinerary.stays)

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        yield from self._not_scheduled_as_stops(context)
        yield from self._grounded(context)
        yield from self._inside_travel_period(context)
        yield from self._one_per_night(context)

    # ---- accommodation must not appear among the day's stops --------------
    def _not_scheduled_as_stops(
        self, context: ValidationContext
    ) -> Iterable[ValidationIssue]:
        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is None or not place.is_accommodation:
                continue
            yield issue(
                ValidationCode.ACCOMMODATION_AS_STOP,
                Severity.ERROR,
                f"'{place.name}'은(는) 숙소인데 일반 일정으로 배치되었습니다.",
                rule_id=self.rule_id,
                item_ids=[item.item_id],
                evidence={"placeId": place.place_id, "date": item.date.isoformat()},
                repair_hint=(
                    f"'{place.name}'을(를) items에서 빼고 stays에 "
                    "checkInDate/checkOutDate로 등록하세요."
                ),
            )

    def _grounded(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        for stay in context.itinerary.stays:
            if context.place_for(stay.place_id) is None:
                yield issue(
                    ValidationCode.PLACE_NOT_GROUNDED,
                    Severity.ERROR,
                    f"숙소 '{stay.place_name}'(placeId={stay.place_id})는 후보 목록에 없습니다.",
                    rule_id=self.rule_id,
                    evidence={"placeId": stay.place_id, "stayId": stay.stay_id},
                    repair_hint="후보 목록의 숙소 placeId로 교체하세요.",
                )

    def _inside_travel_period(
        self, context: ValidationContext
    ) -> Iterable[ValidationIssue]:
        period = context.request.travel_period
        for stay in context.itinerary.stays:
            outside = [n for n in stay.nights_covered() if not period.contains(n)]
            if not outside:
                continue
            yield issue(
                ValidationCode.STAY_OUTSIDE_TRAVEL_PERIOD,
                Severity.ERROR,
                f"숙소 '{stay.place_name}'의 숙박일({', '.join(str(d) for d in outside)})이 "
                f"여행 기간({period.start_date}~{period.end_date}) 밖입니다.",
                rule_id=self.rule_id,
                evidence={
                    "stayId": stay.stay_id,
                    "outsideNights": [d.isoformat() for d in outside],
                },
                repair_hint="체크인/체크아웃 날짜를 여행 기간 안으로 맞추세요.",
            )

    # ---- exactly one stay per night --------------------------------------
    def _one_per_night(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        period = context.request.travel_period
        # The last day is a departure day: a 3-day trip has 2 nights.
        nights = period.dates()[:-1]
        if not nights:
            return

        has_candidates = any(p.is_accommodation for p in context.candidates.values())

        for night in nights:
            covering = [s for s in context.itinerary.stays if s.covers(night)]
            if len(covering) > 1:
                yield issue(
                    ValidationCode.OVERLAPPING_STAY,
                    Severity.ERROR,
                    f"{night} 밤에 숙소가 {len(covering)}곳 배정되었습니다: "
                    + ", ".join(s.place_name for s in covering),
                    rule_id=self.rule_id,
                    evidence={
                        "night": night.isoformat(),
                        "placeIds": [s.place_id for s in covering],
                    },
                    repair_hint=f"{night} 밤에는 숙소를 하나만 남기세요.",
                )
            elif not covering:
                yield issue(
                    ValidationCode.MISSING_ACCOMMODATION,
                    Severity.ERROR if has_candidates else Severity.WARNING,
                    f"{night} 밤에 배정된 숙소가 없습니다.",
                    rule_id=self.rule_id,
                    evidence={
                        "night": night.isoformat(),
                        "accommodationCandidateCount": sum(
                            1 for p in context.candidates.values() if p.is_accommodation
                        ),
                    },
                    repair_hint=(
                        f"{night} 밤을 덮는 숙소를 stays에 추가하세요."
                        if has_candidates
                        else "후보 중 숙소가 없어 배정할 수 없습니다. 숙소 검색이 필요합니다."
                    ),
                )
