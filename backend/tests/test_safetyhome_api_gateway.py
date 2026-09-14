"""Contracts for the bounded read-only SafetyHome API gateway."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import Mock

from components.safetyhome_api.gateway import (
    HISTORY_REQUEST_EVENT,
    HISTORY_RESPONSE_EVENT,
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    SafetyHomeApiGateway,
)


def _entry(entry_id: str, text: str = "message") -> dict[str, Any]:
    return {
        "id": entry_id,
        "tag": f"tag-{entry_id}",
        "kind": "new",
        "fault_state": "SET",
        "level": 2,
        "title": text,
        "message": text,
        "text_truncated": False,
        "created_at": "2026-09-14T08:00:00+00:00",
        "attempted_at": "2026-09-14T08:00:01+00:00",
        "attempt": 1,
        "service": "notify/all_phones",
        "result": "accepted_by_home_assistant",
        "deadline_missed": False,
    }


def test_start_and_stop_manage_one_read_only_event_listener() -> None:
    app = Mock()
    app.listen_event.return_value = "listener"
    gateway = SafetyHomeApiGateway(app, lambda: ())

    gateway.start()
    gateway.start()
    gateway.stop()

    app.listen_event.assert_called_once_with(
        gateway.handle_notification_history_request,
        HISTORY_REQUEST_EVENT,
    )
    app.cancel_listen_event.assert_called_once_with("listener")


def test_history_pages_are_newest_first_and_revision_stable() -> None:
    gateway = SafetyHomeApiGateway(Mock(), lambda: [_entry(str(i)) for i in range(30)])

    first = gateway._history_page("request-1", {"limit": MAX_PAGE_SIZE})
    assert first["status"] == "ok"
    assert first["revision"] == "29"
    assert first["total"] == 30
    assert [entry["id"] for entry in first["entries"]] == [
        str(i) for i in range(29, 4, -1)
    ]

    second = gateway._history_page(
        "request-2",
        {
            "limit": MAX_PAGE_SIZE,
            "cursor": first["next_cursor"],
            "revision": first["revision"],
        },
    )
    assert [entry["id"] for entry in second["entries"]] == [
        str(i) for i in range(4, -1, -1)
    ]
    assert second["next_cursor"] is None


def test_response_is_bounded_even_for_maximum_length_history_text() -> None:
    gateway = SafetyHomeApiGateway(
        Mock(), lambda: [_entry(str(i), "x" * 2048) for i in range(20)]
    )

    response = gateway._history_page("request", {"limit": 20})

    assert response["status"] == "ok"
    assert 0 < len(response["entries"]) < 20
    assert len(
        json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ) <= MAX_RESPONSE_BYTES
    assert response["next_cursor"] is not None


def test_invalid_or_stale_pagination_inputs_return_explicit_errors() -> None:
    entries = [_entry("one"), _entry("two")]
    gateway = SafetyHomeApiGateway(Mock(), lambda: entries)

    assert gateway._history_page("request", {"limit": 0})["error"] == "invalid_limit"
    assert gateway._history_page("request", {"cursor": "bad cursor"})["error"] == "invalid_cursor"
    assert gateway._history_page("request", {"revision": "old"})["error"] == "stale_revision"
    assert gateway._history_page("request", {"cursor": "missing"})["error"] == "stale_cursor"


def test_handler_emits_only_correlated_history_response() -> None:
    app = Mock()
    gateway = SafetyHomeApiGateway(app, lambda: [_entry("one")])

    gateway.handle_notification_history_request(
        HISTORY_REQUEST_EVENT,
        {"request_id": "request:1", "limit": 20},
        {},
    )

    app.fire_event.assert_called_once()
    event_name = app.fire_event.call_args.args[0]
    payload = app.fire_event.call_args.kwargs
    assert event_name == HISTORY_RESPONSE_EVENT
    assert payload["request_id"] == "request:1"
    assert payload["status"] == "ok"
    assert "config" not in json.dumps(payload).lower()


def test_invalid_request_id_is_ignored_without_broadcasting_data() -> None:
    app = Mock()
    gateway = SafetyHomeApiGateway(app, lambda: [_entry("one")])

    gateway.handle_notification_history_request(
        HISTORY_REQUEST_EVENT,
        {"request_id": "invalid request id"},
        {},
    )

    app.fire_event.assert_not_called()
