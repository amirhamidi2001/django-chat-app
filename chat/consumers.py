import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import models as django_models
from .models import Message, UserStatus, SecurityLog
import uuid


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Asynchronous WebSocket consumer with enhanced security validation
    """

    MESSAGES_PER_PAGE = 20
    MAX_MESSAGE_LENGTH = 5000  # NEW: Character limit for messages

    async def connect(self):
        """Called when WebSocket connection is established"""
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        self.other_username = self.scope["url_route"]["kwargs"]["username"]

        # NEW: Prevent chatting with yourself
        if self.other_username == self.user.username:
            await self.close()
            return

        other_user_exists = await self.check_user_exists(self.other_username)
        if not other_user_exists:
            await self.close()
            return

        usernames = sorted([self.user.username, self.other_username])
        self.room_name = f"chat_{'_'.join(usernames)}"
        self.room_group_name = f"chat_{self.room_name}"

        await self.accept()

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.set_user_online(self.user)
        await self.broadcast_status_change(self.user.username, True)

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

        read_message_ids = await self.mark_messages_as_read()
        if read_message_ids:
            await self.broadcast_read_receipt(read_message_ids)

        await self.send_initial_messages()

    async def disconnect(self, close_code):
        """Called when WebSocket connection is closed"""
        if hasattr(self, "room_group_name"):
            await self.set_user_offline(self.user)
            await self.broadcast_status_change(self.user.username, False)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "username": self.user.username,
                    "is_typing": False,
                },
            )

            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket
        ENHANCED: with validation and security checks
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            # NEW: Invalid JSON - ignore silently
            return

        message_type = data.get("type", "message")

        # Handle regular chat messages
        if message_type == "message":
            message_content = data.get("message", "")

            # NEW: Validate message content
            if not message_content.strip():
                return

            if len(message_content) > self.MAX_MESSAGE_LENGTH:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": f"Message too long (max {self.MAX_MESSAGE_LENGTH} characters)",
                        }
                    )
                )
                return

            # NEW: Security validation - ensure sender is current user
            # This prevents malicious clients from spoofing sender
            message = await self.save_message(message_content)

            if message:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message",
                        "message": message_content,
                        "sender": self.user.username,
                        "timestamp": message.timestamp.isoformat(),
                        "message_id": str(message.id),  # NEW: UUID as string
                        "is_read": False,
                        "has_file": False,
                    },
                )

        # Handle file message broadcast
        elif message_type == "file_message":
            message_id_str = data.get("message_id")

            # NEW: Validate UUID format
            try:
                message_id = uuid.UUID(message_id_str)
            except (ValueError, AttributeError):
                return

            # NEW: Verify message belongs to current user
            message_data = await self.get_message_data(message_id)

            if message_data:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message",
                        "message": message_data["content"],
                        "sender": self.user.username,
                        "timestamp": message_data["timestamp"],
                        "message_id": str(message_id),
                        "is_read": False,
                        "has_file": True,
                        "file_url": message_data["file_url"],
                        "file_name": message_data["file_name"],
                        "file_size": message_data["file_size"],
                        "file_type": message_data["file_type"],
                        "is_image": message_data["is_image"],
                    },
                )

        # Handle typing indicator
        elif message_type == "typing":
            is_typing = data.get("is_typing", False)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "username": self.user.username,
                    "is_typing": is_typing,
                },
            )

        # Handle load more messages
        elif message_type == "load_more":
            offset = data.get("offset", 0)

            # NEW: Validate offset
            if not isinstance(offset, int) or offset < 0:
                return

            await self.send_paginated_messages(offset)

        # Handle mark as read
        elif message_type == "mark_as_read":
            message_ids = data.get("message_ids", [])

            # NEW: Validate message IDs are UUIDs
            validated_ids = []
            for mid in message_ids:
                try:
                    validated_ids.append(uuid.UUID(str(mid)))
                except (ValueError, AttributeError):
                    continue

            if validated_ids:
                updated_ids = await self.mark_specific_messages_read(validated_ids)
                if updated_ids:
                    await self.broadcast_read_receipt(updated_ids)

    async def chat_message(self, event):
        """Handler for chat messages sent to the group"""
        message_data = {
            "type": "message",
            "message": event["message"],
            "sender": event["sender"],
            "timestamp": event["timestamp"],
            "message_id": event["message_id"],
            "is_read": event.get("is_read", False),
            "has_file": event.get("has_file", False),
        }

        if event.get("has_file"):
            message_data.update(
                {
                    "file_url": event["file_url"],
                    "file_name": event["file_name"],
                    "file_size": event["file_size"],
                    "file_type": event["file_type"],
                    "is_image": event["is_image"],
                }
            )

        await self.send(text_data=json.dumps(message_data))

    async def status_change(self, event):
        """Handler for status change events"""
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
        """Handler for typing indicator events"""
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

    async def read_receipt(self, event):
        """Handler for read receipt events"""
        if event["sender_username"] == self.user.username:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "read_receipt",
                        "message_ids": [
                            str(mid) for mid in event["message_ids"]
                        ],  # NEW: UUIDs as strings
                        "read_by": event["read_by"],
                    }
                )
            )

    async def broadcast_status_change(self, username, is_online):
        """Broadcast user status change to the room group"""
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

    async def broadcast_read_receipt(self, message_ids):
        """Broadcast read receipt to the room group"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "read_receipt",
                "message_ids": message_ids,
                "read_by": self.user.username,
                "sender_username": self.other_username,
            },
        )

    # ========================================================================
    # PAGINATION METHODS
    # ========================================================================

    async def send_initial_messages(self):
        """Send initial batch of messages"""
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
        """Send a batch of older messages"""
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
    # DATABASE OPERATIONS
    # ========================================================================

    @database_sync_to_async
    def check_user_exists(self, username):
        return User.objects.filter(username=username).exists()

    @database_sync_to_async
    def set_user_online(self, user):
        status, created = UserStatus.objects.get_or_create(user=user)
        status.is_online = True
        status.last_seen = timezone.now()
        status.save(update_fields=["is_online", "last_seen"])
        return status

    @database_sync_to_async
    def set_user_offline(self, user):
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
        NEW: Enhanced with validation
        """
        try:
            receiver = User.objects.get(username=self.other_username)

            # Security: Ensure sender is current user (prevent spoofing)
            message = Message.objects.create(
                sender=self.user, receiver=receiver, content=content
            )

            # Log message send
            SecurityLog.objects.create(
                user=self.user,
                event_type="message_send",
                message=message,
                description=f"Sent message to {receiver.username}",
            )

            return message
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_message_data(self, message_id):
        """
        NEW: Enhanced with security validation
        """
        try:
            # Security: Only return message if sender is current user
            message = Message.objects.get(
                id=message_id, sender=self.user, deleted=False
            )
            return {
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "file_url": message.file.url if message.file else None,
                "file_name": message.file_name,
                "file_size": message.file_size,
                "file_type": message.file_type,
                "is_image": message.is_image,
            }
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def get_paginated_messages(self, offset=0):
        """Retrieve paginated message history"""
        try:
            other_user = User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return {
                "messages": [],
                "has_more": False,
                "total_count": 0,
                "offset": offset,
            }

        # NEW: Exclude soft-deleted messages
        total_count = Message.objects.filter(
            django_models.Q(sender=self.user, receiver=other_user)
            | django_models.Q(sender=other_user, receiver=self.user),
            deleted=False,
        ).count()

        has_more = (offset + self.MESSAGES_PER_PAGE) < total_count

        messages = (
            Message.objects.filter(
                django_models.Q(sender=self.user, receiver=other_user)
                | django_models.Q(sender=other_user, receiver=self.user),
                deleted=False,
            )
            .select_related("sender")
            .order_by("-timestamp")[offset : offset + self.MESSAGES_PER_PAGE]
        )

        messages_list = []
        for msg in messages:
            msg_data = {
                "message": msg.content,
                "sender": msg.sender.username,
                "timestamp": msg.timestamp.isoformat(),
                "message_id": str(msg.id),  # NEW: UUID as string
                "is_read": msg.is_read,
                "has_file": bool(msg.file),
            }

            if msg.file:
                msg_data.update(
                    {
                        "file_url": msg.file.url,
                        "file_name": msg.file_name,
                        "file_size": msg.file_size,
                        "file_type": msg.file_type,
                        "is_image": msg.is_image,
                    }
                )

            messages_list.append(msg_data)

        return {
            "messages": messages_list,
            "has_more": has_more,
            "total_count": total_count,
            "offset": offset + len(messages_list),
        }

    @database_sync_to_async
    def mark_messages_as_read(self):
        try:
            other_user = User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return []

        unread_messages = Message.objects.filter(
            sender=other_user, receiver=self.user, is_read=False, deleted=False  # NEW
        )

        message_ids = list(unread_messages.values_list("id", flat=True))
        unread_messages.update(is_read=True)

        return message_ids

    @database_sync_to_async
    def mark_specific_messages_read(self, message_ids):
        """NEW: Enhanced with UUID validation"""
        try:
            other_user = User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return []

        updated = Message.objects.filter(
            id__in=message_ids,
            sender=other_user,
            receiver=self.user,
            is_read=False,
            deleted=False,  # NEW
        )

        updated_ids = list(updated.values_list("id", flat=True))
        updated.update(is_read=True)

        return updated_ids
