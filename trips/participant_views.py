from django.db.models import Exists, OuterRef
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from common.exceptions import TriptailorAPIException

from .models import Participant, ParticipantPreference, Trip
from .participant_serializers import (
    TripParticipantListResponseSerializer,
    TripParticipantSerializer,
)


class TripParticipantListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Participants"],
        summary="여행 참여자 목록 조회",
        responses={
            200: TripParticipantListResponseSerializer,
        },
    )
    def get(self, request, trip_id):
        try:
            trip = Trip.objects.get(
                trip_id=trip_id,
                deleted_at__isnull=True,
            )
        except Trip.DoesNotExist:
            raise TriptailorAPIException(
                code="TRIP_NOT_FOUND",
                message="여행을 찾을 수 없습니다.",
                status_code=404,
            )

        is_owner = trip.owner_id == request.user.user_id
        is_participant = trip.participants.filter(
            user=request.user,
        ).exists()

        if not is_owner and not is_participant:
            raise TriptailorAPIException(
                code="TRIP_ACCESS_DENIED",
                message="해당 여행에 접근할 권한이 없습니다.",
                status_code=403,
            )

        participants = (
            Participant.objects.filter(trip=trip)
            .select_related("user")
            .annotate(
                has_submitted=Exists(
                    ParticipantPreference.objects.filter(
                        participant_id=OuterRef("pk"),
                    )
                )
            )
            .order_by("joined_at")
        )

        serializer = TripParticipantSerializer(
            participants,
            many=True,
        )

        submitted_count = sum(
            1 for item in serializer.data if item["hasSubmitted"]
        )

        return Response(
            {
                "data": {
                    "tripId": str(trip.trip_id),
                    "participantLimit": trip.participant_limit,
                    "participantCount": len(serializer.data),
                    "submittedCount": submitted_count,
                    "participants": serializer.data,
                }
            },
            status=status.HTTP_200_OK,
        )
