import httpx

from django.conf import settings
from urllib.parse import unquote


class TourAPIClient:
    def __init__(self):
        self.base_url = settings.TOUR_API_BASE_URL
        self.service_key = unquote(settings.TOUR_API_SERVICE_KEY)

    async def get_places_by_region(
        self,
        regn_code: str,
        signgu_code: str = "",
        *,
        page_no: int = 1,
        num_of_rows: int = 100,
    ) -> list[dict]:
        url = f"{self.base_url}/areaBasedList2"

        params = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": "TripTailor",
            "_type": "json",
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "lDongRegnCd": regn_code,
            "arrange": "O",
        }

        if signgu_code:
            params["lDongSignguCd"] = signgu_code

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)

        response.raise_for_status()

        data = response.json()
        return self._extract_items(data)

    async def get_festivals_by_region(
        self,
        regn_code: str,
        signgu_code: str = "",
        *,
        start_date,
        end_date,
        page_no: int = 1,
        num_of_rows: int = 100,
    ) -> list[dict]:
        url = f"{self.base_url}/searchFestival2"

        params = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": "TripTailor",
            "_type": "json",
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "eventStartDate": start_date.strftime("%Y%m%d"),
            "eventEndDate": end_date.strftime("%Y%m%d"),
            "lDongRegnCd": regn_code,
            "arrange": "O",
        }

        if signgu_code:
            params["lDongSignguCd"] = signgu_code

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)

        response.raise_for_status()

        data = response.json()
        return self._extract_items(data)

    async def get_stays_by_region(
        self,
        regn_code: str,
        signgu_code: str = "",
        *,
        page_no: int = 1,
        num_of_rows: int = 100,
    ) -> list[dict]:
        url = f"{self.base_url}/searchStay2"

        params = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": "TripTailor",
            "_type": "json",
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "lDongRegnCd": regn_code,
            "arrange": "O",
        }

        if signgu_code:
            params["lDongSignguCd"] = signgu_code

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)

        response.raise_for_status()

        data = response.json()
        return self._extract_items(data)

    @staticmethod
    def _extract_items(data: dict) -> list[dict]:
        body = data.get("response", {}).get("body", {})
        items = body.get("items")

        if not isinstance(items, dict):
            return []

        item = items.get("item", [])

        if isinstance(item, list):
            return item

        if isinstance(item, dict):
            return [item]

        return []