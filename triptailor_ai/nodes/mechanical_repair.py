"""Deterministic repair for violations that need arithmetic, not judgement.

A real evaluation run showed 15 of 40 scenarios ending in ``NEEDS_INPUT``
because ``gpt-4o-mini`` could not clear ``DUPLICATE_PLACE`` and
``OUTSIDE_OPENING_HOURS`` inside the repair budget. Both are mechanical: a
duplicate is fixed by swapping in an unused candidate, and an out-of-hours stop
is fixed by moving it into the window. Asking a model to do that is slow,
costly and unreliable.

So this runs first. Whatever it cannot settle -- anything involving taste,
priority or trade-offs -- is left for the LLM repair node.

The pass only ever produces changes the validator can re-check; it never
suppresses an issue it did not actually fix.
"""

from __future__ import annotations

from datetime import date, time

from triptailor_ai.retrieval.base import RetrievalConstraints
from triptailor_ai.schemas.common import minutes_between, to_minutes
from triptailor_ai.schemas.itinerary import Itinerary, ItineraryDay, ItineraryItem
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.trip import TravelPeriod
from triptailor_ai.schemas.validation import ValidationCode, ValidationIssue

#: Codes this pass knows how to settle without a model.
MECHANICAL_CODES: frozenset[ValidationCode] = frozenset(
    {
        ValidationCode.PLACE_NOT_GROUNDED,
        ValidationCode.DUPLICATE_PLACE,
        ValidationCode.DUPLICATE_ITEM_ID,
        ValidationCode.INVALID_TIME_RANGE,
        ValidationCode.SCHEDULE_OVERLAP,
        ValidationCode.OUTSIDE_OPENING_HOURS,
        ValidationCode.PLACE_CLOSED,
        ValidationCode.DAY_DATE_MISMATCH,
        ValidationCode.OUTSIDE_TRAVEL_PERIOD,
    }
)

#: Minimum useful stay; below this a stop is dropped rather than squeezed.
MIN_STAY_MINUTES = 30
#: Gap left between consecutive stops when pushing one later.
TRANSFER_GAP_MINUTES = 20


def mechanical_repair(
    *,
    itinerary: Itinerary,
    issues: list[ValidationIssue],
    candidates: list[PlaceCandidate],
    travel_period: TravelPeriod,
    constraints: RetrievalConstraints | None = None,
    participant_count: int = 1,
) -> tuple[Itinerary, list[str]]:
    """Return a repaired itinerary and a log of what was changed.

    Idempotent: running it on an already-clean plan changes nothing.
    """

    by_place = {place.place_id: place for place in candidates}
    items = [item.model_copy(deep=True) for item in itinerary.all_items()]
    targeted = {
        item_id
        for issue in issues
        if issue.code in MECHANICAL_CODES
        for item_id in issue.item_ids
    }
    codes = {issue.code for issue in issues}
    log: list[str] = []

    items = _drop_ungrounded(items, by_place, log)
    items = _fix_dates(items, travel_period, codes, log)
    items = _fix_time_ranges(items, log)

    if ValidationCode.DUPLICATE_PLACE in codes:
        items = _replace_duplicates(items, by_place, constraints, log)
    if {ValidationCode.OUTSIDE_OPENING_HOURS, ValidationCode.PLACE_CLOSED} & codes:
        items = _fix_opening_hours(items, by_place, constraints, targeted, log)
    if ValidationCode.SCHEDULE_OVERLAP in codes:
        items = _fix_overlaps(items, log)

    return _rebuild(items, itinerary, participant_count), log


# --------------------------------------------------------------------------
def _drop_ungrounded(
    items: list[ItineraryItem], by_place: dict[str, PlaceCandidate], log: list[str]
) -> list[ItineraryItem]:
    kept = [item for item in items if item.place_id in by_place]
    for item in items:
        if item.place_id not in by_place:
            log.append(f"'{item.place_name}' 제거: 후보 목록에 없는 장소")
    return kept


