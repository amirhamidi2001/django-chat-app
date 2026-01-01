from django.contrib import admin
from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["sender", "receiver", "content", "timestamp", "is_read"]
    list_filter = ["timestamp", "is_read"]
    search_fields = ["sender__username", "receiver__username", "content"]
    readonly_fields = ["timestamp"]
