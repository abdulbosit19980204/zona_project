"""Xost loyihada: path("api/support/", include("support.urls"))."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

app_name = "support"

router = SimpleRouter()
router.register("bots", views.BotViewSet, basename="bot")
router.register("groups", views.GroupViewSet, basename="group")
router.register("entries", views.EntryViewSet, basename="entry")
router.register("messages", views.MessageViewSet, basename="message")

urlpatterns = [
    path("settings/", views.settings_view, name="settings"),
    path("stats/", views.stats, name="stats"),
    path("staff/", views.staff, name="staff"),
    path("", include(router.urls)),
]
