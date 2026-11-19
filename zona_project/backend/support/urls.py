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
    path("analytics/", views.analytics, name="analytics"),
    path("media/upload/", views.media_upload, name="media-upload"),
    path("media/<int:pk>/file/", views.media_file, name="media-file"),
    path("images/", views.image_types, name="images"),
    path("images/label/", views.image_label, name="images-label"),
    path("tg-users/", views.tg_users, name="tg-users"),
    path("tg-users/<int:pk>/link/", views.tg_user_link, name="tg-user-link"),
    path("staff-people/", views.staff_people_search, name="staff-people"),
    path("ai/jobs/", views.ai_jobs, name="ai-jobs"),
    path("ai/suggestions/", views.suggestions, name="ai-suggestions"),
    path("ai/suggestions/<int:pk>/<str:action>/", views.suggestion_decide, name="ai-suggestion-decide"),
    path("history/", views.history_jobs, name="history"),
    path("mtproto/send-code/", views.mtproto_send_code, name="mtproto-send-code"),
    path("mtproto/sign-in/", views.mtproto_sign_in, name="mtproto-sign-in"),
    path("mtproto/logout/", views.mtproto_logout, name="mtproto-logout"),
    path("", include(router.urls)),
]
