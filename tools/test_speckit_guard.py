"""Test that approval binds the verification plan to the reviewed revision."""

from pathlib import Path
from runpy import run_path

import pytest


def test_plan_review_requires_and_pins_verification_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard_path = Path(__file__).resolve().parents[1] / ".specify/workflows/speckit/guard.py"
    guard = run_path(str(guard_path))
    feature = tmp_path / "docs/features/001-example"
    feature.mkdir(parents=True)
    for name in ("spec.md", "requirements.sdoc", "plan.md", "architecture.sdoc"):
        (feature / name).write_text("fixture", encoding="utf-8")

    monkeypatch.setenv("SAFETYCOMPONENT_WORKFLOW_FEATURE", "docs/features/001-example")
    monkeypatch.setenv("SAFETYCOMPONENT_SPEC_REVISION", guard["revision"](feature))
    context = guard["main"].__globals__
    monkeypatch.setitem(context, "REPO", tmp_path)
    commands: list[tuple[str, ...]] = []
    monkeypatch.setitem(context, "run_guard", lambda *args: commands.append(args))

    assert guard["main"]("review-plan") == 1
    assert "verification.json" in capsys.readouterr().err
    assert not commands

    plan = feature / "verification.json"
    plan.write_text('{"cases": []}', encoding="utf-8")
    assert guard["main"]("review-plan") == 0
    assert commands == [
        ("strictdoc_workflow.py", "architecture", str(feature), "--verification-plan"),
    ]
    monkeypatch.setenv("SAFETYCOMPONENT_PLAN_REVISION", guard["revision"](feature, plan=True))
    assert guard["main"]("approved-plan") == 0
    plan.write_text('{"cases": [{"id": "changed"}]}', encoding="utf-8")
    assert guard["main"]("implementation") == 1
    assert "Reviewed artifacts have changed" in capsys.readouterr().err
    assert len(commands) == 1
