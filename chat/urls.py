from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.index, name="index"),
    path("chat/<str:username>/", views.room, name="room"),
]
