from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.index, name="index"),
    path("chat/<str:username>/", views.room, name="room"),
    path("chat/<str:username>/upload/", views.upload_file, name="upload_file"),
    # NEW: Changed to uuid: path converter for security
    path("download/<uuid:message_id>/", views.download_file, name="download_file"),
]
