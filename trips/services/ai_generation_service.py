from asgiref.sync import async_to_sync
from django.db import transaction

from schedules.models import Schedule, AccommodationStay
from triptailor_ai import TripPlanningService

from trips.services.ai_request_builder import build_trip_planning_request
from trips.services.tour_api_retriever import TourAPIPlaceRetriever


def generate_and_save_trip_itinerary(trip, user):
    async def _generate():
        ai_request = await build_trip_planning_request(trip)

        service = TripPlanningService(
            retriever=TourAPIPlaceRetriever(),
        )

        try:
            return await service.generate(ai_request)
        finally:
            await service.aclose()

    result = async_to_sync(_generate)()

    # AI 생성 자체가 실패했거나 일정이 없는 경우에는 DB 저장하지 않음
    if (
        result.status.value != "NEEDS_REVIEW"
        or result.itinerary is None
    ):
        return result

    _save_ai_result(
        trip=trip,
        user=user,
        result=result,
    )

    return result


@transaction.atomic
def _save_ai_result(trip, user, result):
    itinerary = result.itinerary

    # 이전 AI 생성 결과만 제거
    # MANUAL 일정/숙박은 유지
    Schedule.objects.filter(
        trip=trip,
        source_type=Schedule.SourceType.AI,
    ).delete()

    AccommodationStay.objects.filter(
        trip=trip,
        source_type=AccommodationStay.SourceType.AI,
    ).delete()

    schedules = []

    for day in itinerary.days:
        for item in day.items:
            schedules.append(
                Schedule(
                    trip=trip,
                    created_by=user,
                    title=item.place_name,
                    description=item.description,
                    place=item.place_name,
                    date=item.date,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    order_index=item.sequence,
                    source_type=Schedule.SourceType.AI,
                )
            )

    if schedules:
        Schedule.objects.bulk_create(schedules)

    stays = []

    for stay in itinerary.stays:
        stays.append(
            AccommodationStay(
                trip=trip,
                created_by=user,
                place_id=stay.place_id,
                place_name=stay.place_name,
                check_in_date=stay.check_in_date,
                check_out_date=stay.check_out_date,
                price_per_night_per_person=(
                    stay.price_per_night_per_person
                ),
                image_url=stay.image_url,
                description=stay.description,
                source_type=AccommodationStay.SourceType.AI,
            )
        )

    if stays:
        AccommodationStay.objects.bulk_create(stays)