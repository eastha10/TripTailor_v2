"""Travel-time providers.

The default is :class:`NullTravelTimeProvider`, which honestly reports "we do
not know".  That is a deliberate product decision: a fabricated travel time
would make the validator's ``INSUFFICIENT_TRAVEL_TIME`` check *look* like it
passed while proving nothing.
"""

from __future__ import annotations

import math

from triptailor_ai.schemas.common import VerificationStatus
from triptailor_ai.schemas.place import PlaceCandidate, TravelTimeEstimate


class NullTravelTimeProvider:
    """Reports every pair as unknown.  The safe production default."""

    async def estimate(
        self, pairs: list[tuple[str, str]], places: dict[str, PlaceCandidate]
    ) -> list[TravelTimeEstimate]:
        return [
            TravelTimeEstimate(
                from_place_id=origin,
                to_place_id=destination,
                minutes=None,
                verification_status=VerificationStatus.UNVERIFIED,
            )
            for origin, destination in pairs
        ]


class StaticTravelTimeProvider:
    """Looks travel times up in a caller-supplied matrix.

    Anything missing from the matrix stays unknown.  Used with fixtures and by
    a backend that already has a cached distance table.
    """

    def __init__(
        self,
        matrix: dict[tuple[str, str], int],
        *,
        symmetric: bool = True,
        source: str = "static-matrix",
        verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
    ) -> None:
        self._matrix = dict(matrix)
        self._symmetric = symmetric
        self._source = source
        self._status = verification_status

    async def estimate(
        self, pairs: list[tuple[str, str]], places: dict[str, PlaceCandidate]
    ) -> list[TravelTimeEstimate]:
        results: list[TravelTimeEstimate] = []
        for origin, destination in pairs:
            minutes = self._matrix.get((origin, destination))
            if minutes is None and self._symmetric:
                minutes = self._matrix.get((destination, origin))
            results.append(
                TravelTimeEstimate(
                    from_place_id=origin,
                    to_place_id=destination,
                    minutes=minutes,
                    mode="unspecified" if minutes is not None else None,
                    source=self._source if minutes is not None else None,
                    verification_status=(
                        self._status if minutes is not None else VerificationStatus.UNVERIFIED
                    ),
                )
            )
        return results


class HaversineTravelTimeProvider:
    """Straight-line distance divided by an assumed average speed.

    **Opt-in only.**  This is a geometric approximation, not routing: it
    ignores roads, ferries, traffic and terrain.  Results are always marked
    ``UNVERIFIED`` so they cannot be mistaken for a routing-API answer.  Do not
    make this the default in production -- plug in a real routing provider.
    """

    def __init__(self, *, average_speed_kmh: float = 35.0, minimum_minutes: int = 5) -> None:
        self.average_speed_kmh = average_speed_kmh
        self.minimum_minutes = minimum_minutes

    async def estimate(
        self, pairs: list[tuple[str, str]], places: dict[str, PlaceCandidate]
    ) -> list[TravelTimeEstimate]:
        results: list[TravelTimeEstimate] = []
        for origin, destination in pairs:
            distance = _haversine_km(places.get(origin), places.get(destination))
            minutes = (
                None
                if distance is None
                else max(self.minimum_minutes, round(distance / self.average_speed_kmh * 60))
            )
            results.append(
                TravelTimeEstimate(
                    from_place_id=origin,
                    to_place_id=destination,
                    minutes=minutes,
                    mode="approx-driving" if minutes is not None else None,
                    distance_km=round(distance, 2) if distance is not None else None,
                    source="haversine-approximation" if minutes is not None else None,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )
        return results


def _haversine_km(a: PlaceCandidate | None, b: PlaceCandidate | None) -> float | None:
    if a is None or b is None:
        return None
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return None
    radius_km = 6371.0
    lat1, lon1, lat2, lon2 = map(
        math.radians, (a.latitude, a.longitude, b.latitude, b.longitude)
    )
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(h))
