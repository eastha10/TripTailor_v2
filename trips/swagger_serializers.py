from rest_framework import serializers

from .serializers import (
    TripDetailSerializer,
    MyTripListSerializer,
)

class RegionSummarySerializer(serializers.Serializer):
    regionId = serializers.UUIDField()
    name = serializers.CharField()


class TravelPeriodSerializer(serializers.Serializer):
    startDate = serializers.DateField()
    endDate = serializers.DateField()


class TripCreateDataSerializer(serializers.Serializer):
    tripId = serializers.UUIDField()
    participantLimit = serializers.IntegerField()
    region = RegionSummarySerializer()
    travelPeriod = TravelPeriodSerializer()
    inviteCode = serializers.CharField()
    inviteUrl = serializers.URLField()
    status = serializers.CharField()
    createdAt = serializers.DateTimeField()


class TripCreateResponseSerializer(serializers.Serializer):
    data = TripCreateDataSerializer()


class InviteLinkDataSerializer(serializers.Serializer):
    inviteCode = serializers.CharField()
    inviteUrl = serializers.URLField()
    inviteActive = serializers.BooleanField()


class InviteLinkResponseSerializer(serializers.Serializer):
    data = InviteLinkDataSerializer()


class InvitationDetailDataSerializer(serializers.Serializer):
    tripId = serializers.UUIDField()
    regionName = serializers.CharField()
    participantLimit = serializers.IntegerField()
    travelPeriod = TravelPeriodSerializer()


class InvitationDetailResponseSerializer(serializers.Serializer):
    data = InvitationDetailDataSerializer()


class InvitationAcceptDataSerializer(serializers.Serializer):
    participantId = serializers.UUIDField()
    tripId = serializers.UUIDField()
    joinedAt = serializers.DateTimeField()


class InvitationAcceptResponseSerializer(serializers.Serializer):
    data = InvitationAcceptDataSerializer()

class TripDetailResponseSerializer(serializers.Serializer):
    data = TripDetailSerializer()


class PaginationMetaSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    size = serializers.IntegerField()
    totalElements = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    requestId = serializers.CharField(allow_null=True)


class MyTripListResponseSerializer(serializers.Serializer):
    data = MyTripListSerializer(many=True)
    meta = PaginationMetaSerializer()