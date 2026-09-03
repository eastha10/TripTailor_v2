"""Place candidate schema -- the *only* source of truth for what may appear
in an itinerary.

The planner LLM can only reference ``placeId`` values that a
:class:`~triptailor_ai.retrieval.base.PlaceRetriever` actually returned.
Missing data is represented as ``None`` and surfaced as UNVERIFIED; it is
never filled in by the model.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from triptailor_ai.schemas.common import AiBaseModel, TimeStr, VerificationStatus, Weekday


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
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    image_url: str | None = None

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
    def is_meal_place(self) -> bool:
        """Whether this is somewhere the group can eat.

        Used by meal-coverage validation and by repair when swapping a stop
        for one of the same kind.
        """

        haystack = {v.lower() for v in (*self.categories, *self.tags)}
        return bool(haystack & MEAL_MARKERS)

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
