import secrets

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import TriptailorAPIException

from .models import Trip
from .serializers import TripCreateSerializer, TripDetailSerializer

class TripCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invite_code = self._generate_invite_code()
        invite_url = f"{settings.FRONTEND_BASE_URL}/trip/{invite_code}"

        serializer = TripCreateSerializer(
            data=request.data,
            context={
                "request": request,
                "invite_code": invite_code,
                "invite_url": invite_url,
            },
        )

        serializer.is_valid(raise_exception=True)
        trip = serializer.save()

        return Response(
            {
                "data": {
                    "tripId": str(trip.trip_id),
                    "participantLimit": trip.participant_limit,
                    "region": {
                        "regionId": str(trip.region.region_id),
                        "name": trip.region.name,
                    },
                    "travelPeriod": {
                        "startDate": trip.start_date,
                        "endDate": trip.end_date,
                    },
                    "inviteCode": trip.invite_code,
                    "inviteUrl": trip.invite_url,
                    "status": trip.status,
                    "createdAt": trip.created_at,
                }
            },
            status=status.HTTP_201_CREATED,
        )

    def _generate_invite_code(self):
        while True:
            invite_code = secrets.token_urlsafe(6)

            if not Trip.objects.filter(invite_code=invite_code).exists():
                return invite_code

class TripDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, trip_id):
        try:
            trip = Trip.objects.select_related(
                "owner",
                "region",
            ).get(
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

        serializer = TripDetailSerializer(trip)

        return Response(
            {
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )