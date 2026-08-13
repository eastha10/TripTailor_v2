from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import SignupSerializer, LoginSerializer


class SignupView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = SignupSerializer(data=request.data)

        if serializer.is_valid():
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
                        "requestId": None,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "입력값을 확인해주세요.",
                    "field": serializer.errors,
                    "requestId": None,
                }
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
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
                        "requestId": None,
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
                    "field": None,
                    "requestId": None,
                }
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response(
            {
                "data": {
                    "userId": str(user.user_id),
                    "email": user.email,
                    "username": user.username,
                    "phoneNumber": user.phone_number,
                },
                "meta": {
                    "requestId": None,
                },
            },
            status=status.HTTP_200_OK,
        )

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        refresh_token = request.data.get("refreshToken")

        if not refresh_token:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_FAILED",
                        "message": "refreshToken이 필요합니다.",
                        "field": "refreshToken",
                        "requestId": None,
                    }
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(status=status.HTTP_204_NO_CONTENT)

        except TokenError:
            return Response(
                {
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "유효하지 않은 refresh token입니다.",
                        "field": None,
                        "requestId": None,
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )