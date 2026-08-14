from django.urls import path

from .views import TripCreateView


urlpatterns = [
    path("", TripCreateView.as_view(), name="trip-create"),
]