"""Persist and retire MQTT fault identities owned by battery monitoring."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


_FAULT_NAME = re.compile(r"RemoteBatteryLow[A-Za-z0-9]+\Z")
_MAX_FAULTS = 1024


class BatteryFaultCatalog:
    """Remember published battery faults and retry retained-topic retirement."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> tuple[set[str], set[str]]:
        """Read validated active and retired identities; never guess on corruption."""

        if not self.path.exists():
            return set(), set()
        with self.path.open("r", encoding="utf-8") as stream:
            payload: Any = json.load(stream)
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Invalid battery fault catalog version")
        active = self._names(payload.get("active"))
        retired = self._names(payload.get("retired"))
        if active & retired:
            raise ValueError("Battery fault catalog has conflicting identities")
        return active, retired

    def save(self, active: set[str], retired: set[str]) -> None:
        """Atomically persist the next catalog after MQTT tombstones succeed."""

        active = self._names(sorted(active))
        retired = self._names(sorted(retired))
        if active & retired:
            raise ValueError("Battery fault catalog has conflicting identities")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    {"version": 1, "active": sorted(active), "retired": sorted(retired)},
                    stream,
                    sort_keys=True,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @staticmethod
    def _names(value: Any) -> set[str]:
        if (
            not isinstance(value, list)
            or len(value) > _MAX_FAULTS
            or any(
                not isinstance(name, str) or not _FAULT_NAME.fullmatch(name)
                for name in value
            )
            or len(set(value)) != len(value)
        ):
            raise ValueError("Invalid battery fault catalog identities")
        return set(value)


def reconcile_battery_faults(
    catalog: BatteryFaultCatalog,
    mqtt_entities: Any,
    *,
    current: set[str],
    explicitly_inactive: set[str],
    inventory_complete: bool,
) -> None:
    """Retire only owned identities; retain history on discovery failure."""

    previous, previously_retired = catalog.load()
    if current & explicitly_inactive:
        raise ValueError("An active battery fault cannot be explicitly inactive")
    active = set(current) if inventory_complete else (previous | current)
    active -= explicitly_inactive
    retired = (previously_retired | explicitly_inactive) - active
    if inventory_complete:
        retired |= previous - active
    for name in sorted(retired):
        mqtt_entities.remove_sensor(
            f"sensor.fault_{name}", remove_legacy_topic=True
        )
    catalog.save(active, retired)
