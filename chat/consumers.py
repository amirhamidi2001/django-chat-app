import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db import models
from .models import Message


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Asynchronous WebSocket consumer for handling real-time chat
    """

    async def connect(self):
        """
        Called when WebSocket connection is established
        """
        # Get the current user from scope (set by AuthMiddlewareStack)
        self.user = self.scope["user"]

        # Reject connection if user is not authenticated
        if not self.user.is_authenticated:
            await self.close()
            return

        # Get the other user's username from URL route
        self.other_username = self.scope["url_route"]["kwargs"]["username"]

        # Create a unique room name for this conversation
        # Sort usernames to ensure same room for both users
        usernames = sorted([self.user.username, self.other_username])
        self.room_name = f"chat_{'_'.join(usernames)}"
        self.room_group_name = f"chat_{self.room_name}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # Accept the WebSocket connection
        await self.accept()

        # Send previous messages to the connected user
        await self.send_message_history()

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed
        """
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket
        """
        data = json.loads(text_data)
        message_content = data.get("message", "")

        if not message_content.strip():
            return

        # Save message to database
        message = await self.save_message(message_content)

        # Broadcast message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message_content,
                "sender": self.user.username,
                "timestamp": message.timestamp.isoformat(),
                "message_id": message.id,
            },
        )

    async def chat_message(self, event):
        """
        Handler for messages sent to the group
        """
        # Send message to WebSocket
        await self.send(
            text_data=json.dumps(
                {
                    "message": event["message"],
                    "sender": event["sender"],
                    "timestamp": event["timestamp"],
                    "message_id": event["message_id"],
                }
            )
        )

    @database_sync_to_async
    def save_message(self, content):
        """
        Save message to database (sync operation wrapped in async)
        """
        receiver = User.objects.get(username=self.other_username)
        return Message.objects.create(
            sender=self.user, receiver=receiver, content=content
        )

    @database_sync_to_async
    def get_message_history(self):
        """
        Retrieve message history between two users
        """
        try:
            other_user = User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return []

        # Get messages between current user and other user (both directions)
        messages = (
            Message.objects.filter(
                models.Q(sender=self.user, receiver=other_user)
                | models.Q(sender=other_user, receiver=self.user)
            )
            .select_related("sender")
            .order_by("timestamp")[:50]
        )  # Last 50 messages

        return [
            {
                "message": msg.content,
                "sender": msg.sender.username,
                "timestamp": msg.timestamp.isoformat(),
                "message_id": msg.id,
            }
            for msg in messages
        ]

    async def send_message_history(self):
        """
        Send previous messages to the newly connected user
        """
        messages = await self.get_message_history()
        await self.send(
            text_data=json.dumps({"type": "message_history", "messages": messages})
        )
