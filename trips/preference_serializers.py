from rest_framework import serializers

from common.exceptions import TriptailorAPIException

from .models import ParticipantPreference


class PreferenceSerializer(serializers.ModelSerializer):
    preferenceId = serializers.UUIDField(
        source="preference_id",
        read_only=True,
    )
    participantId = serializers.UUIDField(
        source="participant_id",
        read_only=True,
    )
    userId = serializers.UUIDField(
        source="participant.user.user_id",
        read_only=True,
    )
    username = serializers.CharField(
        source="participant.user.username",
        read_only=True,
    )
    budgetBand = serializers.CharField(
        source="budget_band",
    )
    accommodationType = serializers.CharField(
        source="accommodation_type",
    )
    mustHaves = serializers.CharField(
        source="must_haves",
        required=False,
        allow_blank=True,
    )
    additionalNotes = serializers.CharField(
        source="additional_notes",
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    submittedAt = serializers.DateTimeField(
        source="submitted_at",
        read_only=True,
    )
    updatedAt = serializers.DateTimeField(
        source="updated_at",
        read_only=True,
    )

    class Meta:
        model = ParticipantPreference
        fields = [
            "preferenceId",
            "participantId",
            "userId",
            "username",
            "budgetBand",
            "accommodationType",
            "mustHaves",
            "additionalNotes",
            "submittedAt",
            "updatedAt",
        ]

    def validate_budgetBand(self, value):
        valid = set(ParticipantPreference.BudgetBand.values)

        if value not in valid:
            raise TriptailorAPIException(
                code="INVALID_BUDGET_BAND",
                message="예산 유형이 올바르지 않습니다.",
                field="budgetBand",
                status_code=400,
            )

        return value

    def validate_accommodationType(self, value):
        valid = set(ParticipantPreference.AccommodationType.values)

        if value not in valid:
            raise TriptailorAPIException(
                code="INVALID_ACCOMMODATION_TYPE",
                message="숙소 유형이 올바르지 않습니다.",
                field="accommodationType",
                status_code=400,
            )

        return value

    def create(self, validated_data):
        return ParticipantPreference.objects.create(
            participant=self.context["participant"],
            **validated_data,
        )


class PreferenceResponseSerializer(serializers.Serializer):
    data = PreferenceSerializer()


class PreferenceListDataSerializer(serializers.Serializer):
    tripId = serializers.UUIDField()
    participantCount = serializers.IntegerField()
    submittedCount = serializers.IntegerField()
    preferences = PreferenceSerializer(many=True)


class PreferenceListResponseSerializer(serializers.Serializer):
    data = PreferenceListDataSerializer()
