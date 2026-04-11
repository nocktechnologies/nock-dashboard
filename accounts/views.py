from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    """User profile page — displays account details.

    Lightweight placeholder for PR 2. PR 3 extends this view with
    UserProfile fields (company_name, subscription_plan, trial_ends_at,
    etc.) once the UserProfile model and billing integration land.
    """
    return render(request, "accounts/profile.html", {"user": request.user})
