from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import NotificationChannel, NotificationLog, NotificationRule


@require_GET
@login_required
def notification_list(request: HttpRequest) -> HttpResponse:
    """Notification log with channels and rules overview."""
    logs = NotificationLog.objects.select_related("channel", "rule").order_by("-sent_at")[:100]
    channels = NotificationChannel.objects.order_by("name")
    rules = NotificationRule.objects.select_related("channel").order_by("trigger_event")

    return render(request, "notifications/list.html", {
        "logs": logs,
        "channels": channels,
        "rules": rules,
    })
