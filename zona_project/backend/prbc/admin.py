from django.contrib import admin

from .models import Change, Person, SyncRun, Task


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "status", "left_on", "tab_number", "prbc_user", "left_applied")
    list_filter = ("status", "left_applied", "link_manual")
    search_fields = ("full_name", "tab_number", "phone")
    raw_id_fields = ("staff_person", "member", "inv_employee", "tg_user")


admin.site.register(Change)
admin.site.register(SyncRun)
admin.site.register(Task)
