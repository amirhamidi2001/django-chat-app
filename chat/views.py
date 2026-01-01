from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User


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
