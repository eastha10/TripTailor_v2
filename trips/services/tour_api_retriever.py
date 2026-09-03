from datetime import datetime

from trips.models import Region
from trips.services.tour_api_client import TourAPIClient

from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.common import VerificationStatus


class TourAPIPlaceRetriever:
    def __init__(self):
        self.client = TourAPIClient()

    async def retrieve(
        self,
        request,
        normalized_preferences,
        constraints,
    ) -> list[PlaceCandidate]:

        if not constraints.region_id:
            return []

        region = await Region.objects.aget(
            region_id=constraints.region_id
        )

        places = await self.client.get_places_by_region(
            regn_code=region.l_dong_regn_code,
            signgu_code=region.l_dong_signgu_code,
            num_of_rows=constraints.limit,
        )

        return [
            self._to_place_candidate(
                place=place,
                region=region,
            )
            for place in places
        ]

    def _to_place_candidate(
        self,
        place: dict,
        region: Region,
    ) -> PlaceCandidate:

        return PlaceCandidate(
            place_id=str(place["contentid"]),
            name=place["title"],
            region=region.name,

            latitude=self._to_float(place.get("mapy")),
            longitude=self._to_float(place.get("mapx")),

            categories=self._build_categories(place),
            tags=[],

            description=None,
            image_url=place.get("firstimage") or None,

            opening_hours=None,
            closed_days=[],
            closed_dates=[],

            estimated_stay_minutes=None,
            estimated_cost_per_person=None,

            accessibility=[],
            dietary_tags=[],

            source_ids=[
                f"tour-api:{place['contentid']}"
            ],

            updated_at=self._parse_datetime(
                place.get("modifiedtime")
            ),

            verification_status=VerificationStatus.UNVERIFIED,
            confidence=0.5,
        )

    @staticmethod
    def _to_float(value: str | None) -> float | None:
        if not value:
            return None

        return float(value)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None

        return datetime.strptime(
            value,
            "%Y%m%d%H%M%S",
        )

    @staticmethod
    def _build_categories(place: dict) -> list[str]:
        categories = []

        for key in (
            "contenttypeid",
            "cat1",
            "cat2",
            "cat3",
            "lclsSystm1",
            "lclsSystm2",
            "lclsSystm3",
        ):
            value = place.get(key)

            if value:
                categories.append(value)

        return categories