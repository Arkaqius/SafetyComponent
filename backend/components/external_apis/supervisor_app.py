"""Read this App's identity without exposing Supervisor credentials or options."""

from __future__ import annotations

import json
import os
import re
from http.client import HTTPException
from urllib.request import Request, urlopen

SELF_INFO_URL = "http://supervisor/addons/self/info"
MAX_INFO_BYTES = 64 * 1024


def own_app_slug() -> str:
    """Return only the authenticated self slug; never accept a client target."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("Restart is available only in a Home Assistant App")
    try:
        request = Request(SELF_INFO_URL, headers={"Authorization": f"Bearer {token}"})
        with urlopen(request, timeout=5) as response:
            raw = response.read(MAX_INFO_BYTES + 1)
        if len(raw) > MAX_INFO_BYTES:
            raise ValueError("Oversized app identity response")
        payload = json.loads(raw)
        data = payload.get("data") if isinstance(payload, dict) else None
        slug = data.get("slug") if isinstance(data, dict) else None
        if (
            payload.get("result") != "ok"
            or not isinstance(slug, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", slug)
        ):
            raise ValueError("Invalid app identity response")
        return slug
    except (OSError, ValueError, AttributeError, HTTPException):
        raise RuntimeError("Supervisor app identity is unavailable") from None
