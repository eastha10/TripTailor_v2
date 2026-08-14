from rest_framework import serializers

from .models import Region, Trip


class TravelPeriodSerializer(serializers.Serializer):
    startDate = serializers.DateField()
    endDate = serializers.DateField()

    def validate(self, attrs):
        if attrs["startDate"] > attrs["endDate"]:
            raise serializers.ValidationError(
                "여행 시작일은 종료일보다 늦을 수 없습니다."
            )

        return attrs


class TripCreateSerializer(serializers.Serializer):
    participantLimit = serializers.IntegerField(min_value=1)
    regionId = serializers.UUIDField()
    travelPeriod = TravelPeriodSerializer()

    def validate_regionId(self, value):
        if not Region.objects.filter(region_id=value).exists():
            raise serializers.ValidationError(
                "존재하지 않는 지역입니다."
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