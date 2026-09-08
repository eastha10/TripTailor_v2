from trips.models import ParticipantPreference
from triptailor_ai import TripPlanningRequest
from django.core.exceptions import ObjectDoesNotExist


BUDGET_BAND_MAP = {
    ParticipantPreference.BudgetBand.LOW:
        "UP_TO_200000_KRW",

    ParticipantPreference.BudgetBand.MID:
        "FROM_200000_TO_400000_KRW",

    ParticipantPreference.BudgetBand.HIGH:
        "FROM_400000_TO_600000_KRW",
}


ACCOMMODATION_TYPE_MAP = {
    ParticipantPreference.AccommodationType.HOTEL:
        "HOTEL",

    ParticipantPreference.AccommodationType.PENSION:
        "EMOTIONAL_STAY_OR_PENSION",

    ParticipantPreference.AccommodationType.GUESTHOUSE:
        "GUESTHOUSE",

    ParticipantPreference.AccommodationType.ETC:
        "NO_PREFERENCE",
}

async def build_trip_planning_request(trip):
    participants = await _get_participants_with_preferences(trip)

    return TripPlanningRequest.model_validate({
        "tripId": str(trip.trip_id),
        "region": {
            "regionId": str(trip.region.region_id),
            "name": trip.region.name,
        },
        "travelPeriod": {
            "startDate": trip.start_date.isoformat(),
            "endDate": trip.end_date.isoformat(),
        },
        "participantLimit": trip.participant_limit,
        "participants": [
            {
                "participantId": str(participant.participant_id),
                "budgetBand": BUDGET_BAND_MAP[
                    participant.preference.budget_band
                ],
                "accommodationType": ACCOMMODATION_TYPE_MAP[
                    participant.preference.accommodation_type
                ],
                "mustHaves": participant.preference.must_haves,
                "additionalNotes": (
                    participant.preference.additional_notes or ""
                ),
            }
            for participant in participants
        ],
    })

async def _get_participants_with_preferences(trip):
    participants = []

    queryset = (
        trip.participants
        .select_related("preference")
        .order_by("joined_at")
    )

    async for participant in queryset:
        try:
            participant.preference
        except ObjectDoesNotExist:
            continue

        participants.append(participant)

    return participants