import uuid

from django.db import models


class Region(models.Model):
    region_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    l_dong_regn_code = models.CharField(
        max_length=10,
    )

    l_dong_signgu_code = models.CharField(
        max_length=10,
        blank=True,
        default="",
    )

    name = models.CharField(
        max_length=50,
    )

    name_en = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "regions"
        constraints = [
            models.UniqueConstraint(
                fields=["l_dong_regn_code", "l_dong_signgu_code"],
                name="unique_region_code",
            )
        ]

    def __str__(self):
        return self.name

class Trip(models.Model):
    class Status(models.TextChoices):
        COLLECTING_RESPONSES = "COLLECTING_RESPONSES", "응답 수집 중"
        PLANNING = "PLANNING", "일정 생성 중"
        READY = "READY", "일정 생성 완료"

    trip_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    owner = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="trips",
    )

    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="trips",
    )

    participant_limit = models.PositiveIntegerField()

    start_date = models.DateField()
    end_date = models.DateField()

    invite_code = models.CharField(
        max_length=50,
        unique=True,
    )

    invite_url = models.URLField(
        max_length=500,
    )

    invite_active = models.BooleanField(
        default=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.COLLECTING_RESPONSES,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "trips"

    def __str__(self):
        return f"{self.region.name} - {self.start_date}"

class Participant(models.Model):
    participant_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="participants",
    )

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="trip_participations",
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "participants"
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "user"],
                name="unique_trip_participant",
            ),
        ]

    def __str__(self):
        return f"{self.trip.trip_id} - {self.user.user_id}"