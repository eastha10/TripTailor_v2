from django.urls import path

from .participant_views import TripParticipantListView
from .views import TripCreateView, TripDetailView, InviteLinkRegenerateView, InviteLinkRevokeView

urlpatterns = [
    path("", TripCreateView.as_view(), name="trip-create"),
    path("<uuid:trip_id>/", TripDetailView.as_view(), name="trip-detail"),
    path("<uuid:trip_id>/participants/", TripParticipantListView.as_view(), name="trip-participant-list"),
    path("<uuid:trip_id>/invite-link/regenerate/", InviteLinkRegenerateView.as_view(), name="invite-link-regenerate"),
    path("<uuid:trip_id>/invite-link/", InviteLinkRevokeView.as_view(), name="invite-link-revoke"),
]