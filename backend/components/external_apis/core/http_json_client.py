"""Bounded HTTPS JSON transport for untrusted external provider payloads."""

from __future__ import annotations

import json
from http.client import HTTPException
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class HttpJsonError(RuntimeError):
    """Categorized transport or payload error suitable for diagnostics."""

    def __init__(self, code: str, message: str, *, payload: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise HttpJsonError("redirect_rejected", f"Rejected redirect to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpJsonClient:
    """Fetch JSON over TLS with host, size, and structural limits."""

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | frozenset[str],
        max_response_bytes: int = 2_000_000,
        max_depth: int = 12,
        max_list_items: int = 10_000,
        max_string_length: int = 20_000,
    ) -> None:
        self.allowed_hosts = frozenset(allowed_hosts)
        self.max_response_bytes = max_response_bytes
        self.max_depth = max_depth
        self.max_list_items = max_list_items
        self.max_string_length = max_string_length
        self._opener = build_opener(_SafeRedirectHandler(self.allowed_hosts))

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> Any:
        """Fetch and parse a bounded JSON response."""

        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise HttpJsonError("host_rejected", f"Unapproved provider URL: {url}")

        query = urlencode(
            [(key, item) for key, value in (params or {}).items() for item in (value if isinstance(value, (list, tuple)) else [value])]
        )
        request_url = f"{url}{'&' if parsed.query else '?'}{query}" if query else url
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "SafetyComponent/ExternalHazardMonitoring",
            **dict(headers or {}),
        }
        request = Request(request_url, headers=request_headers, method="GET")
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                final_url = response.geturl()
                final_host = urlparse(final_url).hostname
                if final_host not in self.allowed_hosts:
                    raise HttpJsonError(
                        "redirect_rejected", f"Rejected final provider host: {final_host}"
                    )
                body = response.read(self.max_response_bytes + 1)
        except HTTPError as exc:
            error_payload = self._bounded_error_payload(exc)
            raise HttpJsonError(
                f"http_{exc.code}",
                f"Provider returned HTTP {exc.code}",
                payload=error_payload,
            ) from exc
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            reason = "timeout" if "timed out" in str(exc).lower() else "network_error"
            raise HttpJsonError(reason, f"Provider request failed: {exc}") from exc

        if len(body) > self.max_response_bytes:
            raise HttpJsonError("oversized_response", "Provider response exceeded byte limit")
        try:
            payload = json.loads(body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpJsonError("malformed_json", "Provider returned malformed JSON") from exc
        self._validate_shape(payload)
        return payload

    def _bounded_error_payload(self, error: HTTPError) -> Any:
        """Parse a bounded JSON error body for provider-specific semantics."""

        try:
            body = error.read(self.max_response_bytes + 1)
        except (OSError, HTTPException):
            return None
        if len(body) > self.max_response_bytes:
            return None
        try:
            payload = json.loads(body.decode("utf-8-sig"))
            self._validate_shape(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, HttpJsonError):
            return None
        return payload

    def _validate_shape(self, value: Any, depth: int = 0) -> None:
        if depth > self.max_depth:
            raise HttpJsonError("payload_too_deep", "Provider JSON exceeded depth limit")
        if isinstance(value, str):
            if len(value) > self.max_string_length:
                raise HttpJsonError("string_too_long", "Provider string exceeded length limit")
            return
        if isinstance(value, list):
            if len(value) > self.max_list_items:
                raise HttpJsonError("list_too_long", "Provider list exceeded item limit")
            for item in value:
                self._validate_shape(item, depth + 1)
            return
        if isinstance(value, dict):
            if len(value) > self.max_list_items:
                raise HttpJsonError("mapping_too_large", "Provider mapping exceeded item limit")
            for key, item in value.items():
                self._validate_shape(key, depth + 1)
                self._validate_shape(item, depth + 1)
