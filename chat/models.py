from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User


class Message(models.Model):
    """
    Model to store private messages between users
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
            models.Index(fields=["sender", "receiver", "timestamp"]),
        ]

    def __str__(self):
        return (
            f"{self.sender.username} to {self.receiver.username}: {self.content[:50]}"
        )
