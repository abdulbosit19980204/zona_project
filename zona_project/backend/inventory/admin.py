from django.contrib import admin

from .models import Access, Branch, DeviceType, Employee, Item, Location, Log, Org


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "region", "status", "conductor")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("inv_number", "branch", "device_type", "brand", "model", "serial", "condition", "is_deleted")
    list_filter = ("branch", "condition", "is_deleted")
    search_fields = ("inv_number", "serial", "model")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "branch", "org", "project", "is_active")
    list_filter = ("branch", "org", "is_active")
    search_fields = ("full_name", "phone")


@admin.register(Access)
class AccessAdmin(admin.ModelAdmin):
    list_display = ("user", "level")
    exclude = ("password_enc",)


admin.site.register([Org, Location, DeviceType])


@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ("at", "user", "branch", "entity", "action", "summary")
    list_filter = ("action", "entity", "branch")
