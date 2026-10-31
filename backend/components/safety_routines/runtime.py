"""Bounded routine sessions and correlated Home Assistant event interface."""

from __future__ import annotations

import copy
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from components.core.localization import Localizer

from .evaluation import evaluate_check, summarize
from .schema import SafetyRoutinesConfig

REQUEST_EVENT = "safety_routine_request"
RESPONSE_EVENT = "safety_routine_response"
COMPLETED_EVENT = "safety_routine_completed"
MAX_HISTORY = 20
MAX_RESPONSE_BYTES = 256 * 1024
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SafetyRoutineRuntime:
    """Own advisory check sessions without interacting with fault or recovery APIs."""

    def __init__(
        self,
        app: Any,
        config: Mapping[str, Any],
        store: Any,
        localization: Mapping[str, Any] | None = None,
        *,
        now: Callable[[], datetime] | None = None,
        diagnostics_observer: Callable[..., None] | None = None,
    ) -> None:
        self.app = app
        self.config = SafetyRoutinesConfig.model_validate(dict(config))
        self.store = store
        self.localizer = Localizer(localization)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.history: list[dict[str, Any]] = []
        self.active: dict[str, dict[str, Any]] = {}
        self.handles: list[tuple[str, Any]] = []
        self.timers: dict[str, Any] = {}
        self.storage_available = True
        self.history_loaded = False
        self.diagnostics_observer = diagnostics_observer
        self.last_samples: dict[str, datetime] = {}
        self.observations: dict[str, dict[str, str | None]] = {}
        self.started = False
        self.lock = threading.RLock()

    def start(self) -> None:
        """Restore historical reports and register triggers without replaying them."""
        with self.lock:
            if self.started:
                return
            self.started = True
            try:
                snapshot = self.store.load()
                if snapshot and snapshot.get("version") != 1:
                    raise ValueError("unsupported routine history version")
                reports = snapshot.get("runs", [])
                if not isinstance(reports, list) or len(reports) > MAX_HISTORY:
                    raise ValueError("invalid routine history")
                for report in reports:
                    if not self._valid_report(report):
                        raise ValueError("invalid routine report")
                self.history = copy.deepcopy(reports)
                self.history_loaded = True
                self._storage_diagnostic(False, "read")
                for report in self.history:
                    if report["state"] in ("waiting", "running"):
                        report.update(
                            state="interrupted",
                            status="unknown",
                            finished_at=self.now().isoformat(),
                        )
                self._persist()
            except Exception as exc:
                self.history = []
                self.storage_available = False
                self._storage_diagnostic(True, "read")
                self.app.log(f"Unable to restore routine history: {exc}", level="ERROR")
            self.handles.append(
                ("event", self.app.listen_event(self.handle_request, REQUEST_EVENT))
            )
            for routine_id, routine in self.config.routines.items():
                if not routine.enabled:
                    continue
                for trigger in routine.triggers:
                    if trigger.kind == "event":
                        handle = self.app.listen_event(
                            self._event_trigger, trigger.event, routine_id=routine_id
                        )
                        self.handles.append(("event", handle))
                    else:
                        handle = self.app.listen_state(
                            self._state_trigger,
                            trigger.entity_id,
                            old=trigger.from_state,
                            new=trigger.to_state,
                            routine_id=routine_id,
                        )
                        self.handles.append(("state", handle))

    @staticmethod
    def _valid_report(report: Any) -> bool:
        """Reject damaged stored envelopes instead of surfacing a false success."""
        if not isinstance(report, dict):
            return False
        if not all(
            isinstance(report.get(key), str)
            for key in ("run_id", "routine_id", "name", "started_at")
        ):
            return False
        if report.get("state") not in (
            "waiting",
            "running",
            "completed",
            "interrupted",
            "cancelled",
        ):
            return False
        results = report.get("results")
        if not isinstance(results, list) or len(results) > 24:
            return False
        if not all(
            isinstance(item, dict)
            and item.get("status") in ("pass", "problem", "unknown", "skipped")
            for item in results
        ):
            return False
        if report["state"] == "completed":
            return (
                bool(results) and report.get("status") == summarize(results)["status"]
            )
        return report.get("status") == "unknown"

    def stop(self) -> None:
        """Cancel pending work; keep unfinished runs explicitly interrupted."""
        with self.lock:
            self.started = False
            for routine_id in list(self.active):
                self._finish(routine_id, "interrupted")
            for kind, handle in self.handles:
                try:
                    getattr(self.app, "cancel_listen_" + kind)(handle)
                except Exception as exc:
                    self.app.log(
                        f"Unable to remove routine listener: {exc}", level="WARNING"
                    )
            self.handles.clear()

    def run(
        self, routine_id: str, request_id: str | None = None, source: str = "manual"
    ) -> dict[str, Any]:
        """Start one run or return the existing run for a duplicate request."""
        with self.lock:
            if not self.started:
                return {"error": "not_running"}
            routine = self.config.routines.get(routine_id)
            if routine is None or not routine.enabled:
                return {"error": "routine_unavailable"}
            if request_id:
                previous = next(
                    (r for r in self.history if r.get("request_id") == request_id), None
                )
                if previous:
                    return (
                        {"run": copy.deepcopy(previous)}
                        if previous["routine_id"] == routine_id
                        else {"error": "request_conflict"}
                    )
            if routine_id in self.active:
                return {
                    "error": "already_running",
                    "run_id": self.active[routine_id]["run_id"],
                }
            now = self.now()
            run: dict[str, Any] = {
                "run_id": uuid4().hex,
                "request_id": request_id,
                "routine_id": routine_id,
                "name": routine.name,
                "source": source,
                "state": "waiting",
                "status": "unknown",
                "started_at": now.isoformat(),
                "finished_at": None,
                "results": [],
                "counts": {"pass": 0, "problem": 0, "unknown": 0, "skipped": 0},
                "sample_count": 0,
                "evidence_incomplete": False,
                "observation_seconds": routine.observation_seconds,
                "due_at": (now + timedelta(seconds=routine.delay_seconds)).isoformat(),
            }
            self.active[routine_id] = run
            self.history.append(run)
            # Active runs must remain available for interrupted-run recovery.
            while len(self.history) > MAX_HISTORY:
                remove = next(
                    r for r in self.history if r["state"] not in ("waiting", "running")
                )
                self.history.remove(remove)
            self._persist()
            if routine.delay_seconds:
                self._schedule(routine_id, routine.delay_seconds)
            else:
                self._sample(routine_id)
            return {"run": copy.deepcopy(run)}

    def _schedule(self, routine_id: str, seconds: float) -> None:
        try:
            self.timers[routine_id] = self.app.run_in(
                self._timer,
                seconds,
                routine_id=routine_id,
                run_id=self.active[routine_id]["run_id"],
            )
        except Exception as exc:
            self.app.log(f"Unable to schedule routine: {exc}", level="ERROR")
            self._finish(routine_id, "interrupted")

    def _timer(self, kwargs: Mapping[str, Any] | None = None, **values: Any) -> None:
        data = {**dict(kwargs or {}), **values}
        with self.lock:
            routine_id = data.get("routine_id")
            if not isinstance(routine_id, str):
                return
            run = self.active.get(routine_id)
            if self.started and run and run["run_id"] == data.get("run_id"):
                self.timers.pop(routine_id, None)
                self._sample(routine_id)

    def _sample(self, routine_id: str) -> None:
        run = self.active[routine_id]
        routine = self.config.routines[routine_id]
        now = self.now()
        previous_sample = self.last_samples.get(routine_id)
        if previous_sample and not 0 < (now - previous_sample).total_seconds() <= 10:
            self._finish(routine_id, "interrupted")
            return
        self.last_samples[routine_id] = now
        if run["state"] == "waiting":
            run.update(state="running", observation_started_at=now.isoformat())
            run["due_at"] = (
                now + timedelta(seconds=routine.observation_seconds)
            ).isoformat()
        remaining = (datetime.fromisoformat(run["due_at"]) - now).total_seconds()
        if remaining > routine.observation_seconds or (
            run["sample_count"] and remaining < -10
        ):
            self._finish(routine_id, "interrupted")
            return
        ids: set[str] = set()
        for check in routine.checks.values():
            for binding in (check, check.condition):
                if binding:
                    ids.add(binding.entity_id)
                    if binding.observed_at_entity_id:
                        ids.add(binding.observed_at_entity_id)
        states: dict[str, Any] = {}
        for entity_id in ids:
            try:
                states[entity_id] = copy.deepcopy(
                    self.app.get_state(entity_id, attribute="all")
                )
            except Exception:
                states[entity_id] = None
        results = [
            evaluate_check(key, check, states, now)
            for key, check in routine.checks.items()
        ]
        # Every scheduled observation matters; later passes cannot erase gaps/problems.
        old_results = {item["check_id"]: item for item in run["results"]}
        observations = self.observations.setdefault(routine_id, {})
        for index, result in enumerate(results):
            observed = result["observed_at"]
            previous_observed = observations.get(result["check_id"])
            if (
                observed
                and previous_observed
                and observed <= previous_observed
                and result["status"] == "pass"
            ):
                result.update(status="unknown", reason="observation_not_advanced")
            observations[result["check_id"]] = observed
            if result["status"] == "unknown":
                run["evidence_incomplete"] = True
            old = old_results.get(result["check_id"])
            if old:
                if old["status"] == "problem" or (
                    old["status"] == "unknown" and result["status"] != "problem"
                ):
                    results[index] = old
                elif {old["status"], result["status"]} == {"pass", "skipped"}:
                    result.update(status="unknown", reason="condition_changed")
                    run["evidence_incomplete"] = True
        run["results"] = results
        run["sample_count"] += 1
        run["counts"] = summarize(results)["counts"]
        if remaining <= 0:
            self._finish(routine_id, "completed")
        else:
            self._schedule(routine_id, min(5, remaining))

    def _finish(self, routine_id: str, state: str) -> None:
        run = self.active.pop(routine_id)
        self.last_samples.pop(routine_id, None)
        self.observations.pop(routine_id, None)
        timer = self.timers.pop(routine_id, None)
        if timer is not None:
            try:
                self.app.cancel_timer(timer)
            except Exception:
                pass
        run.update(state=state, finished_at=self.now().isoformat())
        run["status"] = (
            summarize(run["results"])["status"] if state == "completed" else "unknown"
        )
        self._persist()
        if state == "completed":
            try:
                self.app.fire_event(
                    COMPLETED_EVENT,
                    **self._summary(run),
                    storage_available=self.storage_available,
                )
            except Exception as exc:
                self.app.log(
                    f"Unable to announce routine completion: {exc}", level="ERROR"
                )

    def _persist(self) -> None:
        if not self.history_loaded:
            self.storage_available = False
            return
        try:
            self.store.save({"version": 1, "runs": self.history})
            self.storage_available = True
            self._storage_diagnostic(False, "write")
        except Exception as exc:
            self.storage_available = False
            self._storage_diagnostic(True, "write")
            self.app.log(f"Unable to persist routine history: {exc}", level="ERROR")

    def _storage_diagnostic(self, failed: bool, operation: str) -> None:
        if self.diagnostics_observer:
            self.diagnostics_observer(
                "persistence", failed, detail="safety_routines", operation=operation
            )

    @staticmethod
    def _summary(run: dict[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value) for key, value in run.items() if key != "results"
        }

    def _present(self, run: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(run)
        result["status_label"] = self.localizer.text("routine.status." + run["status"])
        for check in result["results"]:
            check["status_label"] = self.localizer.text(
                "routine.status." + check["status"]
            )
            check["reason_label"] = self.localizer.text(
                "routine.reason." + check["reason"]
            )
        return result

    def handle_request(
        self, event_name: str, data: Mapping[str, Any], kwargs: Any = None, **_: Any
    ) -> None:
        """Serve bounded lists/reports and explicit commands via authenticated HA events."""
        del event_name, kwargs
        request_id = data.get("request_id") if isinstance(data, Mapping) else None
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            return
        with self.lock:
            if not self.started:
                return
            try:
                response = self._request(data)
            except Exception as exc:
                self.app.log(f"Routine request failed: {exc}", level="ERROR")
                response = {"error": "internal_error"}
            response.update(
                version=1,
                request_id=request_id,
                storage_available=self.storage_available,
            )
            if (
                len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
                > MAX_RESPONSE_BYTES
            ):
                response = {
                    "version": 1,
                    "request_id": request_id,
                    "error": "response_too_large",
                    "storage_available": self.storage_available,
                }
            self.app.fire_event(RESPONSE_EVENT, **response)

    def _request(self, data: Mapping[str, Any]) -> dict[str, Any]:
        action = data.get("action", "list")
        if action == "list":
            return {
                "routines": [
                    {
                        "routine_id": key,
                        "name": cfg.name,
                        "enabled": cfg.enabled,
                        "check_count": len(cfg.checks),
                    }
                    for key, cfg in self.config.routines.items()
                ],
                "runs": [self._summary(run) for run in reversed(self.history)],
            }
        routine_id = data.get("routine_id")
        if not isinstance(routine_id, str):
            return {"error": "routine_unavailable"}
        if action != "report" and routine_id not in self.config.routines:
            return {"error": "routine_unavailable"}
        if action == "run":
            result = self.run(routine_id, str(data["request_id"]))
            return {"run": self._present(result["run"])} if "run" in result else result
        if action == "cancel":
            run = self.active.get(routine_id)
            if not run or run["run_id"] != data.get("run_id"):
                return {"error": "run_unavailable"}
            self._finish(routine_id, "cancelled")
            return {"run": self._present(run)}
        if action == "report":
            run = next(
                (
                    r
                    for r in reversed(self.history)
                    if r["routine_id"] == routine_id
                    and (data.get("run_id") is None or r["run_id"] == data["run_id"])
                ),
                None,
            )
            return {"run": self._present(run)} if run else {"error": "run_unavailable"}
        return {"error": "invalid_action"}

    def _event_trigger(
        self,
        event: str,
        data: Any,
        kwargs: Mapping[str, Any] | None = None,
        **values: Any,
    ) -> None:
        del event, data
        self.run(
            str({**dict(kwargs or {}), **values}.get("routine_id")), source="event"
        )

    def _state_trigger(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: Mapping[str, Any] | None = None,
        **values: Any,
    ) -> None:
        del entity, attribute
        if old is None or old == new:
            return
        self.run(
            str({**dict(kwargs or {}), **values}.get("routine_id")), source="state"
        )
