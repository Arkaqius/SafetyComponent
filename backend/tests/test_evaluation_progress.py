"""Safety evaluation progress must not be inferred from an app heartbeat."""

from components.core.evaluation_progress import EvaluationProgress


def test_component_progress_is_independent_and_unknown_until_evaluated() -> None:
    now = [0.0]
    progress = EvaluationProgress(
        {"EntityMonitorComponent": 15, "TemperatureComponent": None},
        clock=lambda: now[0],
    )

    progress.record("TemperatureComponent", success=True)
    initial = progress.snapshot()
    assert initial["status"] == "unknown"
    assert initial["components"]["EntityMonitorComponent"]["status"] == "unknown"
    assert initial["components"]["TemperatureComponent"]["status"] == "observed"

    progress.record("EntityMonitorComponent", success=True)
    now[0] = 16.0
    overdue = progress.snapshot()
    assert overdue["status"] == "attention"
    assert overdue["components"]["EntityMonitorComponent"]["status"] == "overdue"
    assert overdue["components"]["EntityMonitorComponent"]["missed_deadline_count"] == 1
    assert progress.snapshot()["components"]["EntityMonitorComponent"]["missed_deadline_count"] == 1
    assert overdue["components"]["TemperatureComponent"]["status"] == "observed"


def test_failed_callback_is_not_a_successful_evaluation() -> None:
    progress = EvaluationProgress({"SmokeMonitor": None}, clock=lambda: 1.0)
    progress.record("SmokeMonitor", success=False)

    component = progress.snapshot()["components"]["SmokeMonitor"]
    assert component["status"] == "error"
    assert component["failure_count"] == 1
    assert component["last_result"] == "error"
