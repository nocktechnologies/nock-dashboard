"""Agent status view must not be cached — stale data causes offline-when-online bug."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_agent_status_has_no_cache_header(client):
    """Cache-Control must include no-store to prevent stale offline readings."""
    user = User.objects.create_user(username="cache_tester", password="pass")
    client.force_login(user)
    response = client.get("/api/remote/agent/status/")
    assert response.status_code == 200
    cc = response.get("Cache-Control", "")
    assert "no-store" in cc, (
        f"Cache-Control must include 'no-store', got: '{cc}'"
    )
