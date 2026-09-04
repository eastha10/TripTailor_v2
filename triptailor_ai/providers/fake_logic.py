"""Deterministic heuristics behind :class:`FakeModelProvider`.

These functions stand in for LLM reasoning so that the *entire* graph --
prompt construction, structured output, validation, repair, routing -- can run
in CI with no API key and no GPU.

They are intentionally rule-based and modest.  They are **not** a fallback
planner for production: nothing here is wired into the OpenAI or Qwen paths.
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from typing import Any, Iterable

from triptailor_ai.schemas.common import Weekday
from triptailor_ai.schemas.itinerary import ItineraryDraft, ItineraryItem
from triptailor_ai.schemas.preference import (
    CommonPreference,
    Conflict,
    ConsensusAnalysis,
    ConstraintType,
    NormalizedPreference,
    NormalizedPreferenceSet,
    PreferenceCategory,
    Priority,
)

# --------------------------------------------------------------------------
# Normalizer heuristics
# --------------------------------------------------------------------------

#: Markers that make a statement a HARD constraint (explicit impossibility).
_HARD_MARKERS = (
    "알레르기",
    "알러지",
    "불가",
    "못 먹",
    "못먹",
    "안 먹",
    "먹을 수 없",
    "먹지 못",
    "섭취 불가",
    "휠체어",
    "절대",
    "무조건",
)
#: Markers of difficulty -- strong preference, but *not* a hard constraint.
_SOFT_STRONG_MARKERS = ("힘들", "부담", "선호", "꼭", "필수", "반드시", "위주")

_CATEGORY_KEYWORDS: tuple[tuple[PreferenceCategory, tuple[str, ...]], ...] = (
    (PreferenceCategory.MOBILITY, ("걷", "도보", "휠체어", "무릎", "체력", "계단", "등산")),
    (
        PreferenceCategory.DIETARY,
        ("알레르기", "알러지", "못 먹", "못먹", "안 먹", "먹을 수 없", "채식", "비건"),
    ),
    (PreferenceCategory.FOOD, ("맛집", "음식", "먹", "카페", "커피", "디저트", "식당", "회")),
    (PreferenceCategory.ACTIVITY, ("오름", "자연", "산", "바다", "해변", "액티비티", "박물관", "미술관", "체험", "관광")),
    (PreferenceCategory.ATMOSPHERE, ("조용", "분위기", "감성", "사진", "뷰", "야경", "한적")),
    (
        PreferenceCategory.PACE,
        ("여유", "빡빡", "천천", "쉬엄", "일정", "많은 곳", "열 군데", "두세 곳", "체력"),
    ),
    (PreferenceCategory.ACCOMMODATION, ("숙소", "호텔", "펜션", "게스트하우스", "리조트", "풀빌라")),
    (PreferenceCategory.BUDGET, ("예산", "저렴", "가성비", "비싸", "돈")),
    (PreferenceCategory.AVOID, ("싫", "별로", "피하", "제외")),
)

_MUST_MARKERS = ("꼭", "필수", "반드시", "무조건")
_CLAUSE_SPLIT = re.compile(r"[.\n!?·]|,\s|(?<=요)\s+(?=[가-힣])")


def _clauses(text: str) -> list[str]:
    parts = [c.strip(" \t,.") for c in _CLAUSE_SPLIT.split(text)]
    return [c for c in parts if c]


def _classify(clause: str) -> PreferenceCategory:
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in clause for keyword in keywords):
            return category
    return PreferenceCategory.OTHER


def _constraint_type(clause: str, category: PreferenceCategory) -> ConstraintType:
    """HARD only on explicit impossibility, never on mere difficulty."""

    if any(marker in clause for marker in _HARD_MARKERS):
        return ConstraintType.HARD
    if category is PreferenceCategory.AVAILABILITY:
        return ConstraintType.HARD
    return ConstraintType.SOFT


def _priority(clause: str, constraint: ConstraintType) -> Priority:
    if constraint is ConstraintType.HARD:
        return Priority.HIGH
    if any(marker in clause for marker in (*_MUST_MARKERS, *_SOFT_STRONG_MARKERS)):
        return Priority.HIGH
    return Priority.MEDIUM


def _tags(clause: str) -> list[str]:
    found: list[str] = []
    for _, keywords in _CATEGORY_KEYWORDS:
        found.extend(k for k in keywords if k in clause)
    return sorted(set(found))


def fake_normalize(participants: list[dict[str, Any]]) -> NormalizedPreferenceSet:
    """Turn raw questionnaire text into traceable normalized preferences."""

    preferences: list[NormalizedPreference] = []
    for participant in participants:
        pid = str(participant.get("participantId", "unknown"))
        counter = 0

        for field_name, raw_text in (participant.get("fields") or {}).items():
            for clause in _clauses(str(raw_text)):
                counter += 1
                category = (
                    PreferenceCategory.AVAILABILITY
                    if field_name == "availableDateText"
                    else _classify(clause)
                )
                if field_name == "mustHaves" and category in (
                    PreferenceCategory.OTHER,
                    PreferenceCategory.ACTIVITY,
                ):
                    if any(m in clause for m in _MUST_MARKERS) or field_name == "mustHaves":
                        category = PreferenceCategory.MUST_VISIT
                constraint = _constraint_type(clause, category)
                preferences.append(
                    NormalizedPreference(
                        preference_id=f"{pid}-pref-{counter}",
                        participant_id=pid,
                        source_field=field_name,
                        source_text=clause,
                        category=category,
                        value=clause[:60],
                        priority=_priority(clause, constraint),
                        constraint_type=constraint,
                        confidence=0.8 if constraint is ConstraintType.HARD else 0.6,
                        tags=_tags(clause),
                    )
                )

        if participant.get("budgetBand"):
            counter += 1
            preferences.append(
                NormalizedPreference(
                    preference_id=f"{pid}-pref-{counter}",
                    participant_id=pid,
                    source_field="budgetBand",
                    source_text=str(participant["budgetBand"]),
                    category=PreferenceCategory.BUDGET,
                    value=str(participant["budgetBand"]),
                    priority=Priority.HIGH,
                    # System-designated: the collected band is an upper bound.
                    constraint_type=ConstraintType.HARD,
                    confidence=1.0,
                )
            )
        if participant.get("accommodationType") and participant["accommodationType"] != "NO_PREFERENCE":
            counter += 1
            preferences.append(
                NormalizedPreference(
                    preference_id=f"{pid}-pref-{counter}",
                    participant_id=pid,
                    source_field="accommodationType",
                    source_text=str(participant["accommodationType"]),
                    category=PreferenceCategory.ACCOMMODATION,
                    value=str(participant["accommodationType"]),
                    priority=Priority.MEDIUM,
                    constraint_type=ConstraintType.SOFT,
                    confidence=1.0,
                )
            )
    return NormalizedPreferenceSet(preferences=preferences)


# --------------------------------------------------------------------------
# Consensus heuristics
# --------------------------------------------------------------------------

_OPPOSED_TAGS: tuple[tuple[str, str], ...] = (
    ("걷", "등산"),
    ("조용", "액티비티"),
    ("저렴", "풀빌라"),
)


def fake_consensus(
    preferences: list[NormalizedPreference], participant_ids: list[str]
) -> ConsensusAnalysis:
    total = max(len(participant_ids), 1)

    buckets: dict[tuple[str, str], list[NormalizedPreference]] = {}
    for pref in preferences:
        for tag in pref.tags or [pref.value]:
            buckets.setdefault((pref.category.value, tag), []).append(pref)

    common: list[CommonPreference] = []
    for (category, tag), group in sorted(buckets.items()):
        owners = sorted({p.participant_id for p in group})
        if len(owners) < 2:
            continue
        common.append(
            CommonPreference(
                label=tag,
                category=PreferenceCategory(category),
                participant_ids=owners,
                preference_ids=[p.preference_id for p in group],
                support_ratio=round(len(owners) / total, 3),
            )
        )

    common_ids = {pid for c in common for pid in c.preference_ids}
    hard = [p for p in preferences if p.is_hard]
    soft = [p for p in preferences if not p.is_hard]
    individual = [p for p in preferences if p.preference_id not in common_ids]

    conflicts = _detect_conflicts(preferences)
    return ConsensusAnalysis(
        common_preferences=common,
        individual_preferences=individual,
        hard_constraints=hard,
        soft_preferences=soft,
        conflicts=conflicts,
        summary=(
            f"공통 관심사 {len(common)}건, 하드 제약 {len(hard)}건, "
            f"충돌 {len(conflicts)}건을 확인했습니다."
        ),
    )


def _detect_conflicts(preferences: list[NormalizedPreference]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    counter = 0

    # 1) Budget band mismatch.
    bands = {p.participant_id: p.value for p in preferences if p.source_field == "budgetBand"}
    if len(set(bands.values())) > 1:
        counter += 1
        conflicts.append(
            Conflict(
                conflict_id=f"conflict-{counter}",
                involved_participant_ids=sorted(bands),
                related_preference_ids=[
                    p.preference_id for p in preferences if p.source_field == "budgetBand"
                ],
                reason="참여자별 예산 밴드가 서로 다릅니다. 가장 낮은 상한을 기준으로 계획됩니다.",
                possible_compromises=[
                    "가장 낮은 예산 상한에 맞춘 기본 일정 + 선택 추가 비용 항목 분리",
                    "고가 활동은 희망자만 참여하는 자유시간으로 배치",
                ],
                blocking=False,
            )
        )

    # 2) Mobility hard constraint vs. high-effort activity wishes.
    mobility_hard = [
        p
        for p in preferences
        if p.category is PreferenceCategory.MOBILITY and p.is_hard
    ]
    effort = [
        p
        for p in preferences
        if p.category in (PreferenceCategory.ACTIVITY, PreferenceCategory.MUST_VISIT)
        and any(t in p.source_text for t in ("오름", "등산", "산", "트레킹"))
    ]
    if mobility_hard and effort:
        involved = sorted({p.participant_id for p in (*mobility_hard, *effort)})
        if len(involved) > 1:
            counter += 1
            conflicts.append(
                Conflict(
                    conflict_id=f"conflict-{counter}",
                    involved_participant_ids=involved,
                    related_preference_ids=[
                        p.preference_id for p in (*mobility_hard, *effort)
                    ],
                    reason="이동/보행이 어려운 참여자가 있는데 도보 부담이 큰 장소 희망이 있습니다.",
                    possible_compromises=[
                        "정상 등반 대신 전망대/주차장 인근 조망 포인트로 대체",
                        "해당 활동은 희망자만 참여하고 나머지는 인근 카페에서 대기",
                    ],
                    blocking=True,
                )
            )

    # 3) One participant's hard dietary exclusion vs. another's food wish.
    from triptailor_ai.retrieval.service import DIETARY_TAG_HINTS

    dietary_hard = [
        p
        for p in preferences
        if p.category is PreferenceCategory.DIETARY and p.is_hard
    ]
    for restriction in dietary_hard:
        markers = [m for m in DIETARY_TAG_HINTS if m in restriction.source_text]
        clashing = [
            p
            for p in preferences
            if p.participant_id != restriction.participant_id
            and p.category in (PreferenceCategory.FOOD, PreferenceCategory.MUST_VISIT)
            and any(marker in p.source_text for marker in markers)
        ]
        if not clashing:
            continue
        counter += 1
        conflicts.append(
            Conflict(
                conflict_id=f"conflict-{counter}",
                involved_participant_ids=sorted(
                    {restriction.participant_id, *(p.participant_id for p in clashing)}
                ),
                related_preference_ids=[
                    restriction.preference_id,
                    *(p.preference_id for p in clashing),
                ],
                reason=(
                    "한 참여자의 식이 제약(하드)과 다른 참여자의 음식 선호가 충돌합니다: "
                    f"'{restriction.source_text}' vs '{clashing[0].source_text}'"
                ),
                possible_compromises=[
                    "제약이 있는 참여자도 먹을 수 있는 메뉴가 함께 있는 식당 선택",
                    "해당 음식은 자유시간에 희망자만 별도로 방문",
                ],
                blocking=True,
            )
        )

    # 4) Opposed pace: one wants a packed day, another wants to slow down.
    _DENSE = ("많은 곳", "많이", "빡빡", "열 군데", "최대한")
    _SLOW = ("천천", "쉬엄", "여유", "두세 곳", "두 곳", "체력이 약")
    dense = [
        p
        for p in preferences
        if any(m in p.source_text for m in _DENSE)
        and not any(m in p.source_text for m in _SLOW)
    ]
    slow = [p for p in preferences if any(m in p.source_text for m in _SLOW)]
    owners = {p.participant_id for p in dense} | {p.participant_id for p in slow}
    if dense and slow and len(owners) > 1:
        counter += 1
        conflicts.append(
            Conflict(
                conflict_id=f"conflict-{counter}",
                involved_participant_ids=sorted(owners),
                related_preference_ids=[p.preference_id for p in (*dense, *slow)],
                reason=(
                    "하루 일정 밀도에 대한 선호가 상충합니다: "
                    f"'{dense[0].source_text}' vs '{slow[0].source_text}'"
                ),
                possible_compromises=[
                    "핵심 일정만 함께 하고 나머지는 자유시간으로 분리",
                    "오전은 여유롭게, 오후는 밀도 높게 배치",
                ],
                blocking=False,
            )
        )

    # 5) Explicitly opposed tag pairs across participants.
    for left, right in _OPPOSED_TAGS:
        lefts = [p for p in preferences if left in p.tags]
        rights = [p for p in preferences if right in p.tags]
        owners = {p.participant_id for p in lefts} | {p.participant_id for p in rights}
        if lefts and rights and len(owners) > 1:
            counter += 1
            conflicts.append(
                Conflict(
                    conflict_id=f"conflict-{counter}",
                    involved_participant_ids=sorted(owners),
                    related_preference_ids=[p.preference_id for p in (*lefts, *rights)],
                    reason=f"'{left}' 관련 선호와 '{right}' 관련 선호가 상충합니다.",
                    possible_compromises=["일자별로 성향을 나누어 배치", "오전/오후로 분리"],
                    blocking=False,
                )
            )
    return conflicts


# --------------------------------------------------------------------------
# Planner heuristics
# --------------------------------------------------------------------------

_MEAL_CATEGORIES = {"restaurant", "food", "cafe", "맛집", "식당", "카페"}
#: Minimum gap left between two consecutive stops, in minutes.
_MIN_TRANSFER_GAP_MINUTES = 30
#: Latest minute a stop may still start.
_LATEST_START_MINUTES = 21 * 60

#: (start minutes, stay minutes, is_meal) slots for one day.
_DAY_SLOTS: tuple[tuple[int, int, bool], ...] = (
    (10 * 60, 90, False),
    (12 * 60, 60, True),
    (14 * 60, 90, False),
    (16 * 60 + 30, 90, False),
    (18 * 60 + 30, 75, True),
)


_ACCOMMODATION_MARKERS = {"accommodation", "hotel", "guesthouse", "resort",
                          "pension", "숙소", "호텔", "게스트하우스", "리조트", "펜션"}
_FESTIVAL_MARKERS = {"festival", "event", "축제", "행사"}


def _kind_of(place: dict[str, Any]) -> str:
    if place.get("kind"):
        return str(place["kind"])
    haystack = {c.lower() for c in place.get("categories") or []}
    haystack |= {t.lower() for t in place.get("tags") or []}
    if haystack & _ACCOMMODATION_MARKERS:
        return "ACCOMMODATION"
    if haystack & _FESTIVAL_MARKERS:
        return "FESTIVAL"
    if haystack & _MEAL_CATEGORIES:
        return "RESTAURANT"
    return "ATTRACTION"


def _is_accommodation(place: dict[str, Any]) -> bool:
    return _kind_of(place) == "ACCOMMODATION"


def _runs_on(place: dict[str, Any], day: date) -> bool:
    """Festivals may only be placed on a date they actually run."""

    if _kind_of(place) != "FESTIVAL":
        return True
    period = place.get("eventPeriod")
    if not period:
        return True  # unknown; the validator reports it as unverified
    start = date.fromisoformat(str(period["startDate"]))
    end = date.fromisoformat(str(period["endDate"]))
    return start <= day <= end


def _is_meal(place: dict[str, Any]) -> bool:
    haystack = {c.lower() for c in place.get("categories") or []}
    haystack |= {t.lower() for t in place.get("tags") or []}
    return bool(haystack & _MEAL_CATEGORIES)


def _minutes_to_time(minutes: int) -> time:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return time(hour=minutes // 60, minute=minutes % 60)


def _opening_window(place: dict[str, Any], weekday: str) -> tuple[int, int] | None:
    hours = place.get("openingHours")
    if not hours:
        return None
    intervals = (hours.get("weekly") or {}).get(weekday)
    if not intervals:
        return None
    first = intervals[0]
    return _parse_hhmm(first["open"]), _parse_hhmm(first["close"])


def _parse_hhmm(value: str) -> int:
    hour, minute = str(value).split(":")[:2]
    return int(hour) * 60 + int(minute)


def _score(place: dict[str, Any], preference_terms: list[str]) -> float:
    text = " ".join(
        [
            place.get("name", ""),
            place.get("description") or "",
            *(place.get("categories") or []),
            *(place.get("tags") or []),
        ]
    ).lower()
    hits = sum(1 for term in preference_terms if term and term.lower() in text)
    return hits + float(place.get("confidence") or 0.0)


#: Instruction words the offline planner understands. A real model reads the
#: sentence; this fake only recognises "make it lighter".
_LIGHTEN_MARKERS = ("줄여", "줄이", "적게", "덜 ", "빼", "제거", "여유", "쉬엄")


def fake_plan(
    *,
    trip: dict[str, Any],
    candidates: list[dict[str, Any]],
    constraints: dict[str, Any],
    preferences: list[dict[str, Any]],
    exclude_place_ids: Iterable[str] = (),
    instruction: dict[str, Any] | None = None,
) -> ItineraryDraft:
    """Greedy, constraint-aware scheduler used as the offline planner.

    ``instruction`` carries a revision request. The offline interpretation is
    intentionally shallow -- it recognises "lighten this day" and nothing
    else. Real instruction understanding is the LLM's job.
    """

    lighten_days = _lighten_days(instruction, trip)

    terms: list[str] = []
    for pref in preferences:
        terms.extend(pref.get("tags") or [])
        if pref.get("value"):
            terms.append(str(pref["value"]))

    banned_dietary = {t.lower() for t in constraints.get("excludedDietaryTags") or []}
    banned_access = {t.lower() for t in constraints.get("excludedAccessibilityTags") or []}
    budget_cap = constraints.get("budgetCapPerPerson")

    lodging = [p for p in candidates if _is_accommodation(p)]
    usable = [
        place
        for place in candidates
        if place.get("placeId") not in set(exclude_place_ids)
        and not _is_accommodation(place)
        and not ({t.lower() for t in place.get("dietaryTags") or []} & banned_dietary)
        and not ({t.lower() for t in place.get("accessibility") or []} & banned_access)
    ]
    usable.sort(key=lambda p: (-_score(p, terms), p.get("placeId", "")))

    items: list[ItineraryItem] = []
    day_titles: dict[int, str] = {}
    used: set[str] = set()
    running_cost = 0
    sequence = 0

    for day_info in trip.get("days") or []:
        day_number = int(day_info["day"])
        day_date = date.fromisoformat(str(day_info["date"]))
        weekday = day_info.get("weekday") or Weekday.from_weekday_index(day_date.weekday()).value
        # Earliest minute the next stop may start, so slots never overlap.
        earliest = 0

        slots = _DAY_SLOTS
        if day_number in lighten_days:
            # Keep the meals, drop the optional stops.
            slots = tuple(s for s in _DAY_SLOTS if s[2]) + (_DAY_SLOTS[0],)
            slots = tuple(sorted(slots, key=lambda s: s[0]))

        for slot_start, slot_stay, meal_slot in slots:
            pick = _pick_place(
                usable,
                used=used,
                weekday=weekday,
                day_date=day_date,
                slot_start=max(slot_start, earliest),
                slot_stay=slot_stay,
                meal_slot=meal_slot,
                budget_cap=budget_cap,
                running_cost=running_cost,
            )
            if pick is None:
                continue
            place, start_minutes, stay = pick
            earliest = start_minutes + stay + _MIN_TRANSFER_GAP_MINUTES
            used.add(place["placeId"])
            running_cost += int(place.get("estimatedCostPerPerson") or 0)
            sequence += 1
            items.append(
                ItineraryItem(
                    item_id=f"item-{day_number}-{sequence}",
                    sequence=sequence,
                    day=day_number,
                    date=day_date,
                    start_time=_minutes_to_time(start_minutes),
                    end_time=_minutes_to_time(start_minutes + stay),
                    place_id=place["placeId"],
                    place_name=place.get("name", place["placeId"]),
                    image_url=place.get("imageUrl"),
                    description=place.get("description"),
                    reason=_reason_for(place, terms),
                    matched_preference_ids=_matched_preference_ids(place, preferences),
                    estimated_cost_per_person=place.get("estimatedCostPerPerson"),
                    source_ids=place.get("sourceIds") or [],
                )
            )
        if any(i.day == day_number for i in items):
            day_titles[day_number] = f"Day {day_number} 일정"

    stays = _plan_stays(trip, lodging, budget_cap, running_cost)
    covered = {pid for item in items for pid in item.matched_preference_ids}
    unmet = [
        str(p.get("preferenceId"))
        for p in preferences
        if p.get("preferenceId") and p["preferenceId"] not in covered
    ]
    return ItineraryDraft(
        items=items,
        stays=stays,
        day_titles=day_titles,
        unmet_preferences=unmet[:20],
        notes=["offline fake planner: greedy slot filling"],
    )


def _lighten_days(
    instruction: dict[str, Any] | None, trip: dict[str, Any]
) -> set[int]:
    """Days the user asked to make lighter; empty when no such request."""

    if not instruction:
        return set()
    text = str(instruction.get("text") or "")
    if not any(marker in text for marker in _LIGHTEN_MARKERS):
        return set()

    targets = {int(d) for d in instruction.get("targetDays") or []}
    if targets:
        return targets

    ordinals = {"첫": 1, "1일": 1, "둘": 2, "2일": 2, "셋": 3, "3일": 3, "넷": 4, "4일": 4}
    mentioned = {value for marker, value in ordinals.items() if marker in text}
    if mentioned:
        return mentioned
    return {int(d["day"]) for d in trip.get("days") or []}


def _plan_stays(
    trip: dict[str, Any],
    lodging: list[dict[str, Any]],
    budget_cap: int | None = None,
    spent: int = 0,
) -> list[Any]:
    """One stay per night, consecutive nights at the same place merged.

    Accommodation is normally the largest cost in a trip, so the choice is made
    against what is left of the budget rather than by taking the first option.
    """

    from triptailor_ai.schemas.itinerary import AccommodationStay

    days = trip.get("days") or []
    if len(days) < 2 or not lodging:
        return []

    nights = [date.fromisoformat(str(d["date"])) for d in days][:-1]
    ranked = sorted(lodging, key=lambda p: p.get("pricePerNightPerPerson") or 0)

    place = ranked[0]
    if budget_cap is not None:
        remaining = budget_cap - spent
        affordable = [
            p
            for p in ranked
            if (p.get("pricePerNightPerPerson") or 0) * len(nights) <= remaining
        ]
        # Best that fits; if nothing fits, the cheapest, and the validator
        # reports the overrun rather than this quietly hiding it.
        place = affordable[-1] if affordable else ranked[0]
    return [
        AccommodationStay(
            place_id=place["placeId"],
            place_name=place.get("name", place["placeId"]),
            check_in_date=nights[0],
            check_out_date=nights[-1] + timedelta(days=1),
            price_per_night_per_person=place.get("pricePerNightPerPerson"),
            reason="숙소 선호를 반영해 전 일정 동일 숙소로 배치했습니다.",
        )
    ]


def _pick_place(
    usable: list[dict[str, Any]],
    *,
    used: set[str],
    weekday: str,
    day_date: date,
    slot_start: int,
    slot_stay: int,
    meal_slot: bool,
    budget_cap: int | None,
    running_cost: int,
) -> tuple[dict[str, Any], int, int] | None:
    """Return ``(place, start_minutes, stay_minutes)`` for one slot, if any fits."""

    for place in usable:
        place_id = place.get("placeId")
        if not place_id or place_id in used:
            continue
        if _is_meal(place) is not meal_slot:
            continue
        if weekday in (place.get("closedDays") or []):
            continue
        if not _runs_on(place, day_date):
            continue
        if day_date.isoformat() in [str(d) for d in place.get("closedDates") or []]:
            continue

        cost = int(place.get("estimatedCostPerPerson") or 0)
        if budget_cap is not None and running_cost + cost > budget_cap:
            continue

        stay = min(int(place.get("estimatedStayMinutes") or slot_stay), slot_stay)
        start = slot_start

        window = _opening_window(place, weekday)
        if window is not None:
            opens, closes = window
            start = max(start, opens)
            if start >= closes:
                continue
            if start + stay > closes:
                # Try trimming the stay, otherwise this place cannot fit here.
                if closes - start < 30:
                    continue
                stay = closes - start
        if start > _LATEST_START_MINUTES:
            continue
        return place, start, stay
    return None


def _reason_for(place: dict[str, Any], terms: list[str]) -> str:
    text = " ".join([*(place.get("tags") or []), *(place.get("categories") or [])])
    matched = [t for t in dict.fromkeys(terms) if t and t in text][:2]
    if matched:
        return f"'{', '.join(matched)}' 선호와 맞는 후보라 배치했습니다."
    return "일정 흐름과 이동 동선을 고려해 배치했습니다."


def _matched_preference_ids(
    place: dict[str, Any], preferences: list[dict[str, Any]]
) -> list[str]:
    text = " ".join(
        [
            place.get("name", ""),
            place.get("description") or "",
            *(place.get("categories") or []),
            *(place.get("tags") or []),
        ]
    )
    matched: list[str] = []
    for pref in preferences:
        tags = [t for t in (pref.get("tags") or []) if t]
        if any(tag in text for tag in tags):
            matched.append(str(pref.get("preferenceId")))
    return matched[:5]


# --------------------------------------------------------------------------
# Repair heuristics
# --------------------------------------------------------------------------

def fake_repair(
    *,
    trip: dict[str, Any],
    itinerary_items: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    constraints: dict[str, Any],
    stays: list[dict[str, Any]] | None = None,
) -> ItineraryDraft:
    """Targeted repair: fix only the items the validator complained about."""

    by_id = {item["itemId"]: dict(item) for item in itinerary_items}
    by_place = {c["placeId"]: c for c in candidates}
    drop: set[str] = set()

    for issue in issues:
        code = issue.get("code")
        targets = issue.get("itemIds") or []
        for item_id in targets:
            item = by_id.get(item_id)
            if item is None:
                continue

            if code in ("PLACE_NOT_GROUNDED", "OUTSIDE_TRAVEL_PERIOD", "DAY_DATE_MISMATCH"):
                drop.add(item_id)
            elif code == "PLACE_CLOSED":
                replacement = _find_replacement(item, by_place, by_id, trip, constraints)
                if replacement is None:
                    drop.add(item_id)
                else:
                    item["placeId"] = replacement["placeId"]
                    item["placeName"] = replacement.get("name", replacement["placeId"])
                    item["estimatedCostPerPerson"] = replacement.get("estimatedCostPerPerson")
                    item["reason"] = "휴무일 충돌로 동일 성격의 다른 장소로 교체했습니다."
            elif code == "OUTSIDE_OPENING_HOURS":
                if not _shift_into_opening_hours(item, by_place):
                    drop.add(item_id)
            elif code == "INVALID_TIME_RANGE":
                start = _parse_hhmm(item["startTime"])
                item["endTime"] = _minutes_to_time(start + 60).strftime("%H:%M")
            elif code in ("SCHEDULE_OVERLAP", "INSUFFICIENT_TRAVEL_TIME"):
                shortfall = int(issue.get("evidence", {}).get("shortfallMinutes") or 30)
                # Only the later of the two items moves; moving both would
                # just recreate the clash further down the day.
                if item_id != targets[-1]:
                    continue
                if not _shift_later(item, minutes=shortfall, by_place=by_place):
                    drop.add(item_id)
            elif code == "BUDGET_EXCEEDED":
                drop.add(_most_expensive(targets, by_id))
            elif code == "MOBILITY_CONSTRAINT_VIOLATION":
                replacement = _find_replacement(item, by_place, by_id, trip, constraints)
                if replacement is None:
                    drop.add(item_id)
                else:
                    item["placeId"] = replacement["placeId"]
                    item["placeName"] = replacement.get("name", replacement["placeId"])
                    item["reason"] = "보행 부담이 적은 장소로 교체했습니다."
            elif code == "DIETARY_CONSTRAINT_VIOLATION":
                drop.add(item_id)

        if code == "BUDGET_EXCEEDED" and not targets:
            drop.add(_most_expensive(list(by_id), by_id))

    kept = [item for item_id, item in by_id.items() if item_id not in drop and item_id]
    kept.sort(key=lambda i: (i["day"], i["startTime"]))
    for index, item in enumerate(kept, start=1):
        item["sequence"] = index

    from triptailor_ai.schemas.itinerary import AccommodationStay

    return ItineraryDraft(
        items=[ItineraryItem.model_validate(item) for item in kept],
        # Repair returns the whole plan, accommodation included.
        stays=[AccommodationStay.model_validate(s) for s in (stays or [])],
        notes=[f"offline fake repair applied to {len(issues)} issue(s)"],
    )


def _most_expensive(item_ids: list[str], by_id: dict[str, dict[str, Any]]) -> str:
    known = [i for i in item_ids if i in by_id]
    if not known:
        return ""
    return max(known, key=lambda i: by_id[i].get("estimatedCostPerPerson") or 0)


def _shift_later(
    item: dict[str, Any], *, minutes: int, by_place: dict[str, dict[str, Any]]
) -> bool:
    """Push an item later. Returns ``False`` when it no longer fits the day."""

    duration = max(_parse_hhmm(item["endTime"]) - _parse_hhmm(item["startTime"]), 30)
    start = _parse_hhmm(item["startTime"]) + max(minutes, 15)

    place = by_place.get(item["placeId"])
    if place is not None:
        day_date = date.fromisoformat(str(item["date"]))
        window = _opening_window(place, Weekday.from_weekday_index(day_date.weekday()).value)
        if window is not None:
            opens, closes = window
            start = max(start, opens)
            if start + duration > closes:
                duration = closes - start
            if duration < 30:
                return False
    if start + duration > _LATEST_START_MINUTES + 120:
        return False

    item["startTime"] = _minutes_to_time(start).strftime("%H:%M")
    item["endTime"] = _minutes_to_time(start + duration).strftime("%H:%M")
    return True


def _shift_into_opening_hours(
    item: dict[str, Any], by_place: dict[str, dict[str, Any]]
) -> bool:
    place = by_place.get(item["placeId"])
    if place is None:
        return False
    day_date = date.fromisoformat(str(item["date"]))
    weekday = Weekday.from_weekday_index(day_date.weekday()).value
    window = _opening_window(place, weekday)
    if window is None:
        return False
    opens, closes = window
    duration = _parse_hhmm(item["endTime"]) - _parse_hhmm(item["startTime"])
    duration = max(min(duration, closes - opens), 30)
    if closes - opens < duration:
        return False
    item["startTime"] = _minutes_to_time(opens).strftime("%H:%M")
    item["endTime"] = _minutes_to_time(opens + duration).strftime("%H:%M")
    return True


def _find_replacement(
    item: dict[str, Any],
    by_place: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    trip: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any] | None:
    """Pick an unused candidate that is open on the item's date."""

    original = by_place.get(item["placeId"], {})
    wanted_meal = _is_meal(original)
    used = {i["placeId"] for i in by_id.values()}
    day_date = date.fromisoformat(str(item["date"]))
    weekday = Weekday.from_weekday_index(day_date.weekday()).value
    banned_access = {t.lower() for t in constraints.get("excludedAccessibilityTags") or []}
    banned_dietary = {t.lower() for t in constraints.get("excludedDietaryTags") or []}

    for place in by_place.values():
        if place["placeId"] in used:
            continue
        if _is_meal(place) is not wanted_meal:
            continue
        if weekday in (place.get("closedDays") or []):
            continue
        if not _runs_on(place, day_date):
            continue
        if {t.lower() for t in place.get("accessibility") or []} & banned_access:
            continue
        if {t.lower() for t in place.get("dietaryTags") or []} & banned_dietary:
            continue
        window = _opening_window(place, weekday)
        if window is not None:
            start = _parse_hhmm(item["startTime"])
            if not window[0] <= start < window[1]:
                continue
        return place
    return None


def next_day(value: date) -> date:
    return value + timedelta(days=1)
