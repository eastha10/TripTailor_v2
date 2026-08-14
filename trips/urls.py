from django.urls import path

from .views import TripCreateView, TripDetailView

urlpatterns = [
    path("", TripCreateView.as_view(), name="trip-create"),
    path("<uuid:trip_id>/", TripDetailView.as_view(), name="trip-detail"),
]