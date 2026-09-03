"""Itinerary schemas, including the legacy-compatible item shape."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from triptailor_ai.schemas.common import AiBaseModel, TimeStr, minutes_between


class ItineraryItem(AiBaseModel):
    """One scheduled stop.

    ``place_id`` is ground truth and must exist in the retrieved candidate
    set; ``place_name`` is a denormalised convenience field for the UI.

    ``item_id`` and ``sequence`` default rather than being required, because
    :func:`~triptailor_ai.nodes.common.build_itinerary` assigns both regardless
    of what the model returned. Demanding them anyway made a 7B model fill two
    extra fields per stop, twelve stops over, for nothing -- and a real Qwen
    run failed schema validation three times on exactly this shape.
    """

    #: Assigned by ``build_itinerary`` when the model leaves it blank.
    item_id: str = ""
    #: Recomputed by ``build_itinerary`` from the day/time ordering.
    sequence: int = 0
    day: int
    date: date
    start_time: TimeStr
    end_time: TimeStr
    place_id: str
    place_name: str
    image_url: str | None = None
    description: str | None = None
    #: Why this place was chosen, in the group's own terms.
    reason: str | None = None
    matched_preference_ids: list[str] = Field(default_factory=list)
    estimated_cost_per_person: int | None = None
    source_ids: list[str] = Field(default_factory=list)

    @property
    def duration_minutes(self) -> int:
        return minutes_between(self.start_time, self.end_time)


class TravelSegment(AiBaseModel):
    """A notable transfer between two consecutive items."""

    from_item_id: str
    to_item_id: str
    from_place_id: str
    to_place_id: str
    estimated_minutes: int | None = None
    mode: str | None = None
    #: Gap the schedule actually leaves for this transfer.
    available_minutes: int | None = None


class ItineraryDay(AiBaseModel):
    day: int
    date: date
    items: list[ItineraryItem] = Field(default_factory=list)
    #: One-line theme, e.g. "동쪽 오름과 바다".
    title: str | None = None

    @model_validator(mode="after")
    def _sort_items(self) -> "ItineraryDay":
        self.items.sort(key=lambda i: (i.start_time, i.sequence))
        return self

    @property
    def estimated_cost_per_person(self) -> int:
        return sum(i.estimated_cost_per_person or 0 for i in self.items)


class Itinerary(AiBaseModel):
    """The full plan draft."""

    days: list[ItineraryDay] = Field(default_factory=list)
    total_estimated_cost: int | None = None
    estimated_cost_per_person: int | None = None
    major_travel_segments: list[TravelSegment] = Field(default_factory=list)
    #: Preference ids the plan could not satisfy.
    unmet_preferences: list[str] = Field(default_factory=list)
    #: Human-readable open questions the reviewer must settle.
    unresolved_issues: list[str] = Field(default_factory=list)
    #: Narrative produced by the explanation node.
    summary: str | None = None

    def all_items(self) -> list[ItineraryItem]:
        return [item for day in self.days for item in day.items]

    def item_by_id(self, item_id: str) -> ItineraryItem | None:
        return next((i for i in self.all_items() if i.item_id == item_id), None)

    def recompute_costs(self, participant_count: int) -> "Itinerary":
        """Recompute cost roll-ups from the items. Never trust LLM arithmetic."""

        per_person = sum(i.estimated_cost_per_person or 0 for i in self.all_items())
        self.estimated_cost_per_person = per_person
        self.total_estimated_cost = per_person * max(participant_count, 1)
        return self


class ItineraryDraft(AiBaseModel):
    """Structured-output envelope for the planner/repair nodes.

    Kept flat (a plain item list) because LLMs produce flat lists far more
    reliably than nested day objects; :func:`build_itinerary` groups them.
    """

    items: list[ItineraryItem] = Field(default_factory=list)
    day_titles: dict[int, str] = Field(default_factory=dict)
    unmet_preferences: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class LegacyItineraryItem(AiBaseModel):
    """The existing TripTailor v1 itinerary item shape.

    Extended AI fields (day/date/times/placeId/reason/cost/...) are lost in
    this projection -- see ``docs/AI_API_SPEC.md``.
    """

    item_id: str
    sequence: int
    place_name: str
    image_url: str | None = None
    description: str | None = None
