from rest_framework import serializers


class MetaSerializer(serializers.Serializer):
    requestId = serializers.CharField()


class UserResponseSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    email = serializers.EmailField()
    username = serializers.CharField()
    phoneNumber = serializers.CharField()
    profileImageUrl = serializers.URLField(
        allow_null=True,
        required=False,
    )


class SignupDataSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    email = serializers.EmailField()
    username = serializers.CharField()
    phoneNumber = serializers.CharField()


class SignupResponseSerializer(serializers.Serializer):
    data = SignupDataSerializer()
    meta = MetaSerializer()


class LoginUserSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    email = serializers.EmailField()
    username = serializers.CharField()
    phoneNumber = serializers.CharField()


class LoginDataSerializer(serializers.Serializer):
    accessToken = serializers.CharField()
    refreshToken = serializers.CharField()
    user = LoginUserSerializer()


class LoginResponseSerializer(serializers.Serializer):
    data = LoginDataSerializer()
    meta = MetaSerializer()


class MeResponseSerializer(serializers.Serializer):
    data = UserResponseSerializer()
    meta = MetaSerializer()


class RefreshTokenRequestSerializer(serializers.Serializer):
    refreshToken = serializers.CharField()


class RefreshTokenDataSerializer(serializers.Serializer):
    accessToken = serializers.CharField()


class RefreshTokenResponseSerializer(serializers.Serializer):
    data = RefreshTokenDataSerializer()
    meta = MetaSerializer()


class LogoutRequestSerializer(serializers.Serializer):
    refreshToken = serializers.CharField()