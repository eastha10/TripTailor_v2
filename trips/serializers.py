from rest_framework import serializers

from common.exceptions import TriptailorAPIException
from .models import Region, Trip


class TravelPeriodSerializer(serializers.Serializer):
    startDate = serializers.DateField()
    endDate = serializers.DateField()

    def validate(self, attrs):
        if attrs["startDate"] > attrs["endDate"]:
            raise TriptailorAPIException(
                code="INVALID_TRAVEL_PERIOD",
                message="여행 시작일은 종료일보다 늦을 수 없습니다.",
                field="travelPeriod",
                status_code=400,
            )

        return attrs


class TripCreateSerializer(serializers.Serializer):
    participantLimit = serializers.IntegerField()
    regionId = serializers.UUIDField()
    travelPeriod = TravelPeriodSerializer()

    def validate_participantLimit(self, value):
        if value < 1:
            raise TriptailorAPIException(
                code="INVALID_PARTICIPANT_LIMIT",
                message="여행 인원은 1명 이상이어야 합니다.",
                field="participantLimit",
                status_code=400,
            )

        return value

    def validate_regionId(self, value):
        if not Region.objects.filter(region_id=value).exists():
            raise TriptailorAPIException(
                code="REGION_NOT_FOUND",
                message="존재하지 않는 지역입니다.",
                field="regionId",
                status_code=404,
            )

        return value

    def create(self, validated_data):
        travel_period = validated_data.pop("travelPeriod")
        region_id = validated_data.pop("regionId")

        region = Region.objects.get(region_id=region_id)

        trip = Trip.objects.create(
            owner=self.context["request"].user,
            region=region,
            participant_limit=validated_data["participantLimit"],
            start_date=travel_period["startDate"],
            end_date=travel_period["endDate"],
            invite_code=self.context["invite_code"],
            invite_url=self.context["invite_url"],
        )

        return trip