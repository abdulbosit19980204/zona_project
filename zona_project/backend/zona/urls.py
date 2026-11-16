"""Xost loyihada: path("", include("zona.urls"))  ->  /api/...
WebSocket manzillari alohida: zona.routing.websocket_urlpatterns (asgi.py)."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views, views_admin, views_ai, views_approvals, views_auth, views_staff, views_knowledge

app_name = "zona"

router = SimpleRouter()
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("teams", views.TeamViewSet, basename="team")
router.register("members", views.MemberViewSet, basename="member")
router.register("authorities", views.AuthorityViewSet, basename="authority")
router.register("systems", views.SystemViewSet, basename="system")
router.register("zones", views.ZoneViewSet, basename="zone")
router.register("processes", views.ProcessViewSet, basename="process")
router.register("roles", views.ProcessRoleViewSet, basename="role")
router.register("tasks", views.TaskViewSet, basename="task")
router.register("edge-cases", views.EdgeCaseViewSet, basename="edgecase")
router.register("staff/projects", views_staff.StaffProjectViewSet, basename="staff-project")
router.register("staff/people", views_staff.StaffPersonViewSet, basename="staff-person")
router.register("synonyms", views.SynonymViewSet, basename="synonym")
router.register("approvals", views_approvals.ChangeRequestViewSet, basename="approval")
router.register("admin/users", views_admin.UserViewSet, basename="admin-user")
router.register("admin/ai/providers", views_admin.AIProviderViewSet, basename="ai-provider")
router.register("admin/ai/tasks", views_admin.AITaskViewSet, basename="ai-task")
router.register("admin/ai/usage", views_admin.AIUsageViewSet, basename="ai-usage")

urlpatterns = [
    path("", views.index, name="index"),
    path("api/auth/login/", views_auth.login, name="login"),
    path("api/auth/refresh/", views_auth.refresh, name="refresh"),
    path("api/auth/logout/", views_auth.logout, name="logout"),
    path("api/auth/me/", views_auth.me, name="me"),
    path("api/auth/password/", views_auth.change_password, name="password"),
    path("api/state/", views.state, name="state"),
    path("api/events/", views.events, name="events"),
    path("api/search/", views.search, name="search"),
    path("api/search/explain/", views.search_explain, name="search-explain"),
    path("api/ai/route/", views_ai.route, name="ai-route"),
    path("api/ai/person/", views_ai.person, name="ai-person"),
    path("api/ai/audit/", views_ai.audit, name="ai-audit"),
    path("api/admin/ai/translate/", views_admin.translate, name="ai-translate"),
    path("api/staff/", views_staff.staff, name="staff"),
    path("api/staff/import/", views_staff.staff_import, name="staff-import"),
    path("api/staff/export.<str:fmt>", views_staff.staff_export, name="staff-export"),
    path("api/export.xlsx", views.export_xlsx, name="export"),
    path("api/bot/ask/", views_knowledge.bot_ask, name="bot-ask"),
    path("api/knowledge/export.<str:fmt>", views_knowledge.knowledge_export, name="knowledge-export"),
    path("api/", include(router.urls)),
]
