from datetime import datetime

from trips.models import Region
from trips.services.tour_api_client import TourAPIClient

from triptailor_ai.schemas.place import PlaceCandidate, PlaceKind
from triptailor_ai.schemas.common import VerificationStatus


# TourAPI contentTypeId → AI PlaceKind
CONTENT_TYPE_TO_KIND = {
    "12": PlaceKind.ATTRACTION,     # 관광지
    "14": PlaceKind.ATTRACTION,     # 문화시설
    "15": PlaceKind.FESTIVAL,       # 축제/공연/행사
    "25": PlaceKind.ATTRACTION,     # 여행코스
    "28": PlaceKind.ATTRACTION,     # 레포츠
    "32": PlaceKind.ACCOMMODATION,  # 숙박
    "38": PlaceKind.ATTRACTION,     # 쇼핑
    "39": PlaceKind.RESTAURANT,     # 음식점
}


# AI accommodationType → TourAPI 숙박 세부 분류 코드
#
# Django → AI 변환은 ai_request_builder.py에서:
# HOTEL      → HOTEL
# PENSION    → EMOTIONAL_STAY_OR_PENSION
# GUESTHOUSE → GUESTHOUSE
# ETC        → NO_PREFERENCE
ACCOMMODATION_TYPE_CODES = {
    "HOTEL": {
        "AC010100",  # 호텔
    },

    "EMOTIONAL_STAY_OR_PENSION": {
        "AC030100",  # 펜션
    },

    "GUESTHOUSE": {
        "AC060200",  # 게스트하우스
    },

    # Django의 ETC를 AI에서는 NO_PREFERENCE로 넘기지만,
    # 백엔드에서는 아래 "기타 숙박" 후보들로 필터링한다.
    "NO_PREFERENCE": {
        "AC020100",  # 콘도
        "AC020200",  # 레지던스
        "AC030200",  # 한옥스테이
        "AC030300",  # 농어촌민박
        "AC030400",  # 홈스테이
        "AC040100",  # 모텔
        "AC050100",  # 일반야영장
        "AC050200",  # 오토캠핑장
        "AC050300",  # 카라반
        "AC050400",  # 글램핑장
        "AC060100",  # 유스호스텔
    },
}


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

        # -------------------------
        # 숙박 전용 검색
        # -------------------------
        if constraints.kinds == [PlaceKind.ACCOMMODATION]:
            fetch_limit = max(constraints.limit * 10, 100)

            stays = await self.client.get_stays_by_region(
                regn_code=region.l_dong_regn_code,
                signgu_code=region.l_dong_signgu_code,
                num_of_rows=fetch_limit,
            )

            # TourAPI에서 다른 시/군 결과가 섞일 가능성에 대비한 재필터링
            stays = [
                stay
                for stay in stays
                if stay.get("lDongRegnCd") == region.l_dong_regn_code
                and (
                    not region.l_dong_signgu_code
                    or stay.get("lDongSignguCd")
                    == region.l_dong_signgu_code
                )
            ]

            # 참여자들이 선택한 숙박 타입을 모은다.
            preferred_types = set()

            for participant in request.participants:
                accommodation_type = participant.accommodation_type

                if accommodation_type is None:
                    continue

                if hasattr(accommodation_type, "value"):
                    accommodation_type = accommodation_type.value

                preferred_types.add(str(accommodation_type))

            # 여러 참여자의 선호가 다르면 후보 타입을 합집합으로 제공한다.
            allowed_codes = set()

            for accommodation_type in preferred_types:
                allowed_codes.update(
                    ACCOMMODATION_TYPE_CODES.get(
                        accommodation_type,
                        set(),
                    )
                )

            # 숙박 선호가 존재할 때만 타입 필터링
            if allowed_codes:
                stays = [
                    stay
                    for stay in stays
                    if stay.get("lclsSystm3") in allowed_codes
                ]

            return [
                self._to_place_candidate(
                    place=stay,
                    region=region,
                    kind=PlaceKind.ACCOMMODATION,
                )
                for stay in stays[:constraints.limit]
            ]

        # -------------------------
        # 일반 장소 검색
        # -------------------------
        places = await self.client.get_places_by_region(
            regn_code=region.l_dong_regn_code,
            signgu_code=region.l_dong_signgu_code,
            num_of_rows=constraints.limit,
        )

        # -------------------------
        # 축제 검색
        # -------------------------
        festivals = await self.client.get_festivals_by_region(
            regn_code=region.l_dong_regn_code,
            signgu_code=region.l_dong_signgu_code,
            start_date=request.travel_period.start_date,
            end_date=request.travel_period.end_date,
            num_of_rows=constraints.limit,
        )

        # 축제 API에서 다른 시/군 결과가 섞여 들어와 재필터링
        festivals = [
            festival
            for festival in festivals
            if festival.get("lDongRegnCd")
            == region.l_dong_regn_code
            and (
                not region.l_dong_signgu_code
                or festival.get("lDongSignguCd")
                == region.l_dong_signgu_code
            )
        ]

        candidates = [
            self._to_place_candidate(
                place=place,
                region=region,
            )
            for place in places
        ]

        candidates.extend(
            self._to_place_candidate(
                place=festival,
                region=region,
                kind=PlaceKind.FESTIVAL,
            )
            for festival in festivals
        )

        return candidates

    def _to_place_candidate(
        self,
        place: dict,
        region: Region,
        kind: PlaceKind | None = None,
    ) -> PlaceCandidate:

        # 일반 장소라면 contenttypeid 기준 자동 분류
        if kind is None:
            kind = CONTENT_TYPE_TO_KIND.get(
                str(place.get("contenttypeid"))
            )

        event_period = None

        if kind == PlaceKind.FESTIVAL:
            start_date = self._parse_date(
                place.get("eventstartdate")
            )
            end_date = self._parse_date(
                place.get("eventenddate")
            )

            if start_date and end_date:
                event_period = {
                    "startDate": start_date,
                    "endDate": end_date,
                }

        return PlaceCandidate(
            place_id=str(place["contentid"]),
            name=place["title"],
            kind=kind,
            region=region.name,

            latitude=self._to_float(
                place.get("mapy")
            ),
            longitude=self._to_float(
                place.get("mapx")
            ),

            categories=self._build_categories(place),
            tags=[],

            description=None,
            image_url=place.get("firstimage") or None,

            event_period=event_period,

            # TourAPI에서 숙박 가격을 제공하지 않으므로 null
            price_per_night_per_person=None,

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
    def _to_float(
        value: str | None,
    ) -> float | None:
        if not value:
            return None

        return float(value)

    @staticmethod
    def _parse_datetime(
        value: str | None,
    ) -> datetime | None:
        if not value:
            return None

        return datetime.strptime(
            value,
            "%Y%m%d%H%M%S",
        )

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None

        return datetime.strptime(
            value,
            "%Y%m%d",
        ).date()

    @staticmethod
    def _build_categories(
        place: dict,
    ) -> list[str]:
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