from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from .models import Message, SecurityLog
import os


def get_client_ip(request):
    """
    NEW: Get client IP address from request
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def log_security_event(
    event_type, user=None, message=None, description="", request=None
):
    """
    NEW: Log security event to audit trail
    """
    log_data = {
        "event_type": event_type,
        "user": user,
        "message": message,
        "description": description,
    }

    if request:
        log_data["ip_address"] = get_client_ip(request)
        log_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]

    SecurityLog.objects.create(**log_data)


@login_required
def index(request):
    """Display list of users to start a chat with"""
    users = User.objects.exclude(id=request.user.id)
    return render(request, "chat/index.html", {"users": users})


@login_required
def room(request, username):
    """Chat room for conversation with a specific user"""
    try:
        other_user = User.objects.get(username=username)
    except User.DoesNotExist:
        return redirect("chat:index")

    # NEW: Prevent chatting with yourself
    if other_user == request.user:
        return redirect("chat:index")

    return render(
        request, "chat/room.html", {"other_user": other_user, "username": username}
    )


@login_required
@require_http_methods(["POST"])
def upload_file(request, username):
    """
    Handle file upload via HTTP POST
    ENHANCED: with security validation and logging
    """
    try:
        other_user = User.objects.get(username=username)
    except User.DoesNotExist:
        log_security_event(
            "validation_failed",
            user=request.user,
            description=f"Attempted upload to non-existent user: {username}",
            request=request,
        )
        return JsonResponse({"error": "User not found"}, status=404)

    # NEW: Prevent sending to yourself
    if other_user == request.user:
        log_security_event(
            "validation_failed",
            user=request.user,
            description="Attempted to send file to self",
            request=request,
        )
        return JsonResponse({"error": "Cannot send files to yourself"}, status=400)

    # Check if file is present
    if "file" not in request.FILES:
        return JsonResponse({"error": "No file provided"}, status=400)

    uploaded_file = request.FILES["file"]

    # Validate file size (max 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    if uploaded_file.size > MAX_FILE_SIZE:
        log_security_event(
            "validation_failed",
            user=request.user,
            description=f"File too large: {uploaded_file.size} bytes",
            request=request,
        )
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
        log_security_event(
            "validation_failed",
            user=request.user,
            description=f"Invalid file type: {content_type}",
            request=request,
        )
        return JsonResponse({"error": "File type not allowed"}, status=400)

    # Get optional message text
    message_text = request.POST.get("message", "").strip()

    # NEW: Validate message text length
    if len(message_text) > 5000:
        return JsonResponse(
            {"error": "Message too long (max 5000 characters)"}, status=400
        )

    # Create message with file
    message = Message.objects.create(
        sender=request.user,
        receiver=other_user,
        content=message_text,
        file=uploaded_file,
        file_name=uploaded_file.name,
        file_size=uploaded_file.size,
        file_type=content_type,
        sender_ip=get_client_ip(request),  # NEW: Log IP
    )

    # NEW: Log successful upload
    log_security_event(
        "file_upload",
        user=request.user,
        message=message,
        description=f"Uploaded {uploaded_file.name} ({uploaded_file.size} bytes) to {other_user.username}",
        request=request,
    )

    # Return message data with UUID (string)
    return JsonResponse(
        {
            "success": True,
            "message_id": str(message.id),  # NEW: Convert UUID to string
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
    Serve file for download with access control
    ENHANCED: with security validation and logging
    """
    # NEW: Validate UUID format
    try:
        message = Message.objects.get(id=message_id, deleted=False)
    except (Message.DoesNotExist, ValidationError):
        log_security_event(
            "unauthorized_access",
            user=request.user,
            description=f"Attempted access to invalid message: {message_id}",
            request=request,
        )
        raise Http404("File not found")

    # Check access permission using model method
    if not message.can_be_read_by(request.user):
        log_security_event(
            "unauthorized_access",
            user=request.user,
            message=message,
            description=f"Unauthorized download attempt by {request.user.username}",
            request=request,
        )
        raise Http404("File not found")

    if not message.file:
        raise Http404("No file attached")

    # NEW: Log successful download
    log_security_event(
        "file_download",
        user=request.user,
        message=message,
        description=f"Downloaded {message.file_name}",
        request=request,
    )

    # Serve the file
    try:
        response = FileResponse(message.file.open("rb"))
        response["Content-Type"] = message.file_type or "application/octet-stream"
        response["Content-Disposition"] = f'attachment; filename="{message.file_name}"'

        # NEW: Security headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"

        return response
    except FileNotFoundError:
        log_security_event(
            "validation_failed",
            user=request.user,
            message=message,
            description=f"File not found on disk: {message.file_name}",
            request=request,
        )
        raise Http404("File not found")
