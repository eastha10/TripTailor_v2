from rest_framework import serializers

from .serializers import ScheduleSerializer


class ScheduleResponseSerializer(serializers.Serializer):
    data = ScheduleSerializer()


class ScheduleListResponseSerializer(serializers.Serializer):
    data = ScheduleSerializer(many=True)


class ScheduleOrderItemRequestSerializer(serializers.Serializer):
    scheduleId = serializers.UUIDField()
    orderIndex = serializers.IntegerField()


class ScheduleOrderRequestSerializer(serializers.Serializer):
    schedules = ScheduleOrderItemRequestSerializer(many=True)


class ScheduleOrderResponseSerializer(serializers.Serializer):
    data = ScheduleSerializer(many=True)
