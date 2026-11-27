"""Xost loyihada: path("api/prbc/", include("prbc.urls"))."""
from django.urls import path

from . import views

app_name = "prbc"

urlpatterns = [
    path("connection/", views.connection, name="connection"),
    path("connection/test/", views.test, name="test"),
    path("sync/", views.sync, name="sync"),
    path("overview/", views.overview, name="overview"),
    path("people/", views.people_list, name="people"),
    path("people/<int:pk>/", views.person_edit, name="person-edit"),
    path("people/<int:pk>/link/", views.person_link, name="person-link"),
    path("people/<int:pk>/left/", views.person_left, name="person-left"),
    path("link-candidates/", views.link_candidates, name="link-candidates"),
    path("changes/", views.changes, name="changes"),
    path("tasks/", views.task_list, name="tasks"),
    path("tasks/stats/", views.task_stats, name="task-stats"),
    path("tasks/<int:pk>/", views.task_detail, name="task-detail"),
    path("tasks/<int:pk>/status/", views.task_set_status, name="task-status"),
    path("tasks/backfill/", views.backfill, name="task-backfill"),
    path("control/", views.control, name="control"),
    path("assignable/", views.assignable, name="assignable"),
    path("projects/", views.projects, name="projects"),
    path("group-projects/", views.group_projects, name="group-projects"),
    path("outlet-status/", views.outlet_status, name="outlet-status"),
    path("access/", views.access_view, name="access"),
    path("access/scan/", views.access_scan, name="access-scan"),
    path("access/check/", views.access_check, name="access-check"),
    path("access/simulate/", views.access_simulate, name="access-simulate"),
    path("access/groups/", views.access_groups, name="access-groups"),
    path("access/log/<int:pk>/revert/", views.access_revert, name="access-revert"),
]
