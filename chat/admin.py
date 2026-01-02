from django.contrib import admin
from .models import Message, UserStatus


@admin.register(UserStatus)
class UserStatusAdmin(admin.ModelAdmin):
    list_display = ["user", "is_online", "last_seen"]
    list_filter = ["is_online"]
    search_fields = ["user__username"]
    readonly_fields = ["last_seen"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["sender", "receiver", "content", "timestamp", "is_read"]
    list_filter = ["timestamp", "is_read"]
    search_fields = ["sender__username", "receiver__username", "content"]
    readonly_fields = ["timestamp"]
