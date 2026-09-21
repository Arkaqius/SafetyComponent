#!/usr/bin/env python3
"""Build the AppDaemon runtime configuration from Home Assistant Core data."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


CORE_CONFIG_URL = "http://supervisor/core/api/config"
REQUIRED_FIELDS = ("latitude", "longitude", "elevation", "time_zone")
PLACEHOLDERS = {
    "latitude": "__HOME_ASSISTANT_LATITUDE__",
    "longitude": "__HOME_ASSISTANT_LONGITUDE__",
    "elevation": "__HOME_ASSISTANT_ELEVATION__",
    "time_zone": "__HOME_ASSISTANT_TIME_ZONE__",
}


def fetch_core_config(
    url: str,
    token: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Read Home Assistant Core configuration through the Supervisor proxy."""

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Home Assistant Core configuration must be a JSON object")
    return payload


def _validated_number(config: Mapping[str, object], field: str) -> int | float:
    """Return one required finite numeric Home Assistant setting."""

    value = config.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"Home Assistant Core configuration field {field!r} must be numeric"
        )
    if not math.isfinite(value):
        raise ValueError(
            f"Home Assistant Core configuration field {field!r} must be finite"
        )
    return value


def render_appdaemon_config(
    template: str,
    core_config: Mapping[str, object],
) -> str:
    """Render AppDaemon's required location fields into its YAML template."""

    replacements = {
        PLACEHOLDERS["latitude"]: json.dumps(
            _validated_number(core_config, "latitude")
        ),
        PLACEHOLDERS["longitude"]: json.dumps(
            _validated_number(core_config, "longitude")
        ),
        PLACEHOLDERS["elevation"]: json.dumps(
            _validated_number(core_config, "elevation")
        ),
    }
    time_zone = core_config.get("time_zone")
    if not isinstance(time_zone, str) or not time_zone.strip():
        raise ValueError(
            "Home Assistant Core configuration field 'time_zone' must be a "
            "non-empty string"
        )
    replacements[PLACEHOLDERS["time_zone"]] = json.dumps(time_zone)

    rendered = template
    for placeholder, value in replacements.items():
        if placeholder not in rendered:
            raise ValueError(
                f"AppDaemon configuration template is missing {placeholder}"
            )
        rendered = rendered.replace(placeholder, value)

    unresolved = [
        placeholder for placeholder in PLACEHOLDERS.values() if placeholder in rendered
    ]
    if unresolved:
        raise ValueError(
            "AppDaemon configuration has unresolved placeholders: "
            + ", ".join(unresolved)
        )
    return rendered


def write_appdaemon_config(
    template_path: Path,
    output_path: Path,
    core_config: Mapping[str, object],
) -> None:
    """Atomically write a rendered AppDaemon runtime configuration."""

    rendered = render_appdaemon_config(
        template_path.read_text(encoding="utf-8"),
        core_config,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_file.write(rendered)
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(output_path)


def fetch_core_config_with_retry(
    url: str,
    token: str,
    attempts: int,
    retry_delay: float,
) -> dict[str, Any]:
    """Wait for Home Assistant Core and return its complete configuration."""

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            core_config = fetch_core_config(url, token)
            missing = [
                field for field in REQUIRED_FIELDS if field not in core_config
            ]
            if missing:
                raise ValueError(
                    "Home Assistant Core configuration is missing required fields: "
                    + ", ".join(missing)
                )
            return core_config
        except (OSError, ValueError) as error:
            last_error = error
            if attempt < attempts:
                if attempt == 1:
                    print(
                        "Waiting for Home Assistant Core configuration...",
                        flush=True,
                    )
                time.sleep(retry_delay)

    raise RuntimeError(
        f"Unable to read Home Assistant Core configuration after {attempts} attempts"
    ) from last_error


def main() -> None:
    """Fetch Home Assistant settings and generate AppDaemon's configuration."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=CORE_CONFIG_URL)
    parser.add_argument("--attempts", type=int, default=60)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    args = parser.parse_args()

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise SystemExit("SUPERVISOR_TOKEN is required")
    if args.attempts < 1:
        raise SystemExit("--attempts must be at least 1")
    if args.retry_delay < 0:
        raise SystemExit("--retry-delay cannot be negative")
    core_config = fetch_core_config_with_retry(
        args.url,
        token,
        attempts=args.attempts,
        retry_delay=args.retry_delay,
    )
    write_appdaemon_config(
        args.template,
        args.output,
        core_config,
    )


if __name__ == "__main__":
    main()
