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

from datetime import date, time, timedelta

from triptailor_ai.retrieval.base import RetrievalConstraints
from triptailor_ai.schemas.common import minutes_between, to_minutes
from triptailor_ai.schemas.itinerary import (
    AccommodationStay,
    Itinerary,
    ItineraryDay,
    ItineraryItem,
)
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
        ValidationCode.OUTSIDE_EVENT_PERIOD,
        ValidationCode.ACCOMMODATION_AS_STOP,
        ValidationCode.MISSING_ACCOMMODATION,
        ValidationCode.OVERLAPPING_STAY,
        ValidationCode.BUDGET_EXCEEDED,
    }
)

#: Minimum useful stay; below this a stop is dropped rather than squeezed.
MIN_STAY_MINUTES = 30
#: Gap left between consecutive stops when pushing one later.
TRANSFER_GAP_MINUTES = 20
#: How many times the hours/overlap pair may alternate before giving up.
MAX_SETTLE_PASSES = 4


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
    codes = {issue.code for issue in issues}
    log: list[str] = []

    items = _drop_ungrounded(items, by_place, log)
    items = _fix_dates(items, travel_period, codes, log)
    items = _fix_time_ranges(items, log)

    if ValidationCode.DUPLICATE_PLACE in codes:
        items = _replace_duplicates(items, by_place, constraints, log)
    if ValidationCode.OUTSIDE_EVENT_PERIOD in codes:
        items = _fix_event_dates(items, by_place, travel_period, log)

    # Moving a stop into its opening window can push it onto a neighbour, and
    # pushing a stop later can push it out of its window. Fixing either once
    # leaves the other broken -- three real scenarios came back from two full
    # repair turns still holding OUTSIDE_OPENING_HOURS or SCHEDULE_OVERLAP for
    # exactly this reason. So the pair runs to a fixed point instead.
    items = _settle_times(items, by_place, constraints, log)

    stays = list(itinerary.stays)
    if {
        ValidationCode.ACCOMMODATION_AS_STOP,
        ValidationCode.MISSING_ACCOMMODATION,
        ValidationCode.OVERLAPPING_STAY,
    } & codes:
        items, stays = _fix_accommodation(
            items, stays, by_place, travel_period, constraints, log
        )

    if ValidationCode.BUDGET_EXCEEDED in codes:
        stays = _downgrade_accommodation(
            stays, items, issues, by_place, constraints, log
        )

    return _rebuild(items, itinerary, participant_count, stays), log


def _downgrade_accommodation(
    stays: list[AccommodationStay],
    items: list[ItineraryItem],
    issues: list[ValidationIssue],
    by_place: dict[str, PlaceCandidate],
    constraints: RetrievalConstraints | None,
    log: list[str],
) -> list[AccommodationStay]:
    """Swap the hotel for a cheaper one when that alone closes the gap.

    Deciding *which activity to give up* is a judgement call and stays with the
    LLM. Picking the cheapest room that still satisfies the hard constraints is
    arithmetic -- and a real gpt-4o-mini run chose a 90,000원/night pension on a
    200,000원 total budget, then failed to walk it back in two repair turns.
    """

    overrun = next(
        (i for i in issues if i.code is ValidationCode.BUDGET_EXCEEDED), None
    )
    if overrun is None or not stays:
        return stays

    cap = overrun.evidence.get("budgetCapPerPerson")
    if not isinstance(cap, int):
        return stays

    stop_cost = sum(i.estimated_cost_per_person or 0 for i in items)
    banned = {
        t.lower() for t in (constraints.excluded_accessibility_tags if constraints else [])
    }
    options = sorted(
        (
            p
            for p in by_place.values()
            if p.is_accommodation
            and p.price_per_night_per_person is not None
            and not ({t.lower() for t in p.accessibility} & banned)
        ),
        key=lambda p: p.price_per_night_per_person or 0,
    )
    if not options:
        return stays

    nights = sum(s.nights for s in stays)
    cheapest = options[0]
    if (cheapest.price_per_night_per_person or 0) * nights + stop_cost > cap:
        # Even the cheapest room does not fit; this is a real trade-off, so
        # leave it for the model rather than pretending it is solved.
        return stays

    current = sum(s.total_cost_per_person or 0 for s in stays)
    # Best room that still fits, not merely the cheapest.
    affordable = [
        p
        for p in options
        if (p.price_per_night_per_person or 0) * nights + stop_cost <= cap
    ]
    chosen = affordable[-1]
    if (chosen.price_per_night_per_person or 0) * nights >= current:
        return stays

    log.append(
        f"예산 초과: 숙소를 '{stays[0].place_name}'에서 '{chosen.name}'로 교체 "
        f"(1인 {current:,}원 -> {(chosen.price_per_night_per_person or 0) * nights:,}원)"
    )
    return [
        stay.model_copy(
            update={
                "place_id": chosen.place_id,
                "place_name": chosen.name,
                "price_per_night_per_person": chosen.price_per_night_per_person,
                "image_url": chosen.image_url,
                "reason": "예산 상한에 맞춰 더 저렴한 숙소로 교체했습니다.",
                "matched_preference_ids": [],
            }
        )
        for stay in stays
    ]


