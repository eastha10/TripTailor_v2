"""Input contract: what the main TripTailor backend hands to the AI module.

The AI module never touches a database.  The backend reads ``Trip`` and
``ParticipantPreference`` rows and assembles a :class:`TripPlanningRequest`.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

from pydantic import Field, field_validator, model_validator

from triptailor_ai.schemas.common import AiBaseModel


class BudgetBand(str, Enum):
    """Budget bands exactly as collected by the existing TripTailor form."""

    UP_TO_200000_KRW = "UP_TO_200000_KRW"
    FROM_200000_TO_400000_KRW = "FROM_200000_TO_400000_KRW"
    FROM_400000_TO_600000_KRW = "FROM_400000_TO_600000_KRW"

    @property
    def lower_bound_krw(self) -> int:
        return _BUDGET_BOUNDS[self][0]

    @property
    def upper_bound_krw(self) -> int:
        """Per-person upper bound for the *whole trip*, in KRW."""

        return _BUDGET_BOUNDS[self][1]


_BUDGET_BOUNDS: dict[BudgetBand, tuple[int, int]] = {
    BudgetBand.UP_TO_200000_KRW: (0, 200_000),
    BudgetBand.FROM_200000_TO_400000_KRW: (200_000, 400_000),
    BudgetBand.FROM_400000_TO_600000_KRW: (400_000, 600_000),
}


class AccommodationType(str, Enum):
    HOTEL = "HOTEL"
    RESORT_OR_POOL_VILLA = "RESORT_OR_POOL_VILLA"
    EMOTIONAL_STAY_OR_PENSION = "EMOTIONAL_STAY_OR_PENSION"
    GUESTHOUSE = "GUESTHOUSE"
    NO_PREFERENCE = "NO_PREFERENCE"


class TripStatus(str, Enum):
    """Status of the *Trip aggregate*, owned by the main backend.

    Deliberately distinct from
    :class:`~triptailor_ai.schemas.generation.GenerationStatus`.
    """

    COLLECTING_RESPONSES = "COLLECTING_RESPONSES"
    PLANNING = "PLANNING"
    READY = "READY"


class Region(AiBaseModel):
    region_id: str
    name: str


class TravelPeriod(AiBaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check_order(self) -> "TravelPeriod":
        if self.end_date < self.start_date:
            raise ValueError("travelPeriod.endDate must not be before startDate")
        return self

    @property
    def day_count(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def dates(self) -> list[date]:
        return [self.start_date + timedelta(days=i) for i in range(self.day_count)]

    def contains(self, value: date) -> bool:
        return self.start_date <= value <= self.end_date


class ParticipantInput(AiBaseModel):
    """One companion's raw questionnaire answer.

    Every free-text field stays raw here; interpretation happens in the
    normalizer node so that each derived preference keeps a pointer back to
    the exact source text.
    """

    participant_id: str
    display_name: str | None = None
    available_date_text: str | None = None
    budget_band: BudgetBand | None = None
    accommodation_type: AccommodationType | None = None
    must_haves: str | None = None
    additional_notes: str | None = None

    def source_fields(self) -> dict[str, str]:
        """Free-text fields the normalizer is allowed to read, non-empty only."""

        candidates = {
            "availableDateText": self.available_date_text,
            "mustHaves": self.must_haves,
            "additionalNotes": self.additional_notes,
        }
        return {k: v.strip() for k, v in candidates.items() if v and v.strip()}


class TripPlanningRequest(AiBaseModel):
    """The single entry-point payload for itinerary generation."""

    trip_id: str
    region: Region
    travel_period: TravelPeriod
    participant_limit: int | None = None
    participants: list[ParticipantInput] = Field(min_length=1)
    #: Optional free-form hint from the trip owner (not a participant answer).
    owner_note: str | None = None

    @field_validator("participants")
    @classmethod
    def _unique_participant_ids(
        cls, value: list[ParticipantInput]
    ) -> list[ParticipantInput]:
        seen: set[str] = set()
        for participant in value:
            if participant.participant_id in seen:
                raise ValueError(f"duplicate participantId: {participant.participant_id}")
            seen.add(participant.participant_id)
        return value

    @model_validator(mode="after")
    def _check_limit(self) -> "TripPlanningRequest":
        if self.participant_limit is not None and len(self.participants) > self.participant_limit:
            raise ValueError(
                f"participants ({len(self.participants)}) exceeds participantLimit "
                f"({self.participant_limit})"
            )
        return self
