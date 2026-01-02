import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import models as django_models
from .models import Message, UserStatus


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Asynchronous WebSocket consumer for handling real-time chat with:
    - Status tracking (Phase 1)
    - Typing indicators (Phase 2)
    - Message pagination (Phase 3)
    """

    # NEW: Pagination settings
    MESSAGES_PER_PAGE = 20  # Number of messages to load per request

    async def connect(self):
        """
        Called when WebSocket connection is established
        IMPORTANT: Accept connection early to prevent handshake errors
        """
        # Get the current user from scope
        self.user = self.scope["user"]

        # Reject connection if user is not authenticated
        if not self.user.is_authenticated:
            await self.close()
            return

        # Get the other user's username from URL route
        self.other_username = self.scope["url_route"]["kwargs"]["username"]

        # Verify other user exists
        other_user_exists = await self.check_user_exists(self.other_username)
        if not other_user_exists:
            await self.close()
            return

        # Create room name (sorted usernames for consistency)
        usernames = sorted([self.user.username, self.other_username])
        self.room_name = f"chat_{'_'.join(usernames)}"
        self.room_group_name = f"chat_{self.room_name}"

        # CRITICAL: Accept the connection BEFORE any other operations
        await self.accept()

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # Update user's online status
        await self.set_user_online(self.user)

        # Broadcast status change to the room
        await self.broadcast_status_change(self.user.username, True)

        # Send initial status of the other user to this connection
        other_user_status = await self.get_user_status(self.other_username)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_status",
                    "username": self.other_username,
                    "is_online": other_user_status["is_online"],
                    "last_seen": other_user_status["last_seen"],
                }
            )
        )

        # NEW: Send initial message history with pagination info
        await self.send_initial_messages()

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed
        """
        if hasattr(self, "room_group_name"):
            # Update user's offline status
            await self.set_user_offline(self.user)

            # Broadcast status change to the room
            await self.broadcast_status_change(self.user.username, False)

            # Clear any typing indicator when user disconnects
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "username": self.user.username,
                    "is_typing": False,
                },
            )

            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket
        Handles: messages, typing indicators, and pagination requests
        """
        data = json.loads(text_data)
        message_type = data.get("type", "message")

        # Handle regular chat messages
        if message_type == "message":
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

        # Handle typing indicator signals
        elif message_type == "typing":
            is_typing = data.get("is_typing", False)

            # Broadcast typing status to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "username": self.user.username,
                    "is_typing": is_typing,
                },
            )

        # NEW: Handle load more messages request
        elif message_type == "load_more":
            offset = data.get("offset", 0)
            await self.send_paginated_messages(offset)

    async def chat_message(self, event):
        """
        Handler for chat messages sent to the group
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "message": event["message"],
                    "sender": event["sender"],
                    "timestamp": event["timestamp"],
                    "message_id": event["message_id"],
                }
            )
        )

    async def status_change(self, event):
        """
        Handler for status change events sent to the group
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_status",
                    "username": event["username"],
                    "is_online": event["is_online"],
                    "last_seen": event.get("last_seen"),
                }
            )
        )

    async def typing_indicator(self, event):
        """
        Handler for typing indicator events sent to the group
        Only forward to OTHER users (not the sender)
        """
        # Don't send typing indicator back to the person who's typing
        if event["username"] != self.user.username:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "typing_indicator",
                        "username": event["username"],
                        "is_typing": event["is_typing"],
                    }
                )
            )

    async def broadcast_status_change(self, username, is_online):
        """
        Broadcast user status change to the room group
        """
        last_seen = None
        if not is_online:
            user_status = await self.get_user_status(username)
            last_seen = user_status.get("last_seen")

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "status_change",
                "username": username,
                "is_online": is_online,
                "last_seen": last_seen,
            },
        )

    # ========================================================================
    # NEW: PAGINATION METHODS
    # ========================================================================

    async def send_initial_messages(self):
        """
        Send initial batch of messages with pagination metadata
        """
        messages_data = await self.get_paginated_messages(offset=0)

        await self.send(
            text_data=json.dumps(
                {
                    "type": "message_history",
                    "messages": messages_data["messages"],
                    "has_more": messages_data["has_more"],
                    "total_count": messages_data["total_count"],
                    "offset": messages_data["offset"],
                }
            )
        )

    async def send_paginated_messages(self, offset):
        """
        Send a batch of older messages for infinite scroll
        """
        messages_data = await self.get_paginated_messages(offset)

        await self.send(
            text_data=json.dumps(
                {
                    "type": "load_more_response",
                    "messages": messages_data["messages"],
                    "has_more": messages_data["has_more"],
                    "offset": messages_data["offset"],
                }
            )
        )

    # ========================================================================
    # DATABASE OPERATIONS (All wrapped in @database_sync_to_async)
    # ========================================================================

    @database_sync_to_async
    def check_user_exists(self, username):
        """
        Check if a user exists in the database
        """
        return User.objects.filter(username=username).exists()

    @database_sync_to_async
    def set_user_online(self, user):
        """
        Set user status to online
        """
        status, created = UserStatus.objects.get_or_create(user=user)
        status.is_online = True
        status.last_seen = timezone.now()
        status.save(update_fields=["is_online", "last_seen"])
        return status

    @database_sync_to_async
    def set_user_offline(self, user):
        """
        Set user status to offline with last_seen timestamp
        """
        try:
            status = UserStatus.objects.get(user=user)
            status.is_online = False
            status.last_seen = timezone.now()
            status.save(update_fields=["is_online", "last_seen"])
            return status
        except UserStatus.DoesNotExist:
            return None

    @database_sync_to_async
    def get_user_status(self, username):
        """
        Get user's online status and last seen time
        """
        try:
            user = User.objects.get(username=username)
            status, created = UserStatus.objects.get_or_create(
                user=user, defaults={"is_online": False, "last_seen": timezone.now()}
            )
            return {
                "is_online": status.is_online,
                "last_seen": status.last_seen.isoformat() if status.last_seen else None,
            }
        except User.DoesNotExist:
            return {"is_online": False, "last_seen": None}

    @database_sync_to_async
    def save_message(self, content):
        """
        Save message to database
        """
        receiver = User.objects.get(username=self.other_username)
        return Message.objects.create(
            sender=self.user, receiver=receiver, content=content
        )

    @database_sync_to_async
    def get_paginated_messages(self, offset=0):
        """
        NEW: Retrieve paginated message history between two users
        Returns messages in DESCENDING order (newest first) for pagination,
        but client will reverse them for display
        """
        try:
            other_user = User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return {
                "messages": [],
                "has_more": False,
                "total_count": 0,
                "offset": offset,
            }

        # Get total count of messages in this conversation
        total_count = Message.objects.filter(
            django_models.Q(sender=self.user, receiver=other_user)
            | django_models.Q(sender=other_user, receiver=self.user)
        ).count()

        # Calculate if there are more messages beyond this batch
        has_more = (offset + self.MESSAGES_PER_PAGE) < total_count

        # Fetch messages in DESCENDING order (newest first)
        # This allows efficient pagination with LIMIT/OFFSET
        messages = (
            Message.objects.filter(
                django_models.Q(sender=self.user, receiver=other_user)
                | django_models.Q(sender=other_user, receiver=self.user)
            )
            .select_related("sender")
            .order_by("-timestamp")[offset : offset + self.MESSAGES_PER_PAGE]
        )

        # Convert to list and return metadata
        messages_list = [
            {
                "message": msg.content,
                "sender": msg.sender.username,
                "timestamp": msg.timestamp.isoformat(),
                "message_id": msg.id,
            }
            for msg in messages
        ]

        return {
            "messages": messages_list,
            "has_more": has_more,
            "total_count": total_count,
            "offset": offset + len(messages_list),
        }

    @database_sync_to_async
    def get_message_history(self):
        """
        DEPRECATED: Kept for backward compatibility
        Use get_paginated_messages instead
        """
        try:
            other_user = User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return []

        # Get last 50 messages for backward compatibility
        messages = (
            Message.objects.filter(
                django_models.Q(sender=self.user, receiver=other_user)
                | django_models.Q(sender=other_user, receiver=self.user)
            )
            .select_related("sender")
            .order_by("timestamp")[:50]
        )

        return [
            {
                "message": msg.content,
                "sender": msg.sender.username,
                "timestamp": msg.timestamp.isoformat(),
                "message_id": msg.id,
            }
            for msg in messages
        ]
