#!/usr/bin/env python3
"""Serve the installation-owned SafetyComponent configuration to its UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from build_app_config import SYSTEM_CONFIG_PATH, compile_config
from configuration_model import validate_user_configuration_v2


DEFAULT_USER_CONFIG_PATH = Path("/config/user_config.yml")
MAX_REQUEST_BYTES = 512 * 1024


class RevisionConflictError(ValueError):
    """Raised when a client attempts to overwrite a newer configuration."""


class UserConfigStore:
    """Read, validate, and atomically replace the installation configuration."""

    def __init__(
        self,
        user_path: Path = DEFAULT_USER_CONFIG_PATH,
        system_path: Path = SYSTEM_CONFIG_PATH,
    ) -> None:
        self.user_path = user_path
        self.system_path = system_path
        self._write_lock = threading.Lock()

    def read(self) -> dict[str, Any]:
        """Return the editable user configuration and its content revision."""

        raw = self.user_path.read_bytes()
        document = yaml.safe_load(raw)
        if not isinstance(document, dict) or not isinstance(
            document.get("user_config"), dict
        ):
            raise ValueError("user_config.yml must contain a user_config mapping")
        validate_user_configuration_v2(document["user_config"])
        return {
            "user_config": document["user_config"],
            "revision": self._revision(raw),
            "restart_required": False,
        }

    def save(
        self, user_config: dict[str, Any], expected_revision: str
    ) -> dict[str, Any]:
        """Validate and atomically save one revision without changing system policy."""

        with self._write_lock:
            current_raw = self.user_path.read_bytes()
            current_mode = self.user_path.stat().st_mode & 0o777
            if expected_revision != self._revision(current_raw):
                raise RevisionConflictError(
                    "Configuration changed since it was opened; reload before saving"
                )

            validated = validate_user_configuration_v2(user_config)
            document = {
                "user_config": validated.model_dump(
                    exclude_none=True, exclude_unset=True
                )
            }
            rendered = yaml.safe_dump(
                document,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ).encode("utf-8")

            self.user_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=self.user_path.parent,
                    prefix=".user_config.",
                    suffix=".yml",
                    delete=False,
                ) as candidate:
                    candidate.write(rendered)
                    candidate.flush()
                    os.fsync(candidate.fileno())
                    candidate_path = Path(candidate.name)
                os.chmod(candidate_path, current_mode)

                # Exercise the same compiler used during App startup before replacing
                # the persisted source. This validates both source layers together.
                compile_config(system_path=self.system_path, user_path=candidate_path)
                os.replace(candidate_path, self.user_path)
                candidate_path = None
            finally:
                if candidate_path is not None:
                    candidate_path.unlink(missing_ok=True)

        return {
            "user_config": document["user_config"],
            "revision": self._revision(rendered),
            "restart_required": True,
        }

    @staticmethod
    def _revision(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()


class UserConfigRequestHandler(BaseHTTPRequestHandler):
    """Expose a same-origin JSON API for the Safety Home configuration page."""

    store: UserConfigStore
    server_version = "SafetyComponentConfig/1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path.rstrip("/") != "/api/config":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            self._send_json(HTTPStatus.OK, self.store.read())
        except (OSError, ValueError) as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "configuration_unavailable", "message": str(exc)},
            )

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path.rstrip("/") != "/api/config":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if not 0 < content_length <= MAX_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "invalid_request_size"},
            )
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be an object")
            user_config = payload.get("user_config")
            revision = payload.get("revision")
            if not isinstance(user_config, dict) or not isinstance(revision, str):
                raise ValueError("user_config and revision are required")
            saved = self.store.save(user_config, revision)
        except RevisionConflictError as exc:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"error": "revision_conflict", "message": str(exc)},
            )
            return
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "invalid_configuration", "message": str(exc)},
            )
            return

        self._send_json(HTTPStatus.OK, saved)

    def log_message(self, format: str, *args: Any) -> None:
        """Write concise access messages to the container log."""

        print(f"config-api: {self.address_string()} - {format % args}", flush=True)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ConfigurationHttpServer(ThreadingHTTPServer):
    """Threaded loopback server that can restart without a socket delay."""

    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--user", type=Path, default=DEFAULT_USER_CONFIG_PATH)
    parser.add_argument("--system", type=Path, default=SYSTEM_CONFIG_PATH)
    args = parser.parse_args()

    UserConfigRequestHandler.store = UserConfigStore(args.user, args.system)
    server = ConfigurationHttpServer(
        (args.host, args.port), UserConfigRequestHandler
    )
    print(f"config-api: listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
