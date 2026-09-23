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
from typing import Any, Callable

import yaml

from build_app_config import SYSTEM_CONFIG_PATH, compile_config, load_mapping
from build_appdaemon_config import CORE_CONFIG_URL, fetch_core_config
from configuration_model import validate_user_configuration_v2


DEFAULT_USER_CONFIG_PATH = Path("/config/user_config.yml")
EXAMPLE_USER_CONFIG_PATH = (
    Path(__file__).resolve().parent / "config" / "user_config.example.yml"
)
ABSENT_REVISION = "absent"
MAX_REQUEST_BYTES = 512 * 1024


class RevisionConflictError(ValueError):
    """Raised when a client attempts to overwrite a newer configuration."""


class UserConfigStore:
    """Read, validate, and atomically replace the installation configuration."""

    def __init__(
        self,
        user_path: Path = DEFAULT_USER_CONFIG_PATH,
        system_path: Path = SYSTEM_CONFIG_PATH,
        example_path: Path = EXAMPLE_USER_CONFIG_PATH,
        home_assistant_config_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.user_path = user_path
        self.system_path = system_path
        self.example_path = example_path
        self.home_assistant_config_provider = (
            home_assistant_config_provider or self._fetch_home_assistant_config
        )
        self._write_lock = threading.Lock()

    @staticmethod
    def _fetch_home_assistant_config() -> dict[str, Any]:
        """Read current HA coordinates when validating an installation draft."""

        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            raise ValueError("SUPERVISOR_TOKEN is required for Home Assistant location")
        return fetch_core_config(CORE_CONFIG_URL, token)

    def read(self) -> dict[str, Any]:
        """Return the editable user configuration and its content revision."""

        setup_required = not self.user_path.exists()
        raw = (self.example_path if setup_required else self.user_path).read_bytes()
        validation_error: str | None = None
        document: Any = None
        try:
            document = yaml.safe_load(raw)
            if not isinstance(document, dict) or not isinstance(
                document.get("user_config"), dict
            ):
                raise ValueError("user_config.yml must contain a user_config mapping")
            validate_user_configuration_v2(document["user_config"])
            user_config = document["user_config"]
        except (ValueError, yaml.YAMLError) as exc:
            if setup_required:
                raise
            validation_error = str(exc)
            if isinstance(document, dict) and isinstance(
                document.get("user_config"), dict
            ):
                user_config = document["user_config"]
            else:
                example = yaml.safe_load(self.example_path.read_text(encoding="utf-8"))
                user_config = example["user_config"]

        calibration = load_mapping(self.system_path).get("calibration", {})
        temperature = calibration.get("temperature", {})
        safety_door = calibration.get("safety_door", {})
        entity_monitor = calibration.get("entity_monitor", {})
        external_hazard = calibration.get("external_hazard", {})
        system_defaults = {
            "detector_profiles": sorted(
                calibration.get("internal_environmental_hazard", {})
                .get("profiles", {})
                .keys()
            ),
            "temperature": {
                key: temperature[key]
                for key in ("default_low_temperature_c", "default_high_temperature_c")
                if key in temperature
            },
            "safety_door": {
                "default_timeout_seconds": safety_door.get("default_timeout_seconds")
            },
            "entity_monitor": {
                key: entity_monitor[key]
                for key in (
                    "default_startup_grace_seconds",
                    "default_evaluation_interval_seconds",
                )
                if key in entity_monitor
            },
            "external_hazard": {
                "weather": {
                    key: value
                    for key, value in external_hazard.get("weather", {}).items()
                    if key.startswith("default_")
                },
                "outdoor_air_quality": {
                    "default_warning_at": external_hazard.get(
                        "outdoor_air_quality", {}
                    ).get("default_warning_at")
                },
            },
        }

        return {
            "user_config": user_config,
            "system_defaults": system_defaults,
            "revision": ABSENT_REVISION if setup_required else self._revision(raw),
            "restart_required": False,
            "setup_required": setup_required,
            "validation_error": validation_error,
        }

    def import_yaml(self, source: str) -> dict[str, Any]:
        """Validate an uploaded v2 YAML document without persisting it."""

        document = yaml.safe_load(source)
        if not isinstance(document, dict) or set(document) != {"user_config"}:
            raise ValueError("YAML must contain only a user_config mapping")
        user_config = document["user_config"]
        if not isinstance(user_config, dict):
            raise ValueError("user_config must be a mapping")
        validate_user_configuration_v2(user_config)
        self._validate_with_compiler(document)
        return {"user_config": user_config}

    def save(
        self, user_config: dict[str, Any], expected_revision: str
    ) -> dict[str, Any]:
        """Validate and atomically save one revision without changing system policy."""

        with self._write_lock:
            exists = self.user_path.exists()
            current_raw = self.user_path.read_bytes() if exists else None
            current_mode = self.user_path.stat().st_mode & 0o777 if exists else 0o600
            current_revision = (
                self._revision(current_raw)
                if current_raw is not None
                else ABSENT_REVISION
            )
            if expected_revision != current_revision:
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
                compile_config(
                    system_path=self.system_path,
                    user_path=candidate_path,
                    home_assistant_config=self.home_assistant_config_provider(),
                )
                latest_raw = (
                    self.user_path.read_bytes() if self.user_path.exists() else None
                )
                if latest_raw != current_raw:
                    raise RevisionConflictError(
                        "Configuration changed during validation; reload before saving"
                    )
                os.replace(candidate_path, self.user_path)
                candidate_path = None
            finally:
                if candidate_path is not None:
                    candidate_path.unlink(missing_ok=True)

        return {
            "user_config": document["user_config"],
            "revision": self._revision(rendered),
            "restart_required": True,
            "setup_required": False,
        }

    def _validate_with_compiler(self, document: dict[str, Any]) -> None:
        """Compile a temporary candidate without touching the installation file."""

        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "user_config.yml"
            candidate_path.write_text(
                yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            compile_config(
                system_path=self.system_path,
                user_path=candidate_path,
                home_assistant_config=self.home_assistant_config_provider(),
            )

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
        except (OSError, ValueError, yaml.YAMLError) as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "configuration_unavailable", "message": str(exc)},
            )

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path.rstrip("/") != "/api/config":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            payload = self._read_payload()
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
        except (json.JSONDecodeError, OSError, ValueError, yaml.YAMLError) as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "invalid_configuration", "message": str(exc)},
            )
            return

        self._send_json(HTTPStatus.OK, saved)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path.rstrip("/") != "/api/config/import":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            payload = self._read_payload()
            source = payload.get("yaml")
            if not isinstance(source, str):
                raise ValueError("yaml must be a string")
            imported = self.store.import_yaml(source)
        except (json.JSONDecodeError, OSError, ValueError, yaml.YAMLError) as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "invalid_configuration", "message": str(exc)},
            )
            return
        self._send_json(HTTPStatus.OK, imported)

    def _read_payload(self) -> dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if not 0 < content_length <= MAX_REQUEST_BYTES:
            raise ValueError("Request body must be between 1 and 524288 bytes")
        payload = json.loads(self.rfile.read(content_length))
        if not isinstance(payload, dict):
            raise ValueError("Request body must be an object")
        return payload

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
    server = ConfigurationHttpServer((args.host, args.port), UserConfigRequestHandler)
    print(f"config-api: listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