def _fix_dates(
    items: list[ItineraryItem],
    period: TravelPeriod,
    codes: set[ValidationCode],
    log: list[str],
) -> list[ItineraryItem]:
    if not ({ValidationCode.DAY_DATE_MISMATCH, ValidationCode.OUTSIDE_TRAVEL_PERIOD} & codes):
        return items

    dates = period.dates()
    fixed: list[ItineraryItem] = []
    for item in items:
        if 1 <= item.day <= len(dates):
            expected = dates[item.day - 1]
            if item.date != expected:
                log.append(f"'{item.place_name}' 날짜 정정: {item.date} -> {expected}")
                item = item.model_copy(update={"date": expected})
            fixed.append(item)
        elif period.contains(item.date):
            day = dates.index(item.date) + 1
            log.append(f"'{item.place_name}' day 정정: {item.day} -> {day}")
            fixed.append(item.model_copy(update={"day": day}))
        else:
            log.append(f"'{item.place_name}' 제거: 여행 기간 밖({item.date})")
    return fixed


def _fix_time_ranges(items: list[ItineraryItem], log: list[str]) -> list[ItineraryItem]:
    fixed: list[ItineraryItem] = []
    for item in items:
        if minutes_between(item.start_time, item.end_time) > 0:
            fixed.append(item)
            continue
        end = _to_time(to_minutes(item.start_time) + 60)
        log.append(f"'{item.place_name}' 종료시각 정정: {item.end_time:%H:%M} -> {end:%H:%M}")
        fixed.append(item.model_copy(update={"end_time": end}))
    return fixed


def _replace_duplicates(
    items: list[ItineraryItem],
    by_place: dict[str, PlaceCandidate],
    constraints: RetrievalConstraints | None,
    log: list[str],
) -> list[ItineraryItem]:
    """Keep the first visit; swap later ones for unused candidates."""

    seen: set[str] = set()
    used = {item.place_id for item in items}
    result: list[ItineraryItem] = []

    for item in items:
        if item.place_id not in seen:
            seen.add(item.place_id)
            result.append(item)
            continue

        original = by_place.get(item.place_id)
        replacement = _find_substitute(
            wanted_meal=original.is_meal_place if original else False,
            day=item.date,
            start=to_minutes(item.start_time),
            duration=item.duration_minutes,
            by_place=by_place,
            used=used,
            constraints=constraints,
        )
        if replacement is None:
            log.append(f"'{item.place_name}' 중복 제거: 대체할 후보 없음")
            continue

        used.add(replacement.place_id)
        seen.add(replacement.place_id)
        log.append(f"'{item.place_name}' 중복 -> '{replacement.name}'으로 교체")
        result.append(
            item.model_copy(
                update={
                    "place_id": replacement.place_id,
                    "place_name": replacement.name,
                    "image_url": replacement.image_url,
                    "description": replacement.description,
                    "estimated_cost_per_person": replacement.estimated_cost_per_person,
                    "source_ids": replacement.source_ids,
                    "reason": "중복 배치를 피해 같은 성격의 다른 장소로 교체했습니다.",
                    "matched_preference_ids": [],
                }
            )
        )
    return result


def _find_substitute(
    *,
    wanted_meal: bool,
    day: date,
    start: int,
    duration: int,
    by_place: dict[str, PlaceCandidate],
    used: set[str],
    constraints: RetrievalConstraints | None,
) -> PlaceCandidate | None:
    banned_diet = {t.lower() for t in (constraints.excluded_dietary_tags if constraints else [])}
    banned_access = {
        t.lower() for t in (constraints.excluded_accessibility_tags if constraints else [])
    }

    for place in by_place.values():
        if place.place_id in used:
            continue
        if place.is_meal_place is not wanted_meal:
            continue
        if place.is_closed_on(day):
            continue
        if {t.lower() for t in place.dietary_tags} & banned_diet:
            continue
        if {t.lower() for t in place.accessibility} & banned_access:
            continue
        window = place.opening_window_on(day)
        if window is not None and not (window[0] <= start and start + duration <= window[1]):
            continue
        return place
    return None