def _fix_event_dates(
    items: list[ItineraryItem],
    by_place: dict[str, PlaceCandidate],
    period: TravelPeriod,
    log: list[str],
) -> list[ItineraryItem]:
    """Move a festival onto a trip date it actually runs, or drop it."""

    dates = period.dates()
    result: list[ItineraryItem] = []
    for item in items:
        place = by_place.get(item.place_id)
        if place is None or not place.is_festival or place.event_period is None:
            result.append(item)
            continue
        if place.event_period.contains(item.date):
            result.append(item)
            continue

        usable = [d for d in dates if place.event_period.contains(d)]
        if not usable:
            log.append(f"'{place.name}' 제거: 여행 기간과 겹치는 개최일 없음")
            continue
        new_date = usable[0]
        log.append(f"'{place.name}' 날짜 이동: {item.date} -> {new_date} (개최 기간 내)")
        result.append(
            item.model_copy(
                update={"date": new_date, "day": dates.index(new_date) + 1}
            )
        )
    return result


def _fix_accommodation(
    items: list[ItineraryItem],
    stays: list[AccommodationStay],
    by_place: dict[str, PlaceCandidate],
    period: TravelPeriod,
    constraints: RetrievalConstraints | None,
    log: list[str],
) -> tuple[list[ItineraryItem], list[AccommodationStay]]:
    """Pull hotels out of the day's stops, then make the nights line up."""

    kept_items: list[ItineraryItem] = []
    promoted: list[AccommodationStay] = []
    for item in items:
        place = by_place.get(item.place_id)
        if place is None or not place.is_accommodation:
            kept_items.append(item)
            continue
        # A hotel scheduled as a stop is a night that was modelled wrongly, so
        # convert it rather than discarding the model's choice of hotel.
        check_in = item.date
        if not period.contains(check_in) or check_in >= period.end_date:
            log.append(f"'{place.name}' 제거: 숙박 가능한 날짜가 아님")
            continue
        promoted.append(
            AccommodationStay(
                place_id=place.place_id,
                place_name=place.name,
                check_in_date=check_in,
                check_out_date=check_in + timedelta(days=1),
                price_per_night_per_person=place.price_per_night_per_person,
                reason="일반 일정으로 잡혀 있던 숙소를 숙박으로 옮겼습니다.",
            )
        )
        log.append(f"'{place.name}' 일정 -> 숙박({check_in} 1박)으로 이동")

    merged = _dedupe_nights(stays + promoted, period, log)
    merged = _fill_missing_nights(merged, by_place, period, constraints, log)
    return kept_items, merged


def _dedupe_nights(
    stays: list[AccommodationStay], period: TravelPeriod, log: list[str]
) -> list[AccommodationStay]:
    """Keep one stay per night; split any that overlap an already-taken night."""

    taken: dict[date, AccommodationStay] = {}
    for stay in sorted(stays, key=lambda s: (s.check_in_date, s.stay_id)):
        for night in stay.nights_covered():
            if not period.contains(night) or night >= period.end_date:
                continue
            if night in taken:
                log.append(
                    f"{night} 밤 중복: '{stay.place_name}' 대신 "
                    f"'{taken[night].place_name}' 유지"
                )
                continue
            taken[night] = stay
    return _merge_runs(taken)


