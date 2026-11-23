"""Xost loyihada: path("api/inventory/", include("inventory.urls"))."""
from django.urls import path

from . import io, views

app_name = "inventory"

urlpatterns = [
    path("bootstrap/", views.bootstrap, name="bootstrap"),
    path("items/", views.items, name="items"),
    path("items/check-serial/", views.check_serial, name="check-serial"),
    path("items/export/", io.export_items, name="items-export"),
    path("items/import/", io.import_items, name="items-import"),
    path("items/<int:pk>/", views.item_detail, name="item"),
    path("items/<int:pk>/restore/", views.item_restore, name="item-restore"),
    path("photos/", views.photo_upload, name="photos"),
    path("photos/<int:pk>/", views.photo_delete, name="photo"),
    path("photos/<int:pk>/file/", views.photo_file, name="photo-file"),
    path("employees/", views.employees, name="employees"),
    path("employees/export/", io.employees_export, name="employees-export"),
    path("employees/template/", io.employees_template, name="employees-template"),
    path("employees/import/", io.employees_import, name="employees-import"),
    path("employees/from-staff/", views.employees_from_staff, name="employees-from-staff"),
    path("employees/<int:pk>/", views.employee_detail, name="employee"),
    path("branches/", views.branches, name="branches"),
    path("branches/<int:pk>/", views.branch_detail, name="branch"),
    path("catalog/", views.catalog_save, name="catalog"),
    path("users/", views.users, name="users"),
    path("users/generate/", views.users_generate, name="users-generate"),
    path("users/credentials/", io.credentials, name="users-credentials"),
    path("users/<int:pk>/", views.user_detail, name="user"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="user-reset"),
    path("logs/", views.logs, name="logs"),
    path("stats/", views.stats, name="stats"),
    path("stats/export/", io.export_report, name="stats-export"),
]