def _fix_opening_hours(
    items: list[ItineraryItem],
    by_place: dict[str, PlaceCandidate],
    constraints: RetrievalConstraints | None,
    targeted: set[str],
    log: list[str],
) -> list[ItineraryItem]:
    used = {item.place_id for item in items}
    result: list[ItineraryItem] = []

    for item in items:
        place = by_place.get(item.place_id)
        if place is None or item.item_id not in targeted:
            result.append(item)
            continue

        if place.is_closed_on(item.date):
            replacement = _find_substitute(
                wanted_meal=place.is_meal_place,
                day=item.date,
                start=to_minutes(item.start_time),
                duration=item.duration_minutes,
                by_place=by_place,
                used=used,
                constraints=constraints,
            )
            if replacement is None:
                log.append(f"'{item.place_name}' 제거: 휴무일이고 대체 후보 없음")
                continue
            used.add(replacement.place_id)
            log.append(f"'{item.place_name}' 휴무 -> '{replacement.name}'으로 교체")
            result.append(
                item.model_copy(
                    update={
                        "place_id": replacement.place_id,
                        "place_name": replacement.name,
                        "estimated_cost_per_person": replacement.estimated_cost_per_person,
                        "reason": "휴무일 충돌로 다른 장소로 교체했습니다.",
                    }
                )
            )
            continue

        window = place.opening_window_on(item.date)
        if window is None:
            result.append(item)
            continue

        opens, closes = window
        start, end = to_minutes(item.start_time), to_minutes(item.end_time)
        if opens <= start and end <= closes:
            result.append(item)
            continue

        duration = min(max(end - start, MIN_STAY_MINUTES), closes - opens)
        new_start = min(max(start, opens), closes - duration)
        if duration < MIN_STAY_MINUTES or new_start < opens:
            log.append(f"'{item.place_name}' 제거: 영업시간 내에 배치 불가")
            continue

        log.append(
            f"'{item.place_name}' 시간 조정: "
            f"{item.start_time:%H:%M} -> {_to_time(new_start):%H:%M} (영업 {opens // 60:02d}:{opens % 60:02d}~{closes // 60:02d}:{closes % 60:02d})"
        )
        result.append(
            item.model_copy(
                update={
                    "start_time": _to_time(new_start),
                    "end_time": _to_time(new_start + duration),
                }
            )
        )
    return result


def _fix_overlaps(items: list[ItineraryItem], log: list[str]) -> list[ItineraryItem]:
    """Push later stops back until nothing on a day overlaps."""

    by_day: dict[int, list[ItineraryItem]] = {}
    for item in items:
        by_day.setdefault(item.day, []).append(item)

    result: list[ItineraryItem] = []
    for day in sorted(by_day):
        ordered = sorted(by_day[day], key=lambda i: (i.start_time, i.sequence))
        previous_end: int | None = None
        for item in ordered:
            start, end = to_minutes(item.start_time), to_minutes(item.end_time)
            if previous_end is not None and start < previous_end:
                shift = previous_end + TRANSFER_GAP_MINUTES
                duration = max(end - start, MIN_STAY_MINUTES)
                if shift + duration > 23 * 60 + 59:
                    log.append(f"'{item.place_name}' 제거: 겹침 해소 시 하루를 넘김")
                    continue
                log.append(
                    f"'{item.place_name}' 겹침 해소: "
                    f"{item.start_time:%H:%M} -> {_to_time(shift):%H:%M}"
                )
                item = item.model_copy(
                    update={
                        "start_time": _to_time(shift),
                        "end_time": _to_time(shift + duration),
                    }
                )
                start, end = shift, shift + duration
            previous_end = end
            result.append(item)
    return result


def _rebuild(
    items: list[ItineraryItem], original: Itinerary, participant_count: int
) -> Itinerary:
    by_day: dict[int, list[ItineraryItem]] = {}
    for item in items:
        by_day.setdefault(item.day, []).append(item)

    sequence = 0
    days: list[ItineraryDay] = []
    titles = {day.day: day.title for day in original.days}
    for day in sorted(by_day):
        entries = sorted(by_day[day], key=lambda i: (i.start_time, i.sequence))
        renumbered: list[ItineraryItem] = []
        for entry in entries:
            sequence += 1
            renumbered.append(entry.model_copy(update={"sequence": sequence}))
        days.append(
            ItineraryDay(
                day=day, date=renumbered[0].date, items=renumbered, title=titles.get(day)
            )
        )

    repaired = original.model_copy(update={"days": days})
    repaired.recompute_costs(participant_count)
    return repaired


def _to_time(minutes: int) -> time:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return time(hour=minutes // 60, minute=minutes % 60)
