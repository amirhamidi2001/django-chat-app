from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os


def user_directory_path(instance, filename):
    """
    File will be uploaded to MEDIA_ROOT/chat/<sender_id>/<filename>
    """
    # Sanitize filename
    name, ext = os.path.splitext(filename)
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_filename = f"{safe_name}{ext}"
    return f"chat/{instance.sender.id}/{safe_filename}"


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

    @classmethod
    def get_or_create_status(cls, user):
        """
        Helper method to get or create user status
        """
        status, created = cls.objects.get_or_create(
            user=user, defaults={"is_online": False, "last_seen": timezone.now()}
        )
        return status


class Message(models.Model):
    """
    Model to store private messages between users
    Enhanced with file attachment support
    """

    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_messages"
    )
    content = models.TextField(blank=True)  # NEW: Allow empty for file-only messages
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    # NEW: File attachment field
    file = models.FileField(
        upload_to=user_directory_path, blank=True, null=True, max_length=255
    )
    file_name = models.CharField(max_length=255, blank=True)  # Original filename
    file_size = models.IntegerField(default=0)  # Size in bytes
    file_type = models.CharField(max_length=50, blank=True)  # MIME type

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["sender", "receiver", "-timestamp"]),
            models.Index(fields=["receiver", "sender", "-timestamp"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["-timestamp"]),
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
        Get total count of messages in a conversation
        """
        from django.db.models import Q

        return cls.objects.filter(
            Q(sender=user1, receiver=user2) | Q(sender=user2, receiver=user1)
        ).count()

    @property
    def is_image(self):
        """
        Check if the attached file is an image
        """
        if not self.file_type:
            return False
        return self.file_type.startswith("image/")

    @property
    def file_extension(self):
        """
        Get file extension
        """
        if self.file_name:
            return os.path.splitext(self.file_name)[1].lower()
        return ""
