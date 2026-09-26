"""Bounded read-only gateway between SafetyFunctions and SafetyHome."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any


HISTORY_REQUEST_EVENT = "safetyhome_notification_history_request"
HISTORY_RESPONSE_EVENT = "safetyhome_notification_history_response"
HISTORY_PAGE_VERSION = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 25
MAX_RESPONSE_BYTES = 12 * 1024
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

HistoryProvider = Callable[[], Sequence[Mapping[str, Any]]]


class SafetyHomeApiGateway:
    """Expose bounded application data without publishing it as HA entity state."""

    def __init__(self, hass_app: Any, history_provider: HistoryProvider) -> None:
        self.hass_app = hass_app
        self._history_provider = history_provider
        self._listener_handle: Any | None = None

    def start(self) -> None:
        """Register the read-only notification-history request handler."""

        if self._listener_handle is not None:
            return
        self._listener_handle = self.hass_app.listen_event(
            self.handle_notification_history_request,
            HISTORY_REQUEST_EVENT,
        )

    def stop(self) -> None:
        """Release the event listener during a controlled shutdown."""

        if self._listener_handle is None:
            return
        cancel = getattr(self.hass_app, "cancel_listen_event", None)
        if callable(cancel):
            cancel(self._listener_handle)
        self._listener_handle = None

    def handle_notification_history_request(
        self,
        event_name: str,
        data: Mapping[str, Any],
        callback_kwargs: Mapping[str, Any] | None = None,
        **_: Any,
    ) -> None:
        """Return one bounded newest-first history page on the HA event bus."""

        del event_name, callback_kwargs
        request_id = data.get("request_id") if isinstance(data, Mapping) else None
        if not isinstance(request_id, str) or not _REQUEST_ID_PATTERN.fullmatch(
            request_id
        ):
            return

        try:
            response = self._history_page(request_id, data)
        except Exception as exc:
            self.hass_app.log(
                f"Unable to serve SafetyHome notification history: {exc}",
                level="ERROR",
            )
            response = self._error_response(request_id, "internal_error")
        self.hass_app.fire_event(HISTORY_RESPONSE_EVENT, **response)

    def _history_page(
        self, request_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        limit = data.get("limit", DEFAULT_PAGE_SIZE)
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:  # noqa: E721 - reject bool and int subclasses
            return self._error_response(request_id, "invalid_limit")

        cursor = data.get("cursor")
        if cursor is not None and (
            not isinstance(cursor, str) or not _REQUEST_ID_PATTERN.fullmatch(cursor)
        ):
            return self._error_response(request_id, "invalid_cursor")

        requested_revision = data.get("revision")
        if requested_revision is not None and (
            not isinstance(requested_revision, str)
            or not _REQUEST_ID_PATTERN.fullmatch(requested_revision)
        ):
            return self._error_response(request_id, "invalid_revision")

        entries = [dict(entry) for entry in reversed(self._history_provider())]
        revision = str(entries[0].get("id", "empty")) if entries else "empty"
        if requested_revision is not None and requested_revision != revision:
            return self._error_response(request_id, "stale_revision", revision)

        start = 0
        if cursor is not None:
            cursor_index = next(
                (
                    index
                    for index, entry in enumerate(entries)
                    if entry.get("id") == cursor
                ),
                None,
            )
            if cursor_index is None:
                return self._error_response(request_id, "stale_cursor", revision)
            start = cursor_index + 1

        page: list[dict[str, Any]] = []
        for entry in entries[start : start + limit]:
            candidate = [*page, entry]
            if self._response_size(
                request_id=request_id,
                revision=revision,
                total=len(entries),
                entries=candidate,
                next_cursor=str(entry.get("id", "")),
            ) > MAX_RESPONSE_BYTES:
                break
            page = candidate

        if start < len(entries) and not page:
            return self._error_response(request_id, "entry_too_large", revision)

        consumed = start + len(page)
        next_cursor = (
            str(page[-1]["id"])
            if page and consumed < len(entries)
            else None
        )
        return {
            "version": HISTORY_PAGE_VERSION,
            "status": "ok",
            "request_id": request_id,
            "revision": revision,
            "total": len(entries),
            "entries": page,
            "next_cursor": next_cursor,
        }

    @staticmethod
    def _error_response(
        request_id: str, error: str, revision: str | None = None
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "version": HISTORY_PAGE_VERSION,
            "status": "error",
            "request_id": request_id,
            "error": error,
        }
        if revision is not None:
            response["revision"] = revision
        return response

    @staticmethod
    def _response_size(
        *,
        request_id: str,
        revision: str,
        total: int,
        entries: list[dict[str, Any]],
        next_cursor: str | None,
    ) -> int:
        payload = {
            "version": HISTORY_PAGE_VERSION,
            "status": "ok",
            "request_id": request_id,
            "revision": revision,
            "total": total,
            "entries": entries,
            "next_cursor": next_cursor,
        }
        return len(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
