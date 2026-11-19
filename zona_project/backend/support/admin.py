from django.contrib import admin

from .models import Entry, Group, Message


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "source", "uses", "updated_at")
    list_filter = ("kind", "status", "source")
    search_fields = ("title", "answer")


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("title", "bot", "mode", "is_active", "last_message_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "group", "status", "stage", "confidence")
    list_filter = ("status", "stage")
    search_fields = ("text", "ocr_text")
