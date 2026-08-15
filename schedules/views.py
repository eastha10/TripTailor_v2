from datetime import date as date_type

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import TriptailorAPIException
from trips.models import Trip

from .models import Schedule
from .serializers import ScheduleOrderRequestSerializer, ScheduleSerializer
from .swagger_serializers import (
    ScheduleListResponseSerializer,
    ScheduleOrderRequestSerializer as ScheduleOrderSwaggerSerializer,
    ScheduleOrderResponseSerializer,
    ScheduleResponseSerializer,
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


def get_schedule(schedule_id):
    try:
        schedule = Schedule.objects.select_related("trip").get(
            schedule_id=schedule_id,
        )
    except Schedule.DoesNotExist:
        raise TriptailorAPIException(
            code="SCHEDULE_NOT_FOUND",
            message="일정을 찾을 수 없습니다.",
            status_code=404,
        )

    if schedule.trip.deleted_at is not None:
        raise TriptailorAPIException(
            code="TRIP_NOT_FOUND",
            message="여행을 찾을 수 없습니다.",
            status_code=404,
        )

    return schedule


class ScheduleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Schedules"],
        summary="여행 일정 목록 조회",
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="특정 날짜(YYYY-MM-DD)의 일정만 조회",
                required=False,
            ),
        ],
        responses={
            200: ScheduleListResponseSerializer,
        },
    )
    def get(self, request, trip_id):
        trip = get_active_trip(trip_id)
        ensure_trip_access(trip, request.user)

        schedules = Schedule.objects.filter(trip=trip).order_by(
            "date",
            "order_index",
            "start_time",
        )

        date_param = request.query_params.get("date")
        if date_param is not None:
            try:
                target_date = date_type.fromisoformat(date_param)
            except ValueError:
                raise TriptailorAPIException(
                    code="INVALID_REQUEST",
                    message="date는 YYYY-MM-DD 형식이어야 합니다.",
                    field="date",
                    status_code=400,
                )

            schedules = schedules.filter(date=target_date)

        serializer = ScheduleSerializer(schedules, many=True)

        return Response(
            {
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Schedules"],
        summary="일정 직접 추가",
        request=ScheduleSerializer,
        responses={
            201: ScheduleResponseSerializer,
        },
    )
    def post(self, request, trip_id):
        trip = get_active_trip(trip_id)
        ensure_trip_access(trip, request.user)

        serializer = ScheduleSerializer(
            data=request.data,
            context={"trip": trip},
        )

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="입력값을 확인해주세요.",
                field=serializer.errors,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        schedule = serializer.save(
            trip=trip,
            created_by=request.user,
            source_type=Schedule.SourceType.MANUAL,
        )

        return Response(
            {
                "data": ScheduleSerializer(schedule).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Schedules"],
        summary="일정 수정",
        request=ScheduleSerializer,
        responses={
            200: ScheduleResponseSerializer,
        },
    )
    def patch(self, request, schedule_id):
        schedule = get_schedule(schedule_id)
        ensure_trip_access(schedule.trip, request.user)

        serializer = ScheduleSerializer(
            schedule,
            data=request.data,
            partial=True,
            context={"trip": schedule.trip},
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

    @extend_schema(
        tags=["Schedules"],
        summary="일정 삭제",
        responses={
            204: None,
        },
    )
    def delete(self, request, schedule_id):
        schedule = get_schedule(schedule_id)
        ensure_trip_access(schedule.trip, request.user)

        schedule.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ScheduleOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Schedules"],
        summary="일정 순서 변경",
        request=ScheduleOrderSwaggerSerializer,
        responses={
            200: ScheduleOrderResponseSerializer,
        },
    )
    def patch(self, request, trip_id):
        trip = get_active_trip(trip_id)
        ensure_trip_access(trip, request.user)

        serializer = ScheduleOrderRequestSerializer(data=request.data)

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="입력값을 확인해주세요.",
                field=serializer.errors,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        schedule_data = serializer.validated_data["schedules"]
        schedule_ids = [item["scheduleId"] for item in schedule_data]

        schedules = list(
            Schedule.objects.filter(
                schedule_id__in=schedule_ids,
                trip=trip,
            )
        )

        if len(schedules) != len(schedule_ids):
            raise TriptailorAPIException(
                code="SCHEDULE_NOT_FOUND",
                message="해당 여행에 속하지 않거나 존재하지 않는 일정이 있습니다.",
                field="schedules",
                status_code=404,
            )

        order_map = {
            item["scheduleId"]: item["orderIndex"]
            for item in schedule_data
        }

        with transaction.atomic():
            for schedule in schedules:
                schedule.order_index = order_map[schedule.schedule_id]
                schedule.save(update_fields=["order_index", "updated_at"])

        updated_schedules = Schedule.objects.filter(trip=trip).order_by(
            "date",
            "order_index",
            "start_time",
        )

        return Response(
            {
                "data": ScheduleSerializer(updated_schedules, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
