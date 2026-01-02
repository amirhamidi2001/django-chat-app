from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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
    Enhanced with better indexing for pagination
    """

    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_messages"
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            # Enhanced compound index for efficient pagination
            models.Index(fields=["sender", "receiver", "-timestamp"]),
            models.Index(fields=["receiver", "sender", "-timestamp"]),
            models.Index(fields=["is_read"]),
            # NEW: Index for faster pagination queries
            models.Index(fields=["-timestamp"]),
        ]

    def __str__(self):
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
