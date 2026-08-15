from django.urls import path

from .views import (
    ScheduleDetailView,
    ScheduleListCreateView,
    ScheduleOrderView,
)


urlpatterns = [
    path(
        "trips/<uuid:trip_id>/schedules/",
        ScheduleListCreateView.as_view(),
        name="schedule-list-create",
    ),
    path(
        "trips/<uuid:trip_id>/schedules/order/",
        ScheduleOrderView.as_view(),
        name="schedule-order",
    ),
    path(
        "schedules/<uuid:schedule_id>/",
        ScheduleDetailView.as_view(),
        name="schedule-detail",
    ),
]
