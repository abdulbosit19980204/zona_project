from django.contrib import admin

from .models import (AIProvider, AITaskConfig, AIUsage, Authority, ChangeRequest, Department, EdgeCase, Event, Member,
                     Process, ProcessRole, Profile, Synonym, System, Task, TaskFallback, Team)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "lead", "order")
    list_filter = ("department",)


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "requested_by", "decided_by", "created_at")
    list_filter = ("status", "kind")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "order")
    list_editable = ("order",)


@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    list_editable = ("order",)


class AuthorityInline(admin.TabularInline):
    model = Authority
    extra = 0


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "department", "manager", "phone", "telegram", "order")
    list_filter = ("department", "is_team")
    search_fields = ("name", "role", "email", "phone", "telegram")
    inlines = [AuthorityInline]


class ProcessRoleInline(admin.TabularInline):
    model = ProcessRole
    extra = 0


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ("name", "system", "order")
    list_filter = ("system",)
    search_fields = ("name",)
    inlines = [ProcessRoleInline]


class TaskFallbackInline(admin.TabularInline):
    model = TaskFallback
    extra = 0
    fields = ("order", "member", "condition")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "process", "is_custom")
    list_filter = ("owner", "process__system", "is_custom")
    search_fields = ("title", "note")
    list_select_related = ("owner", "process")
    inlines = [TaskFallbackInline]


@admin.register(EdgeCase)
class EdgeCaseAdmin(admin.ModelAdmin):
    list_display = ("situation", "first_owner", "then_text", "order")


@admin.register(Synonym)
class SynonymAdmin(admin.ModelAdmin):
    list_display = ("words", "updated_at")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "member", "phone", "telegram")
    list_filter = ("role",)


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_active", "last_check_ok", "updated_at")
    exclude = ("api_key_enc", "models_cache")  # kalit faqat sayt ichidagi "AI sozlamalari"dan kiritiladi


@admin.register(AITaskConfig)
class AITaskConfigAdmin(admin.ModelAdmin):
    list_display = ("task", "enabled", "provider", "model", "effort", "max_tokens")


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ("at", "task", "provider", "model", "ok", "input_tokens", "output_tokens", "latency_ms", "user")
    list_filter = ("task", "provider", "ok")
    readonly_fields = [f.name for f in AIUsage._meta.fields]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("at", "kind", "subject", "from_name", "to_name", "actor")
    list_filter = ("kind",)
    readonly_fields = [f.name for f in Event._meta.fields]
