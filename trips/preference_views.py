from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from common.exceptions import (
    PreferenceAlreadySubmitted,
    PreferenceClosed,
    PreferenceNotFound,
    TriptailorAPIException,
)
from .models import Participant, ParticipantPreference, Trip
from .preference_serializers import (
    PreferenceListResponseSerializer,
    PreferenceResponseSerializer,
    PreferenceSerializer,
)


def get_active_trip(trip_id):
    try:
        return Trip.objects.get(
            trip_id=trip_id,
            deleted_at__isnull=True,
        )
    except Trip.DoesNotExist:
        raise TriptailorAPIException(
            code="TRIP_NOT_FOUND",
            message="여행을 찾을 수 없습니다.",
            status_code=404,
        )


def ensure_trip_access(trip, user):
    is_owner = trip.owner_id == user.user_id
    is_participant = trip.participants.filter(user=user).exists()

    if not is_owner and not is_participant:
        raise TriptailorAPIException(
            code="TRIP_ACCESS_DENIED",
            message="해당 여행에 접근할 권한이 없습니다.",
            status_code=403,
        )


def get_my_participant(trip, user):
    try:
        return Participant.objects.get(trip=trip, user=user)
    except Participant.DoesNotExist:
        raise TriptailorAPIException(
            code="TRIP_ACCESS_DENIED",
            message="해당 여행의 참여자만 설문을 작성할 수 있습니다.",
            status_code=403,
        )


def ensure_collecting_responses(trip):
    if trip.status != Trip.Status.COLLECTING_RESPONSES:
        raise PreferenceClosed()


class PreferenceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Preferences"],
        summary="여행 설문 목록 조회",
        responses={
            200: PreferenceListResponseSerializer,
        },
    )
    def get(self, request, trip_id):
        trip = get_active_trip(trip_id)
        ensure_trip_access(trip, request.user)

        preferences = (
            ParticipantPreference.objects.filter(participant__trip=trip)
            .select_related("participant__user")
            .order_by("submitted_at")
        )

        serializer = PreferenceSerializer(preferences, many=True)

        return Response(
            {
                "data": {
                    "tripId": str(trip.trip_id),
                    "participantCount": trip.participants.count(),
                    "submittedCount": len(serializer.data),
                    "preferences": serializer.data,
                }
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Preferences"],
        summary="내 설문 제출",
        request=PreferenceSerializer,
        responses={
            201: PreferenceResponseSerializer,
        },
    )
    def post(self, request, trip_id):
        trip = get_active_trip(trip_id)
        participant = get_my_participant(trip, request.user)
        ensure_collecting_responses(trip)

        if hasattr(participant, "preference"):
            raise PreferenceAlreadySubmitted()

        serializer = PreferenceSerializer(
            data=request.data,
            context={"participant": participant},
        )

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="입력값을 확인해주세요.",
                field=serializer.errors,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        preference = serializer.save()

        return Response(
            {
                "data": PreferenceSerializer(preference).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PreferenceMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Preferences"],
        summary="내 설문 조회",
        responses={
            200: PreferenceResponseSerializer,
        },
    )
    def get(self, request, trip_id):
        trip = get_active_trip(trip_id)
        participant = get_my_participant(trip, request.user)

        try:
            preference = participant.preference
        except ParticipantPreference.DoesNotExist:
            raise PreferenceNotFound()

        return Response(
            {
                "data": PreferenceSerializer(preference).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Preferences"],
        summary="내 설문 수정",
        request=PreferenceSerializer,
        responses={
            200: PreferenceResponseSerializer,
        },
    )
    def patch(self, request, trip_id):
        trip = get_active_trip(trip_id)
        participant = get_my_participant(trip, request.user)
        ensure_collecting_responses(trip)

        try:
            preference = participant.preference
        except ParticipantPreference.DoesNotExist:
            raise PreferenceNotFound()

        serializer = PreferenceSerializer(
            preference,
            data=request.data,
            partial=True,
        )

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="입력값을 확인해주세요.",
                field=serializer.errors,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serializer.save()

        return Response(
            {
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
