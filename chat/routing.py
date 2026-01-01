from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # WebSocket URL pattern for private chat
    # Matches: ws://domain/ws/chat/<username>/
    re_path(r"ws/chat/(?P<username>\w+)/$", consumers.ChatConsumer.as_asgi()),
]
