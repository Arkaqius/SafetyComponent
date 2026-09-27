"""Bounded, read-only stable-release metadata from publisher GitHub repositories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.client import HTTPException
from threading import Lock, Thread
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

REPOSITORIES = {
    "home_assistant_core": "home-assistant/core",
    "home_assistant_os": "home-assistant/operating-system",
    "home_assistant_supervisor": "home-assistant/supervisor",
    "safety_component": "Arkaqius/SafetyComponent",
}


class StableReleaseProvider:
    """Cache publisher-declared non-draft, non-prerelease metadata for one hour."""

    def __init__(self) -> None:
        self._next_poll = 0.0
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._refreshing = False

    def poll(self) -> dict[str, dict[str, Any]]:
        """Return explicit unknown metadata on failures, never a safety decision."""
        with self._lock:
            start_refresh = not self._refreshing and monotonic() >= self._next_poll
            if start_refresh:
                self._refreshing = True
                self._next_poll = monotonic() + 3600
        if start_refresh:
            Thread(
                target=self._refresh, name="stable-release-metadata", daemon=True
            ).start()
        with self._lock:
            return {
                key: dict(
                    self._cache.get(
                        key,
                        {
                            "status": "unknown",
                            "version": None,
                            "checked_at": None,
                            "reason": "not_observed",
                        },
                    )
                )
                for key in REPOSITORIES
            }

    def _refresh(self) -> None:
        """Fetch off the safety-evaluation thread; no Home Assistant calls here."""
        try:
            results = self._fetch()
            with self._lock:
                self._cache = results
        finally:
            with self._lock:
                self._refreshing = False

    def _fetch(self) -> dict[str, dict[str, Any]]:
        """Bound requests to fixed publisher repositories and response sizes."""
        results: dict[str, dict[str, Any]] = {}
        for product, repository in REPOSITORIES.items():
            url = f"https://api.github.com/repos/{repository}/releases/latest"
            checked = datetime.now(timezone.utc).isoformat()
            item: dict[str, Any] = {
                "status": "unknown",
                "version": None,
                "checked_at": checked,
                "source_url": url,
            }
            try:
                request = Request(
                    url,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "SafetyFunctions",
                    },
                )
                with urlopen(request, timeout=2) as response:
                    raw = response.read(256 * 1024 + 1)
                if len(raw) > 256 * 1024:
                    raise ValueError("Oversized release response")
                release = json.loads(raw)
                if (
                    not isinstance(release, dict)
                    or release.get("draft") is not False
                    or release.get("prerelease") is not False
                ):
                    raise ValueError("No publisher-declared stable release")
                version = release.get("tag_name")
                if (
                    not isinstance(version, str)
                    or not version.strip()
                    or len(version) > 128
                ):
                    raise ValueError("Invalid release version")
                item.update(
                    status="current",
                    version=version,
                    published_at=release.get("published_at"),
                )
            except (OSError, URLError, HTTPException, ValueError, TypeError):
                item["reason"] = "release_metadata_unavailable"
            results[product] = item
        return results
