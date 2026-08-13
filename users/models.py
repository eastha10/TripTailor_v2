import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    user_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    email = models.EmailField(unique=True)

    phone_number = models.CharField(
        max_length=20,
        unique=True,
    )

    profile_image_url = models.URLField(
        blank=True,
        null=True,
    )

    auth_provider = models.CharField(
        max_length=20,
        default="local",
    )

    auth_provider_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "phone_number"]