from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from .models import Message
import os


@login_required
def index(request):
    """
    Display list of users to start a chat with
    """
    users = User.objects.exclude(id=request.user.id)
    return render(request, "chat/index.html", {"users": users})


@login_required
def room(request, username):
    """
    Chat room for conversation with a specific user
    """
    try:
        other_user = User.objects.get(username=username)
    except User.DoesNotExist:
        return redirect("chat:index")

    return render(
        request, "chat/room.html", {"other_user": other_user, "username": username}
    )


@login_required
@require_http_methods(["POST"])
def upload_file(request, username):
    """
    NEW: Handle file upload via HTTP POST
    Returns JSON with file info to be sent via WebSocket
    """
    try:
        other_user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    # Check if file is present
    if "file" not in request.FILES:
        return JsonResponse({"error": "No file provided"}, status=400)

    uploaded_file = request.FILES["file"]

    # Validate file size (max 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    if uploaded_file.size > MAX_FILE_SIZE:
        return JsonResponse({"error": "File too large (max 10MB)"}, status=400)

    # Validate file type
    ALLOWED_TYPES = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "application/zip",
    ]

    content_type = uploaded_file.content_type
    if content_type not in ALLOWED_TYPES:
        return JsonResponse({"error": "File type not allowed"}, status=400)

    # Get optional message text
    message_text = request.POST.get("message", "").strip()

    # Create message with file
    message = Message.objects.create(
        sender=request.user,
        receiver=other_user,
        content=message_text,
        file=uploaded_file,
        file_name=uploaded_file.name,
        file_size=uploaded_file.size,
        file_type=content_type,
    )

    # Return message data
    return JsonResponse(
        {
            "success": True,
            "message_id": message.id,
            "file_url": message.file.url,
            "file_name": message.file_name,
            "file_size": message.file_size,
            "file_type": message.file_type,
            "is_image": message.is_image,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
        }
    )


@login_required
def download_file(request, message_id):
    """
    NEW: Serve file for download with access control
    Only sender or receiver can download
    """
    message = get_object_or_404(Message, id=message_id)

    # Check access permission
    if request.user not in [message.sender, message.receiver]:
        raise Http404("File not found")

    if not message.file:
        raise Http404("No file attached")

    # Serve the file
    try:
        response = FileResponse(message.file.open("rb"))
        response["Content-Type"] = message.file_type or "application/octet-stream"
        response["Content-Disposition"] = f'attachment; filename="{message.file_name}"'
        return response
    except FileNotFoundError:
        raise Http404("File not found")
