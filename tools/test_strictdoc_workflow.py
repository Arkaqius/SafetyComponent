"""Exercise canonical StrictDoc artifacts and per-stage guards."""

import json
from importlib.util import find_spec
from pathlib import Path

import pytest

import strictdoc_workflow as workflow

TEMPLATES = Path(__file__).resolve().parents[1] / ".specify/templates/overrides"
REQUIREMENT_LAYERS = {"F023-STK-001": "STAKEHOLDER", "F023-SYS-001": "SYS", "F023-SW-001": "SW"}


@pytest.fixture
def feature(tmp_path: Path) -> Path:
    path = tmp_path / "023-fixture directory"
    path.mkdir()
    for name in ("requirements", "architecture"):
        content = (TEMPLATES / f"strictdoc-{name}.sdoc").read_text(encoding="utf-8")
        (path / f"{name}.sdoc").write_text(content.replace("EXAMPLE-", "F023-"), encoding="utf-8")
    return path


@pytest.mark.skipif(find_spec("strictdoc") is None, reason="requires tools/requirements-strictdoc.txt")
def test_real_parser_checks_each_stage(
    feature: Path, capsys: pytest.CaptureFixture[str], verification_cases: list[dict],
) -> None:
    assert workflow.main(["requirements", str(feature)]) == 0
    assert workflow.main(["architecture", str(feature)]) == 0
    assert "Validated 3 requirements and 1 architecture decisions" in capsys.readouterr().out

    path = feature / "architecture.sdoc"
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace("F023-SW-001", "F023-SW-missing"), encoding="utf-8")
    assert workflow.main(["architecture", str(feature)]) == 2
    assert "F023-SW-missing" in capsys.readouterr().err
    assert workflow.main(["requirements", str(feature)]) == 0
    grammar, _, _ = source.partition("\n[ADR]\n")
    path.write_text(
        f"{grammar}\n[NO_ADR]\nRATIONALE: The work uses an approved interface.\n",
        encoding="utf-8",
    )
    (feature / "verification.json").write_text(json.dumps({"cases": verification_cases}), encoding="utf-8")
    assert workflow.main(["architecture", str(feature), "--verification-plan"]) == 0
    assert "Validated verification.json coverage" in capsys.readouterr().out


