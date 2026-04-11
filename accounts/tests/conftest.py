"""Shared fixtures for the accounts test suite."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

from allauth.account.models import EmailAddress


@pytest.fixture
def verified_user(db):
    """Create a user with a verified email address.

    With ACCOUNT_EMAIL_VERIFICATION = 'mandatory', allauth blocks login
    for users who haven't verified. This fixture creates a user AND marks
    their email as verified so integration tests that need a logged-in
    user can skip the verification dance.
    """
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="TestPass123!",
    )
    EmailAddress.objects.create(
        user=user,
        email=user.email,
        primary=True,
        verified=True,
    )
    return user
