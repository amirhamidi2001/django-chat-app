from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.index, name="index"),
    path("chat/<str:username>/", views.room, name="room"),
    # NEW: File upload and download endpoints
    path("chat/<str:username>/upload/", views.upload_file, name="upload_file"),
    path("download/<int:message_id>/", views.download_file, name="download_file"),
]