def _fill_missing_nights(
    stays: list[AccommodationStay],
    by_place: dict[str, PlaceCandidate],
    period: TravelPeriod,
    constraints: RetrievalConstraints | None,
    log: list[str],
) -> list[AccommodationStay]:
    """Book an unused accommodation candidate for any uncovered night."""

    nights = period.dates()[:-1]
    covered = {n for s in stays for n in s.nights_covered()}
    missing = [n for n in nights if n not in covered]
    if not missing:
        return stays

    banned = {t.lower() for t in (constraints.excluded_accessibility_tags if constraints else [])}
    used = {s.place_id for s in stays}
    options = sorted(
        (
            p
            for p in by_place.values()
            if p.is_accommodation
            and p.place_id not in used
            and not ({t.lower() for t in p.accessibility} & banned)
        ),
        # Cheapest first: an unbooked night is filled without blowing the cap.
        key=lambda p: p.price_per_night_per_person or 0,
    )

    taken = {n: s for s in stays for n in s.nights_covered()}
    # Reuse one place across the uncovered nights: moving hotel every night is
    # not a plan anyone asked for, and _merge_runs then collapses them.
    place = options[0] if options else None
    for night in missing:
        if place is None:
            log.append(f"{night} 밤: 배정할 숙소 후보가 없음")
            continue
        taken[night] = AccommodationStay(
            place_id=place.place_id,
            place_name=place.name,
            check_in_date=night,
            check_out_date=night + timedelta(days=1),
            price_per_night_per_person=place.price_per_night_per_person,
            reason="비어 있던 밤에 숙소를 배정했습니다.",
        )
        log.append(f"{night} 밤: '{place.name}' 배정")
    return _merge_runs(taken)


def _merge_runs(by_night: dict[date, AccommodationStay]) -> list[AccommodationStay]:
    """Collapse consecutive nights at the same place into one stay."""

    merged: list[AccommodationStay] = []
    for night in sorted(by_night):
        stay = by_night[night]
        if merged and merged[-1].place_id == stay.place_id and (
            merged[-1].check_out_date == night
        ):
            merged[-1] = merged[-1].model_copy(
                update={"check_out_date": night + timedelta(days=1)}
            )
            continue
        merged.append(
            stay.model_copy(
                update={
                    "stay_id": "",
                    "check_in_date": night,
                    "check_out_date": night + timedelta(days=1),
                }
            )
        )
    return merged


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


def _settle_times(
    items: list[ItineraryItem],
    by_place: dict[str, PlaceCandidate],
    constraints: RetrievalConstraints | None,
    log: list[str],
) -> list[ItineraryItem]:
    """Alternate the hours and overlap fixes until nothing more changes.

    Both are idempotent on a clean plan, so this is a no-op when there is
    nothing to settle. Bounded because the two can, in a tight schedule, keep
    trading places -- at which point the remaining conflict is a real one and
    belongs to the LLM stage.
    """

    def fingerprint(entries: list[ItineraryItem]) -> tuple:
        return tuple(
            (i.item_id, i.place_id, i.date, i.start_time, i.end_time) for i in entries
        )

    for _ in range(MAX_SETTLE_PASSES):
        before = fingerprint(items)
        items = _fix_opening_hours(items, by_place, constraints, log)
        items = _fix_overlaps(items, log)
        if fingerprint(items) == before:
            break
    return items


def _fix_opening_hours(
    items: list[ItineraryItem],
    by_place: dict[str, PlaceCandidate],
    constraints: RetrievalConstraints | None,
    log: list[str],
) -> list[ItineraryItem]:
    used = {item.place_id for item in items}
    result: list[ItineraryItem] = []

    for item in items:
        place = by_place.get(item.place_id)
        if place is None:
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
    items: list[ItineraryItem],
    original: Itinerary,
    participant_count: int,
    stays: list[AccommodationStay] | None = None,
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

    resolved_stays = original.stays if stays is None else stays
    for index, stay in enumerate(
        sorted(resolved_stays, key=lambda s: s.check_in_date), start=1
    ):
        if not stay.stay_id:
            resolved_stays[resolved_stays.index(stay)] = stay.model_copy(
                update={"stay_id": f"stay-{index}"}
            )
    repaired = original.model_copy(update={"days": days, "stays": resolved_stays})
    repaired.recompute_costs(participant_count)
    return repaired


def _to_time(minutes: int) -> time:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return time(hour=minutes // 60, minute=minutes % 60)
