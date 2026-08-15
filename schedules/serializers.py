from rest_framework import serializers

from common.exceptions import TriptailorAPIException

from .models import Schedule


class ScheduleSerializer(serializers.ModelSerializer):
    scheduleId = serializers.UUIDField(
        source="schedule_id",
        read_only=True,
    )
    tripId = serializers.UUIDField(
        source="trip_id",
        read_only=True,
    )
    createdBy = serializers.UUIDField(
        source="created_by_id",
        read_only=True,
    )
    startTime = serializers.TimeField(
        source="start_time",
        required=False,
        allow_null=True,
    )
    endTime = serializers.TimeField(
        source="end_time",
        required=False,
        allow_null=True,
    )
    orderIndex = serializers.IntegerField(
        source="order_index",
        required=False,
    )
    sourceType = serializers.CharField(
        source="source_type",
        read_only=True,
    )
    isFixed = serializers.BooleanField(
        source="is_fixed",
        required=False,
    )
    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
    )
    updatedAt = serializers.DateTimeField(
        source="updated_at",
        read_only=True,
    )

    class Meta:
        model = Schedule
        fields = [
            "scheduleId",
            "tripId",
            "createdBy",
            "title",
            "description",
            "place",
            "date",
            "startTime",
            "endTime",
            "orderIndex",
            "sourceType",
            "isFixed",
            "createdAt",
            "updatedAt",
        ]
        extra_kwargs = {
            "description": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "place": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
        }

    def validate_orderIndex(self, value):
        if value < 0:
            raise TriptailorAPIException(
                code="INVALID_REQUEST",
                message="순서는 0 이상이어야 합니다.",
                field="orderIndex",
                status_code=400,
            )

        return value

    def validate(self, attrs):
        instance = self.instance

        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")

        if instance is not None:
            if "start_time" not in attrs:
                start_time = instance.start_time
            if "end_time" not in attrs:
                end_time = instance.end_time

        if start_time and end_time and start_time >= end_time:
            raise TriptailorAPIException(
                code="INVALID_SCHEDULE_TIME",
                message="종료 시간은 시작 시간보다 늦어야 합니다.",
                field="endTime",
                status_code=400,
            )

        trip = self.context.get("trip")
        if trip is None and instance is not None:
            trip = instance.trip

        date = attrs.get("date")
        if date is None and instance is not None:
            date = instance.date

        if trip is not None and date is not None:
            if date < trip.start_date or date > trip.end_date:
                raise TriptailorAPIException(
                    code="INVALID_SCHEDULE_DATE",
                    message="일정 날짜는 여행 기간 안에 있어야 합니다.",
                    field="date",
                    status_code=400,
                )

        return attrs

    def create(self, validated_data):
        if "order_index" not in validated_data:
            last = (
                Schedule.objects.filter(
                    trip=validated_data["trip"],
                    date=validated_data["date"],
                )
                .order_by("-order_index")
                .values_list("order_index", flat=True)
                .first()
            )
            validated_data["order_index"] = 0 if last is None else last + 1

        return super().create(validated_data)


class ScheduleOrderItemSerializer(serializers.Serializer):
    scheduleId = serializers.UUIDField()
    orderIndex = serializers.IntegerField()

    def validate_orderIndex(self, value):
        if value < 0:
            raise TriptailorAPIException(
                code="INVALID_REQUEST",
                message="순서는 0 이상이어야 합니다.",
                field="orderIndex",
                status_code=400,
            )

        return value


class ScheduleOrderRequestSerializer(serializers.Serializer):
    schedules = ScheduleOrderItemSerializer(many=True)

    def validate_schedules(self, value):
        if not value:
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="순서를 변경할 일정이 필요합니다.",
                field="schedules",
                status_code=422,
            )

        schedule_ids = [item["scheduleId"] for item in value]

        if len(schedule_ids) != len(set(schedule_ids)):
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="동일한 일정이 중복되어 있습니다.",
                field="schedules",
                status_code=422,
            )

        return value
