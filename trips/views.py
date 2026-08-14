import secrets

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import TriptailorAPIException

from .models import Trip
from .serializers import TripCreateSerializer, TripDetailSerializer, MyTripListSerializer

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

    def delete(self, request, trip_id):
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

        if trip.owner_id != request.user.user_id:
            raise TriptailorAPIException(
                code="TRIP_ACCESS_DENIED",
                message="여행을 삭제할 권한이 없습니다.",
                status_code=403,
            )

        trip.deleted_at = timezone.now()
        trip.save(
            update_fields=[
                "deleted_at",
                "updated_at",
            ]
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

class MyTripListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            page = int(request.query_params.get("page", 0))
            size = int(request.query_params.get("size", 20))
        except ValueError:
            raise TriptailorAPIException(
                code="INVALID_REQUEST",
                message="page와 size는 정수여야 합니다.",
                status_code=400,
            )

        if page < 0 or size < 1:
            raise TriptailorAPIException(
                code="INVALID_REQUEST",
                message="page는 0 이상, size는 1 이상이어야 합니다.",
                status_code=400,
            )

        trips = (
            Trip.objects.filter(
                participants__user=request.user,
                deleted_at__isnull=True,
            )
            .select_related("region", "owner")
            .distinct()
            .order_by("-created_at")
        )

        total_elements = trips.count()

        start = page * size
        end = start + size

        paginated_trips = trips[start:end]

        serializer = MyTripListSerializer(
            paginated_trips,
            many=True,
            context={"request": request},
        )

        request_id = getattr(request, "request_id", None)

        return Response(
            {
                "data": serializer.data,
                "meta": {
                    "page": page,
                    "size": size,
                    "totalElements": total_elements,
                    "hasNext": end < total_elements,
                    "requestId": request_id,
                },
            },
            status=status.HTTP_200_OK,
        )

class InviteLinkRegenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, trip_id):
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

        if trip.owner_id != request.user.user_id:
            raise TriptailorAPIException(
                code="TRIP_ACCESS_DENIED",
                message="초대 링크를 재발급할 권한이 없습니다.",
                status_code=403,
            )

        invite_code = self._generate_invite_code()
        invite_url = f"{settings.FRONTEND_BASE_URL}/trip/{invite_code}"

        trip.invite_code = invite_code
        trip.invite_url = invite_url
        trip.invite_active = True

        trip.save(
            update_fields=[
                "invite_code",
                "invite_url",
                "invite_active",
                "updated_at",
            ]
        )

        return Response(
            {
                "data": {
                    "inviteCode": trip.invite_code,
                    "inviteUrl": trip.invite_url,
                    "inviteActive": trip.invite_active,
                }
            },
            status=status.HTTP_200_OK,
        )

    def _generate_invite_code(self):
        while True:
            invite_code = secrets.token_urlsafe(6)

            if not Trip.objects.filter(invite_code=invite_code).exists():
                return invite_code

class InviteLinkRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, trip_id):
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

        if trip.owner_id != request.user.user_id:
            raise TriptailorAPIException(
                code="TRIP_ACCESS_DENIED",
                message="초대 링크를 폐기할 권한이 없습니다.",
                status_code=403,
            )

        trip.invite_active = False

        trip.save(
            update_fields=[
                "invite_active",
                "updated_at",
            ]
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

class InvitationDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, invite_code):
        try:
            trip = Trip.objects.select_related("region").get(
                invite_code=invite_code,
                deleted_at__isnull=True,
            )
        except Trip.DoesNotExist:
            raise TriptailorAPIException(
                code="INVITATION_NOT_FOUND",
                message="초대 링크를 찾을 수 없습니다.",
                status_code=404,
            )

        if not trip.invite_active:
            raise TriptailorAPIException(
                code="INVITATION_CLOSED",
                message="사용할 수 없는 초대 링크입니다.",
                status_code=410,
            )

        return Response(
            {
                "data": {
                    "tripId": str(trip.trip_id),
                    "regionName": trip.region.name,
                    "participantLimit": trip.participant_limit,
                    "travelPeriod": {
                        "startDate": trip.start_date,
                        "endDate": trip.end_date,
                    },
                }
            },
            status=status.HTTP_200_OK,
        )