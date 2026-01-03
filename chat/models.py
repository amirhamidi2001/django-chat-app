from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os
import uuid


def user_directory_path(instance, filename):
    """
    File will be uploaded to MEDIA_ROOT/chat/<sender_id>/<uuid>_<filename>
    UUID prefix prevents filename collisions
    """
    name, ext = os.path.splitext(filename)
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    unique_filename = f"{uuid.uuid4().hex[:8]}_{safe_name}{ext}"
    return f"chat/{instance.sender.id}/{unique_filename}"


class UserStatus(models.Model):
    """
    Tracks online/offline status of users in real-time
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="status", primary_key=True
    )
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "User Status"
        verbose_name_plural = "User Statuses"
        indexes = [
            models.Index(fields=["is_online"]),
        ]

    def __str__(self):
        status = "Online" if self.is_online else "Offline"
        return f"{self.user.username} - {status}"


class Message(models.Model):
    """
    Model to store private messages between users
    Enhanced with UUIDs and security features
    """

    # NEW: UUID as primary key for security (prevents enumeration)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_messages"
    )
    content = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    # File attachment fields
    file = models.FileField(
        upload_to=user_directory_path, blank=True, null=True, max_length=255
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.IntegerField(default=0)
    file_type = models.CharField(max_length=50, blank=True)

    # NEW: Security and audit fields
    edited = models.BooleanField(default=False)  # Track if message was edited
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted = models.BooleanField(default=False)  # Soft delete
    deleted_at = models.DateTimeField(null=True, blank=True)

    # NEW: IP address for audit trail (optional)
    sender_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["sender", "receiver", "-timestamp"]),
            models.Index(fields=["receiver", "sender", "-timestamp"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["deleted"]),  # NEW: Index for soft deletes
        ]

    def __str__(self):
        if self.file:
            return f"{self.sender.username} to {self.receiver.username}: [File: {self.file_name}]"
        return (
            f"{self.sender.username} to {self.receiver.username}: {self.content[:50]}"
        )

    @classmethod
    def get_conversation_count(cls, user1, user2):
        """
        Get total count of non-deleted messages in a conversation
        """
        from django.db.models import Q

        return cls.objects.filter(
            Q(sender=user1, receiver=user2) | Q(sender=user2, receiver=user1),
            deleted=False,  # NEW: Exclude soft-deleted messages
        ).count()

    @property
    def is_image(self):
        """Check if the attached file is an image"""
        if not self.file_type:
            return False
        return self.file_type.startswith("image/")

    @property
    def file_extension(self):
        """Get file extension"""
        if self.file_name:
            return os.path.splitext(self.file_name)[1].lower()
        return ""

    def soft_delete(self):
        """
        NEW: Soft delete message (don't actually remove from DB)
        """
        self.deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted", "deleted_at"])

    def can_be_read_by(self, user):
        """
        NEW: Security check - can this user read this message?
        """
        return user in [self.sender, self.receiver]

    def can_be_edited_by(self, user):
        """
        NEW: Security check - can this user edit this message?
        Only sender can edit within 15 minutes
        """
        if user != self.sender:
            return False

        time_limit = timezone.now() - timezone.timedelta(minutes=15)
        return self.timestamp >= time_limit and not self.deleted


# NEW: Audit log model for security events
class SecurityLog(models.Model):
    """
    Log security-relevant events for audit trail
    """

    EVENT_TYPES = [
        ("message_send", "Message Sent"),
        ("message_read", "Message Read"),
        ("file_upload", "File Uploaded"),
        ("file_download", "File Downloaded"),
        ("unauthorized_access", "Unauthorized Access Attempt"),
        ("validation_failed", "Validation Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    message = models.ForeignKey(
        Message, on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["event_type", "-timestamp"]),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous"
        return f"{user_str} - {self.event_type} - {self.timestamp}"
