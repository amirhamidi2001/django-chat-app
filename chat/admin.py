from django.contrib import admin
from django.utils.html import format_html
from .models import Message, UserStatus, SecurityLog


@admin.register(UserStatus)
class UserStatusAdmin(admin.ModelAdmin):
    list_display = ["user", "is_online", "last_seen"]
    list_filter = ["is_online"]
    search_fields = ["user__username"]
    readonly_fields = ["last_seen"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        "id_preview",  # NEW: Show short UUID
        "sender",
        "receiver",
        "content_preview",
        "file_preview",
        "timestamp",
        "is_read",
        "deleted",  # NEW
    ]
    list_filter = [
        "timestamp",
        "is_read",
        "file_type",
        "deleted",
        "edited",
    ]  # NEW filters
    search_fields = ["sender__username", "receiver__username", "content", "file_name"]
    readonly_fields = [
        "id",
        "timestamp",
        "file_preview_large",
        "sender_ip",  # NEW
        "edited",
        "edited_at",
        "deleted",
        "deleted_at",
    ]

    fieldsets = (
        (
            "Message Info",
            {"fields": ("id", "sender", "receiver", "content", "timestamp", "is_read")},
        ),
        (
            "File Attachment",
            {
                "fields": (
                    "file",
                    "file_name",
                    "file_size",
                    "file_type",
                    "file_preview_large",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Security & Audit",
            {  # NEW fieldset
                "fields": ("sender_ip", "edited", "edited_at", "deleted", "deleted_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def id_preview(self, obj):
        """Show first 8 characters of UUID"""
        return str(obj.id)[:8]

    id_preview.short_description = "ID"

    def content_preview(self, obj):
        """Show first 50 characters of content"""
        if obj.content:
            return obj.content[:50] + ("..." if len(obj.content) > 50 else "")
        elif obj.file:
            return f"[File: {obj.file_name}]"
        return "[Empty]"

    content_preview.short_description = "Content"

    def file_preview(self, obj):
        """Show file attachment indicator"""
        if not obj.file:
            return "-"

        icon = "🖼️" if obj.is_image else "📎"
        size = self._format_size(obj.file_size)

        return format_html(
            '<span style="font-size: 1.2em;">{}</span> {} ({})',
            icon,
            obj.file_name[:20] + ("..." if len(obj.file_name) > 20 else ""),
            size,
        )

    file_preview.short_description = "File"

    def file_preview_large(self, obj):
        """Show large preview in detail view"""
        if not obj.file:
            return "No file attached"

        html = f"""
        <div style="margin: 10px 0;">
            <strong>File Name:</strong> {obj.file_name}<br>
            <strong>File Size:</strong> {self._format_size(obj.file_size)}<br>
            <strong>File Type:</strong> {obj.file_type}<br>
            <strong>File URL:</strong> <a href="{obj.file.url}" target="_blank">{obj.file.url}</a><br>
        """

        if obj.is_image:
            html += f"""
            <br>
            <strong>Preview:</strong><br>
            <a href="{obj.file.url}" target="_blank">
                <img src="{obj.file.url}" style="max-width: 300px; max-height: 300px; border: 1px solid #ddd; border-radius: 4px; padding: 5px;">
            </a>
            """

        html += "</div>"
        return format_html(html)

    file_preview_large.short_description = "File Details"

    def _format_size(self, bytes_size):
        """Format file size in human-readable format"""
        if bytes_size == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB"]
        size = bytes_size
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        return f"{size:.1f} {units[unit_index]}"


# NEW: Security log admin
@admin.register(SecurityLog)
class SecurityLogAdmin(admin.ModelAdmin):
    list_display = [
        "id_preview",
        "timestamp",
        "user",
        "event_type",
        "description_preview",
        "ip_address",
    ]
    list_filter = [
        "event_type",
        "timestamp",
    ]
    search_fields = [
        "user__username",
        "description",
        "ip_address",
    ]
    readonly_fields = [
        "id",
        "user",
        "event_type",
        "message",
        "description",
        "ip_address",
        "user_agent",
        "timestamp",
    ]

    fieldsets = (
        (
            "Event Info",
            {"fields": ("id", "timestamp", "event_type", "user", "message")},
        ),
        ("Details", {"fields": ("description", "ip_address", "user_agent")}),
    )

    def id_preview(self, obj):
        """Show first 8 characters of UUID"""
        return str(obj.id)[:8]

    id_preview.short_description = "ID"

    def description_preview(self, obj):
        """Show first 100 characters of description"""
        return obj.description[:100] + ("..." if len(obj.description) > 100 else "")

    description_preview.short_description = "Description"

    def has_add_permission(self, request):
        """Prevent manual creation of logs"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of logs"""
        return request.user.is_superuser
