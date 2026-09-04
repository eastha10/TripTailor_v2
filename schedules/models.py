import uuid

from django.conf import settings
from django.db import models


class Schedule(models.Model):
    class SourceType(models.TextChoices):
        AI = "AI", "AI 생성"
        MANUAL = "MANUAL", "직접 추가"

    schedule_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_schedules",
    )

    title = models.CharField(max_length=200)

    description = models.TextField(
        blank=True,
        null=True,
    )

    place = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )

    date = models.DateField()

    start_time = models.TimeField(
        blank=True,
        null=True,
    )

    end_time = models.TimeField(
        blank=True,
        null=True,
    )

    order_index = models.PositiveIntegerField(
        default=0,
    )

    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.MANUAL,
    )

    is_fixed = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "schedules"
        ordering = [
            "date",
            "order_index",
            "start_time",
        ]
        indexes = [
            models.Index(
                fields=["trip", "date", "order_index"],
            ),
        ]

    def __str__(self):
        return self.title

class AccommodationStay(models.Model):
    class SourceType(models.TextChoices):
        AI = "AI", "AI 생성"
        MANUAL = "MANUAL", "직접 추가"

    stay_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.CASCADE,
        related_name="accommodation_stays",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_accommodation_stays",
    )

    place_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    place_name = models.CharField(
        max_length=200,
    )

    check_in_date = models.DateField()
    check_out_date = models.DateField()

    price_per_night_per_person = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    image_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.MANUAL,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "accommodation_stays"
        ordering = ["check_in_date"]

    def __str__(self):
        return self.place_name
