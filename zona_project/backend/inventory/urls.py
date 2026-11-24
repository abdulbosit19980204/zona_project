"""Xost loyihada: path("api/inventory/", include("inventory.urls"))."""
from django.urls import path

from . import acks, io, views

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
    path("employees/<int:pk>/ack/", acks.employee_ack, name="employee-ack"),
    path("acks/", acks.acks, name="acks"),
    path("acks/bulk/", acks.acks_bulk, name="acks-bulk"),
    path("acks/export/", acks.acks_export, name="acks-export"),
    path("acks/<int:pk>/", acks.ack_detail, name="ack"),
    path("acks/<int:pk>/revoke/", acks.ack_revoke, name="ack-revoke"),
    path("acks/<int:pk>/signature/", acks.ack_signature, name="ack-signature"),
    path("public/ack/<str:token>/", acks.public_ack, name="public-ack"),
    path("public/ack/<str:token>/sign/", acks.public_sign, name="public-sign"),
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
