import json
from typing import Any

from django.http import HttpRequest, JsonResponse


def parse_json_body(request: HttpRequest) -> tuple[dict[str, Any] | None, JsonResponse | None]:
    """Parse JSON request body, returning (data, None) or (None, error_response)."""
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse(
            {"success": False, "message": "Invalid JSON body", "data": None},
            status=400,
        )
