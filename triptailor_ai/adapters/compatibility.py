"""Mapping between the AI itinerary and the existing TripTailor v1 shape.

The legacy ``ItineraryItem`` has five fields.  The AI item has fourteen.  The
projection below is therefore **lossy**, and the loss is enumerated in
:data:`DROPPED_FIELDS` so nobody discovers it in production.
"""

from __future__ import annotations

from typing import Any

from triptailor_ai.schemas.itinerary import Itinerary, ItineraryItem, LegacyItineraryItem

#: Extended fields that do not survive ``to_legacy_items``.
DROPPED_FIELDS: tuple[str, ...] = (
    "day",
    "date",
    "startTime",
    "endTime",
    "placeId",
    "reason",
    "matchedPreferenceIds",
    "estimatedCostPerPerson",
    "sourceIds",
)


def to_legacy_item(item: ItineraryItem) -> LegacyItineraryItem:
    """Project one extended item onto the legacy shape.

    ``placeId`` is dropped, so the result is no longer grounded: a legacy item
    cannot be re-validated.  Store the extended item too if you need that.
    """

    return LegacyItineraryItem(
        item_id=item.item_id,
        sequence=item.sequence,
        place_name=item.place_name,
        image_url=item.image_url,
        description=item.description or item.reason,
    )


def to_legacy_items(itinerary: Itinerary) -> list[LegacyItineraryItem]:
    """Flatten a multi-day itinerary into the legacy single-list shape.

    Day boundaries are lost; ``sequence`` is renumbered across the whole trip
    so the ordering still reads correctly in the existing UI.
    """

    items = sorted(itinerary.all_items(), key=lambda i: (i.day, i.start_time, i.sequence))
    return [
        to_legacy_item(item).model_copy(update={"sequence": index})
        for index, item in enumerate(items, start=1)
    ]


def to_legacy_payload(itinerary: Itinerary) -> dict[str, Any]:
    """``POST /trips/{tripId}/itinerary/items``-shaped body."""

    return {
        "items": [
            item.model_dump(by_alias=True, mode="json") for item in to_legacy_items(itinerary)
        ]
    }


def describe_loss() -> dict[str, Any]:
    """Machine-readable description of what the legacy projection discards."""

    return {
        "droppedFields": list(DROPPED_FIELDS),
        "note": (
            "Legacy items are not grounded (no placeId) and carry no schedule. "
            "Persist the extended itinerary alongside them if you need "
            "re-validation, revision or cost roll-ups."
        ),
    }