def test_architecture_stage_requires_its_document(
    feature: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (feature / "architecture.sdoc").unlink()
    assert workflow.main(["architecture", str(feature)]) == 2
    assert "architecture.sdoc" in capsys.readouterr().err


def requirement(identifier: str, layer: str, parent: str | None = None) -> dict:
    """Create an exported requirement record for semantic checks."""
    node = {
        "_NODE_TYPE": "REQUIREMENT",
        "UID": identifier,
        "LAYER": layer,
        "KIND": "FUNCTIONAL",
        "TITLE": "Fixture title",
        "STATEMENT": "The fixture shall report its state.",
        "VERIFICATION": "Observe the state in the fixture.",
    }
    return {
        **node,
        **({"RELATIONS": [{"TYPE": "Parent", "ROLE": "Refines", "VALUE": parent}]} if parent else {}),
    }


def test_sw_requires_sys_parent() -> None:
    nodes = [requirement("F023-STK-001", "STAKEHOLDER"), requirement("F023-SW-001", "SW", "F023-STK-001")]
    with pytest.raises(workflow.StrictDocError, match="must refine SYS"):
        workflow.validate([{"NODES": nodes}], architecture=False)


def test_sys_can_refine_existing_hara_goal() -> None:
    node = {**requirement("F023-SYS-001", "SYS"), "SAFETY_GOALS": "SG-003"}
    assert workflow.validate([{"NODES": [node]}], architecture=False) == (1, 0)
    node["SAFETY_GOALS"] = "SG-999"
    with pytest.raises(workflow.StrictDocError, match="known HARA goals"):
        workflow.validate([{"NODES": [node]}], architecture=False)


def test_placeholder_uid_rejected() -> None:
    node = requirement("EXAMPLE-STK-001", "STAKEHOLDER")
    with pytest.raises(workflow.StrictDocError, match="replace the example"):
        workflow.validate([{"NODES": [node]}], architecture=False)


def test_architecture_may_record_an_explicit_no_adr_rationale() -> None:
    nodes = [{"NODES": [requirement("F023-STK-001", "STAKEHOLDER")]}]
    no_adr = {"_NODE_TYPE": "NO_ADR", "RATIONALE": "The change uses an existing interface."}
    assert workflow.validate([*nodes, {"NODES": [no_adr]}], architecture=True) == (1, 0)
    with pytest.raises(workflow.StrictDocError, match="one NO_ADR"):
        workflow.validate([*nodes, {"NODES": [no_adr, no_adr]}], architecture=True)


@pytest.fixture
def verification_cases() -> list[dict]:
    return [
        {"id": identifier, "method": method, "requirements": [requirement_uid], "expected": "Observe the expected state."}
        for (identifier, method, requirement_uid) in [
            ("V-01", "stakeholder", "F023-STK-001"),
            ("V-02", "system", "F023-SYS-001"),
            ("V-03", "integration", "F023-SW-001"),
        ]
    ]


@pytest.mark.parametrize("method", ["unit", "static", "system"])
def test_verification_allows_shared_requirements(verification_cases: list[dict], method: str) -> None:
    verification_cases.append({**verification_cases[-1], "id": "V-04", "method": method})
    workflow.validate_verification_plan({"cases": verification_cases}, REQUIREMENT_LAYERS)


@pytest.mark.parametrize(
    ("change", "diagnostic"),
    [
        ({"id": "  "}, "nonblank id"),
        ({"id": " V-02 "}, "duplicate case id V-02"),
        ({"requirements": []}, "nonempty requirements array"),
        ({"requirements": ["F023-SW-001", "F023-SW-001"]}, "duplicate requirement UID F023-SW-001"),
        ({"requirements": ["F023-ADR-001"]}, "unknown requirement UID 'F023-ADR-001'"),
        ({"method": "manual"}, "unknown method 'manual'"),
        ({"method": "system"}, r"no compatible verification case for F023-SW-001 \(SW\)"),
        ({"expected": " \n"}, "expected must be nonblank text"),
    ],
)
def test_verification_rejects_invalid_cases(verification_cases: list[dict], change: dict, diagnostic: str) -> None:
    verification_cases[-1].update(change)
    with pytest.raises(workflow.StrictDocError, match=diagnostic):
        workflow.validate_verification_plan({"cases": verification_cases}, REQUIREMENT_LAYERS)


@pytest.mark.parametrize(
    ("plan", "diagnostic"),
    [([], "cases array"), ({"cases": []}, r"F023-STK-001 .*F023-SW-001 .*F023-SYS-001")],
)
def test_verification_rejects_missing_coverage_or_invalid_plan(plan: object, diagnostic: str) -> None:
    with pytest.raises(workflow.StrictDocError, match=diagnostic):
        workflow.validate_verification_plan(plan, REQUIREMENT_LAYERS)


def test_verification_flag_requires_architecture_and_plan(feature: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert workflow.main(["architecture", str(feature), "--verification-plan"]) == 2
    assert "Missing required artifact" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        workflow.main(["requirements", str(feature), "--verification-plan"])
    assert error.value.code == 2
    assert "requires the architecture stage" in capsys.readouterr().err


def test_verification_plan_must_be_json(tmp_path: Path) -> None:
    plan = tmp_path / "verification.json"
    plan.write_text("this is not JSON", encoding="utf-8")
    records = [requirement("F023-STK-001", "STAKEHOLDER")]
    no_adr = {"_NODE_TYPE": "NO_ADR", "RATIONALE": "Fixture uses an existing interface."}
    with pytest.raises(workflow.StrictDocError, match=r"Invalid JSON in .*verification.json"):
        workflow.validate([{"NODES": records}, {"NODES": [no_adr]}], architecture=True, verification_plan=plan)
