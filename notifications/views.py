from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import NotificationChannel, NotificationLog, NotificationRule


@require_GET
@login_required
def notification_list(request: HttpRequest) -> HttpResponse:
    """Notification log with channels and rules overview."""
    logs = NotificationLog.tenant_objects.for_request(request).select_related("channel", "rule").order_by("-sent_at")[:100]
    channels = NotificationChannel.tenant_objects.for_request(request).order_by("name")
    rules = NotificationRule.tenant_objects.for_request(request).select_related("channel").order_by("trigger_event")

    return render(request, "notifications/list.html", {
        "logs": logs,
        "channels": channels,
        "rules": rules,
    })
