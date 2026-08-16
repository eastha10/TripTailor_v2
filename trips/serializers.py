from rest_framework import serializers

from common.exceptions import TriptailorAPIException
from .models import Participant, Region, Trip
from django.db import transaction


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

    @transaction.atomic
    def create(self, validated_data):
        travel_period = validated_data.pop("travelPeriod")
        region_id = validated_data.pop("regionId")

        region = Region.objects.get(region_id=region_id)
        owner = self.context["request"].user

        trip = Trip.objects.create(
            owner=owner,
            region=region,
            participant_limit=validated_data["participantLimit"],
            start_date=travel_period["startDate"],
            end_date=travel_period["endDate"],
            invite_code=self.context["invite_code"],
            invite_url=self.context["invite_url"],
        )

        Participant.objects.create(
            trip=trip,
            user=owner,
            role=Participant.Role.LEADER,
        )

        return trip

class TripDetailSerializer(serializers.ModelSerializer):
    tripId = serializers.UUIDField(
        source="trip_id",
        read_only=True,
    )

    ownerId = serializers.UUIDField(
        source="owner.user_id",
        read_only=True,
    )

    participantLimit = serializers.IntegerField(
        source="participant_limit",
        read_only=True,
    )

    region = serializers.SerializerMethodField()
    travelPeriod = serializers.SerializerMethodField()

    inviteCode = serializers.CharField(
        source="invite_code",
        read_only=True,
    )

    inviteUrl = serializers.URLField(
        source="invite_url",
        read_only=True,
    )

    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
    )

    class Meta:
        model = Trip
        fields = [
            "tripId",
            "ownerId",
            "participantLimit",
            "region",
            "travelPeriod",
            "inviteCode",
            "inviteUrl",
            "status",
            "createdAt",
        ]

    def get_region(self, obj):
        return {
            "regionId": str(obj.region.region_id),
            "name": obj.region.name,
        }

    def get_travelPeriod(self, obj):
        return {
            "startDate": obj.start_date,
            "endDate": obj.end_date,
        }

class MyTripListSerializer(serializers.ModelSerializer):
    tripId = serializers.UUIDField(
        source="trip_id",
        read_only=True,
    )

    regionName = serializers.CharField(
        source="region.name",
        read_only=True,
    )

    startDate = serializers.DateField(
        source="start_date",
        read_only=True,
    )

    endDate = serializers.DateField(
        source="end_date",
        read_only=True,
    )

    participantLimit = serializers.IntegerField(
        source="participant_limit",
        read_only=True,
    )

    isOwner = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "tripId",
            "regionName",
            "startDate",
            "endDate",
            "participantLimit",
            "status",
            "isOwner",
        ]

    def get_isOwner(self, obj):
        request = self.context.get("request")

        if request is None:
            return False

        return obj.owner_id == request.user.user_id