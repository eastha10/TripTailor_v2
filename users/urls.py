from django.urls import path
from .views import SignupView, LoginView, LogoutView, MeView, RefreshTokenView


urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("sessions/", LoginView.as_view(), name="login"),
    path("sessions/current/", LogoutView.as_view(), name="logout"),
    path("sessions/refresh/", RefreshTokenView.as_view(), name="token_refresh")
]