from django.urls import path

from .views import SignupView, LoginView, MeView, LogoutView


urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("sessions/", LoginView.as_view(), name="login"),
    path("sessions/current/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
]