from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from common.exceptions import TriptailorAPIException

from .serializers import LoginSerializer, SignupSerializer, ProfileUpdateSerializer

from drf_spectacular.utils import extend_schema

from .swagger_serializers import (
    SignupResponseSerializer,
    LoginResponseSerializer,
    MeResponseSerializer,
    RefreshTokenRequestSerializer,
    RefreshTokenResponseSerializer,
    LogoutRequestSerializer,
)


class SignupView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="회원가입",
        request=SignupSerializer,
        responses={201: SignupResponseSerializer},
    )
    def post(self, request):
        serializer = SignupSerializer(data=request.data)

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="입력값을 확인해주세요.",
                field=serializer.errors,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        user = serializer.save()

        return Response(
            {
                "data": {
                    "userId": str(user.user_id),
                    "email": user.email,
                    "username": user.username,
                    "phoneNumber": user.phone_number,
                },
                "meta": {
                    "requestId": request.request_id,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="로그인",
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="INVALID_CREDENTIALS",
                message="이메일 또는 비밀번호가 올바르지 않습니다.",
                field=None,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        result = serializer.validated_data
        user = result["user"]

        return Response(
            {
                "data": {
                    "accessToken": result["accessToken"],
                    "refreshToken": result["refreshToken"],
                    "user": {
                        "userId": str(user.user_id),
                        "email": user.email,
                        "username": user.username,
                        "phoneNumber": user.phone_number,
                    },
                },
                "meta": {
                    "requestId": request.request_id,
                },
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Users"],
        summary="내 정보 조회",
        responses={200: MeResponseSerializer},
    )
    def get(self, request):
        user = request.user

        return Response(
            {
                "data": {
                    "userId": str(user.user_id),
                    "email": user.email,
                    "username": user.username,
                    "phoneNumber": user.phone_number,
                    "profileImageUrl": user.profile_image_url,
                },
                "meta": {
                    "requestId": request.request_id,
                },
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )

        if not serializer.is_valid():
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="입력값을 확인해주세요.",
                field=serializer.errors,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        user = serializer.save()

        return Response(
            {
                "data": {
                    "userId": str(user.user_id),
                    "email": user.email,
                    "username": user.username,
                    "phoneNumber": user.phone_number,
                    "profileImageUrl": user.profile_image_url,
                },
                "meta": {
                    "requestId": request.request_id,
                },
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="로그아웃",
        request=LogoutRequestSerializer,
        responses={204: None},
    )
    def delete(self, request):
        refresh_token = request.data.get("refreshToken")

        if not refresh_token:
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="refreshToken이 필요합니다.",
                field="refreshToken",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

        except TokenError:
            raise TriptailorAPIException(
                code="INVALID_TOKEN",
                message="유효하지 않은 refresh token입니다.",
                field=None,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="Access Token 재발급",
        request=RefreshTokenRequestSerializer,
        responses={200: RefreshTokenResponseSerializer},
    )
    def post(self, request):
        refresh_token = request.data.get("refreshToken")

        if not refresh_token:
            raise TriptailorAPIException(
                code="VALIDATION_FAILED",
                message="refreshToken이 필요합니다.",
                field="refreshToken",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serializer = TokenRefreshSerializer(
            data={"refresh": refresh_token}
        )

        try:
            serializer.is_valid(raise_exception=True)

        except (TokenError, InvalidToken):
            raise TriptailorAPIException(
                code="TOKEN_EXPIRED",
                message="유효하지 않거나 만료된 refresh token입니다.",
                field=None,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "data": {
                    "accessToken": serializer.validated_data["access"],
                },
                "meta": {
                    "requestId": request.request_id,
                },
            },
            status=status.HTTP_200_OK,
        )
