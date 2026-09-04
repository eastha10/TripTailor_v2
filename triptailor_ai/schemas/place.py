"""Place candidate schema -- the *only* source of truth for what may appear
in an itinerary.

The planner LLM can only reference ``placeId`` values that a
:class:`~triptailor_ai.retrieval.base.PlaceRetriever` actually returned.
Missing data is represented as ``None`` and surfaced as UNVERIFIED; it is
never filled in by the model.
"""

from __future__ import annotations

from datetime import date, datetime

from enum import Enum

from pydantic import Field, model_validator

from triptailor_ai.schemas.common import AiBaseModel, TimeStr, VerificationStatus, Weekday


class PlaceKind(str, Enum):
    """What a place *is*, which decides how it may be scheduled.

    Scheduling semantics differ per kind, and treating everything as a generic
    stop produces nonsense: a festival placed outside its run, or three hotels
    on the same afternoon.

    * ``ATTRACTION`` / ``RESTAURANT`` / ``CAFE`` -- a stop with a start and end
      time on one day.
    * ``FESTIVAL`` -- a stop, but only on a date inside :attr:`event_period`.
    * ``ACCOMMODATION`` -- **not a stop at all.** It is a night, modelled as
      :class:`~triptailor_ai.schemas.itinerary.AccommodationStay`.
    """

    ATTRACTION = "ATTRACTION"
    RESTAURANT = "RESTAURANT"
    CAFE = "CAFE"
    FESTIVAL = "FESTIVAL"
    ACCOMMODATION = "ACCOMMODATION"


#: Category/tag markers used to infer a kind when the retriever omits one.
_KIND_MARKERS: tuple[tuple[PlaceKind, frozenset[str]], ...] = (
    (
        PlaceKind.ACCOMMODATION,
        frozenset({"accommodation", "hotel", "hostel", "guesthouse", "resort",
                   "pension", "숙소", "호텔", "게스트하우스", "리조트", "펜션", "민박"}),
    ),
    (
        PlaceKind.FESTIVAL,
        frozenset({"festival", "event", "축제", "행사", "페스티벌"}),
    ),
    (
        PlaceKind.CAFE,
        frozenset({"cafe", "카페", "디저트"}),
    ),
    (
        PlaceKind.RESTAURANT,
        frozenset({"restaurant", "food", "맛집", "식당", "시장"}),
    ),
)


class EventPeriod(AiBaseModel):
    """The dates a festival or seasonal event actually runs."""

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check_order(self) -> "EventPeriod":
        if self.end_date < self.start_date:
            raise ValueError("eventPeriod.endDate must not be before startDate")
        return self

    def contains(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date

    def overlaps(self, start: date, end: date) -> bool:
        """Whether the event runs at any point between ``start`` and ``end``."""

        return self.start_date <= end and start <= self.end_date


#: Category/tag values that mark a place as somewhere you can eat.
MEAL_MARKERS: frozenset[str] = frozenset(
    {"restaurant", "food", "cafe", "맛집", "식당", "카페", "시장"}
)


class OpeningInterval(AiBaseModel):
    open: TimeStr
    close: TimeStr


class OpeningHours(AiBaseModel):
    """Weekly opening hours.

    A weekday absent from ``weekly`` means *unknown*, not *closed*.  Explicit
    closure belongs in :attr:`PlaceCandidate.closed_days`.
    """

    weekly: dict[Weekday, list[OpeningInterval]] = Field(default_factory=dict)

    def intervals_for(self, weekday: Weekday) -> list[OpeningInterval] | None:
        return self.weekly.get(weekday)


class PlaceCandidate(AiBaseModel):
    """A real, retrieved place.  ``place_id`` is the ground truth identifier."""

    place_id: str
    name: str
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    #: What the place is. Left unset, it is inferred from categories/tags so
    #: that a retriever written before this field existed keeps working.
    kind: PlaceKind | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    image_url: str | None = None

    #: When a festival or seasonal event runs. Required for ``FESTIVAL`` to be
    #: schedulable -- without it the date check cannot run and the place is
    #: reported as unverified rather than quietly placed anywhere.
    event_period: EventPeriod | None = None
    #: Nightly price for ``ACCOMMODATION``; ``estimated_cost_per_person`` is
    #: per visit and does not describe a stay.
    price_per_night_per_person: int | None = None

    opening_hours: OpeningHours | None = None
    closed_days: list[Weekday] = Field(default_factory=list)
    closed_dates: list[date] = Field(default_factory=list)

    estimated_stay_minutes: int | None = None
    estimated_cost_per_person: int | None = None

    #: Free vocabulary, e.g. ``"wheelchair_accessible"``, ``"steep_trail"``.
    accessibility: list[str] = Field(default_factory=list)
    #: e.g. ``"raw_fish"``, ``"contains_peanut"``, ``"vegetarian_option"``.
    dietary_tags: list[str] = Field(default_factory=list)

    source_ids: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    #: Retriever-reported match score, 0.0 - 1.0. Not a data-quality signal.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def effective_kind(self) -> PlaceKind:
        """Declared kind, or one inferred from categories and tags."""

        if self.kind is not None:
            return self.kind
        haystack = {v.lower() for v in (*self.categories, *self.tags)}
        for kind, markers in _KIND_MARKERS:
            if haystack & markers:
                return kind
        return PlaceKind.ATTRACTION

    @property
    def is_meal_place(self) -> bool:
        """Whether this is somewhere the group can eat.

        Used by meal-coverage validation and by repair when swapping a stop
        for one of the same kind.
        """

        return self.effective_kind in (PlaceKind.RESTAURANT, PlaceKind.CAFE)

    @property
    def is_accommodation(self) -> bool:
        return self.effective_kind is PlaceKind.ACCOMMODATION

    @property
    def is_festival(self) -> bool:
        return self.effective_kind is PlaceKind.FESTIVAL

    def runs_on(self, day: date) -> bool | None:
        """Whether a festival runs on ``day``; ``None`` when unknown.

        ``None`` is not ``False``: a festival with no declared period is
        unverified, and the validator says so rather than rejecting it.
        """

        if not self.is_festival:
            return True
        if self.event_period is None:
            return None
        return self.event_period.contains(day)

    def opening_window_on(self, day: date) -> tuple[int, int] | None:
        """``(open, close)`` in minutes for ``day``, or ``None`` if unknown."""

        if self.opening_hours is None:
            return None
        intervals = self.opening_hours.intervals_for(
            Weekday.from_weekday_index(day.weekday())
        )
        if not intervals:
            return None
        first = intervals[0]
        return (
            first.open.hour * 60 + first.open.minute,
            first.close.hour * 60 + first.close.minute,
        )

    def is_closed_on(self, day: date) -> bool:
        if day in self.closed_dates:
            return True
        return Weekday.from_weekday_index(day.weekday()) in self.closed_days


class TravelTimeEstimate(AiBaseModel):
    """Estimated travel time between two places.

    ``minutes is None`` means *we do not know*, which the validator reports as
    ``TRAVEL_TIME_UNVERIFIED`` rather than passing silently.
    """

    from_place_id: str
    to_place_id: str
    minutes: int | None = None
    mode: str | None = None
    distance_km: float | None = None
    source: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
