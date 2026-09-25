"""RAM pressure requires two valid measurements and sustained qualification."""

from components.core.memory_pressure import MemoryPressureRule


def _rule(now: list[float]) -> MemoryPressureRule:
    return MemoryPressureRule(
        low_available_mib=512,
        recovery_available_mib=768,
        high_psi_percent=10,
        recovery_psi_percent=5,
        qualification_seconds=60,
        recovery_seconds=60,
        clock=lambda: now[0],
    )


def test_memory_fault_requires_both_signals_for_full_duration() -> None:
    now = [0.0]
    rule = _rule(now)
    assert rule.observe(400, 3).status == "normal"
    assert rule.observe(400, 12).status == "qualifying"
    now[0] = 59.0
    assert not rule.observe(400, 12).fault_active
    now[0] = 60.0
    assert rule.observe(400, 12).fault_active

    now[0] = 61.0
    unknown = rule.observe(None, 12)
    assert unknown.status == "unknown"
    assert unknown.fault_active
    assert not unknown.evidence_valid

    now[0] = 100.0
    assert rule.observe(800, 4).status == "recovering"
    now[0] = 160.0
    assert rule.observe(800, 4).status == "normal"


def test_invalid_values_never_assert_memory_fault() -> None:
    now = [0.0]
    rule = _rule(now)
    for available, psi in ((True, 20), (1, float("nan")), (-1, 20), (100, 101)):
        assert rule.observe(available, psi).status == "unknown"
        assert not rule.fault_active
