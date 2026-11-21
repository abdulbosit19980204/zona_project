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
    path("analytics/workload/", views.analytics_workload, name="analytics-workload"),
    path("analytics/speed/", views.analytics_speed, name="analytics-speed"),
    path("media/upload/", views.media_upload, name="media-upload"),
    path("media/<int:pk>/file/", views.media_file, name="media-file"),
    path("images/", views.image_types, name="images"),
    path("images/label/", views.image_label, name="images-label"),
    path("images/ignore/", views.image_ignore, name="images-ignore"),
    path("tasks/", views.support_tasks, name="tasks"),
    path("tasks/test/", views.support_task_test, name="tasks-test"),
    path("tasks/<int:pk>/<str:action>/", views.support_task_action, name="tasks-action"),
    path("tg-users/", views.tg_users, name="tg-users"),
    path("tg-users/<int:pk>/link/", views.tg_user_link, name="tg-user-link"),
    path("staff-people/", views.staff_people_search, name="staff-people"),
    path("ai/jobs/", views.ai_jobs, name="ai-jobs"),
    path("ai/suggestions/", views.suggestions, name="ai-suggestions"),
    path("ai/suggestions/<int:pk>/<str:action>/", views.suggestion_decide, name="ai-suggestion-decide"),
    path("history/", views.history_jobs, name="history"),
    path("history/continue/", views.history_continue, name="history-continue"),
    path("history/<int:pk>/", views.history_job_action, name="history-action"),
    path("mtproto/send-code/", views.mtproto_send_code, name="mtproto-send-code"),
    path("mtproto/sign-in/", views.mtproto_sign_in, name="mtproto-sign-in"),
    path("mtproto/logout/", views.mtproto_logout, name="mtproto-logout"),
    path("", include(router.urls)),
]
