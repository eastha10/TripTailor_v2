from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


from .models import User


class SignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "username",
            "phone_number",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def create(self, validated_data):
        user = User(
            email=validated_data["email"],
            username=validated_data["username"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"]
        password = attrs["password"]

        user = authenticate(
            username=email,
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        refresh = RefreshToken.for_user(user)

        return {
            "accessToken": str(refresh.access_token),
            "refreshToken": str(refresh),
            "user": user,
        }