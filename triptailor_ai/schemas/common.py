"""Shared base model + primitive helpers for every TripTailor AI schema.

The main TripTailor backend speaks camelCase JSON, while Python code is
snake_case.  Every schema therefore inherits :class:`AiBaseModel`, which
accepts *both* spellings on input and emits camelCase on
``model_dump(by_alias=True)`` / ``model_dump_json()``.
"""

from __future__ import annotations

from datetime import time
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


class AiBaseModel(BaseModel):
    """Base for all AI-module schemas.

    ``extra="ignore"`` is deliberate: the backend may add fields to its own
    payloads before this module is upgraded, and an unknown field must never
    break itinerary generation.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        use_enum_values=False,
        ser_json_timedelta="float",
    )


def _dump_time(value: time) -> str:
    return value.strftime("%H:%M")


#: ``datetime.time`` that always serialises to ``"HH:MM"``.
TimeStr = Annotated[time, PlainSerializer(_dump_time, return_type=str, when_used="json-unless-none")]


class Weekday(str, Enum):
    """ISO weekday names, matching ``datetime.date.weekday()`` order."""

    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"

    @classmethod
    def from_weekday_index(cls, index: int) -> "Weekday":
        return _WEEKDAY_ORDER[index]


_WEEKDAY_ORDER: tuple[Weekday, ...] = (
    Weekday.MON,
    Weekday.TUE,
    Weekday.WED,
    Weekday.THU,
    Weekday.FRI,
    Weekday.SAT,
    Weekday.SUN,
)


class VerificationStatus(str, Enum):
    """How much we trust a piece of retrieved data.

    ``UNVERIFIED`` is the honest default whenever the retriever could not
    supply provenance -- it must never be silently upgraded to ``VERIFIED``.
    """

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    STALE = "STALE"


def minutes_between(start: time, end: time) -> int:
    """Whole minutes from ``start`` to ``end`` on the same calendar day."""

    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute
