from rest_framework import serializers

from .models import Participant


class TripParticipantSerializer(serializers.ModelSerializer):
    participantId = serializers.UUIDField(
        source="participant_id",
        read_only=True,
    )
    userId = serializers.UUIDField(
        source="user.user_id",
        read_only=True,
    )
    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )
    profileImageUrl = serializers.URLField(
        source="user.profile_image_url",
        read_only=True,
        allow_null=True,
    )
    role = serializers.CharField(read_only=True)
    hasSubmitted = serializers.BooleanField(
        source="has_submitted",
        read_only=True,
    )
    joinedAt = serializers.DateTimeField(
        source="joined_at",
        read_only=True,
    )

    class Meta:
        model = Participant
        fields = [
            "participantId",
            "userId",
            "username",
            "profileImageUrl",
            "role",
            "hasSubmitted",
            "joinedAt",
        ]


class TripParticipantListDataSerializer(serializers.Serializer):
    tripId = serializers.UUIDField()
    participantLimit = serializers.IntegerField()
    participantCount = serializers.IntegerField()
    submittedCount = serializers.IntegerField()
    participants = TripParticipantSerializer(many=True)


class TripParticipantListResponseSerializer(serializers.Serializer):
    data = TripParticipantListDataSerializer()
