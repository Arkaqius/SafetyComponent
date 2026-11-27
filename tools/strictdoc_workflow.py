"""Validate a feature's canonical requirements and architecture decisions."""

import argparse
import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

REQUIRED_VERSION = "0.32.1"
HARA = Path(__file__).resolve().parents[1] / "docs/sys/SafetyConcept - HARA.sdoc"
LAYERS = {"STAKEHOLDER", "SYS", "SW"}
KINDS = {"FUNCTIONAL", "QUALITY", "CONSTRAINT"}
VERIFICATION_METHODS = {
    "STAKEHOLDER": {"stakeholder"},
    "SYS": {"system"},
    "SW": {"static", "unit", "integration"},
}


class StrictDocError(Exception):
    """A StrictDoc artifact does not meet the feature workflow contract."""


def export_documents(paths: list[Path]) -> list[dict[str, Any]]:
    """Parse SDoc and build its traceability graph with the installed StrictDoc CLI."""
    install = "python -m pip install -r tools/requirements-strictdoc.txt"
    try:
        installed = version("strictdoc")
    except PackageNotFoundError as error:
        raise StrictDocError(f"StrictDoc is required. Install it with: {install}") from error
    if installed != REQUIRED_VERSION:
        raise StrictDocError(f"Found StrictDoc {installed}. Install {REQUIRED_VERSION} with: {install}")

    with TemporaryDirectory(prefix="safetycomponent-strictdoc-") as temporary:
        output = Path(temporary)
        result = subprocess.run(
            [
                sys.executable, "-c", "from strictdoc.cli.main import main; raise SystemExit(main())",
                "export", *(str(path) for path in paths), "--formats=json",
                "--output-dir", str(output), "--no-parallelization",
            ],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode:
            diagnostic = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
            raise StrictDocError(f"StrictDoc export failed (exit {result.returncode}).\n{diagnostic}")
        index = output / "json/index.json"
        tree = json.loads(index.read_text(encoding="utf-8"))
    documents = tree.get("DOCUMENTS") if isinstance(tree, dict) else None
    if not isinstance(documents, list) or len(documents) != len(paths):
        raise StrictDocError("StrictDoc did not export every expected document")
    return documents


def iter_nodes(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield each authored node, including nodes nested under sections."""
    for node in document.get("NODES", []):
        yield node
        yield from iter_nodes(node)


def value(node: dict[str, Any], key: str) -> str:
    """Return a present and nonblank StrictDoc field."""
    field = node.get(key)
    if not isinstance(field, str) or not field.strip():
        raise StrictDocError(f"{node.get('UID', node.get('_NODE_TYPE'))}: missing {key}")
    return field


def parents(node: dict[str, Any], role: str) -> list[str]:
    """Read the parent UID list in the required relation role."""
    return [
        value(relation, "VALUE")
        for relation in node.get("RELATIONS", [])
        if relation.get("TYPE") == "Parent" and relation.get("ROLE") == role
    ]


def validate_verification_plan(plan: object, layers: dict[str, str]) -> None:
    """Require a compatible verification case for each canonical requirement."""
    cases = plan.get("cases") if isinstance(plan, dict) else None
    if not isinstance(cases, list):
        raise StrictDocError("verification.json must contain a cases array")

    allowed_methods = set().union(*VERIFICATION_METHODS.values())
    case_ids: set[str] = set()
    covered: set[str] = set()
    for index, case in enumerate(cases, start=1):
        case_id = case.get("id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id.strip():
            raise StrictDocError(f"verification.json case {index}: expected a nonblank id")
        case_id = case_id.strip()
        if case_id in case_ids:
            raise StrictDocError(f"verification.json: duplicate case id {case_id}")
        case_ids.add(case_id)

        method, expected = case.get("method"), case.get("expected")
        if not isinstance(method, str) or method not in allowed_methods:
            raise StrictDocError(f"verification.json case {case_id}: unknown method {method!r}")
        if not isinstance(expected, str) or not expected.strip():
            raise StrictDocError(f"verification.json case {case_id}: expected must be nonblank text")

        requirements = case.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            raise StrictDocError(f"verification.json case {case_id}: expected a nonempty requirements array")
        case_requirements: set[str] = set()
        for identifier in requirements:
            if not isinstance(identifier, str) or identifier not in layers:
                raise StrictDocError(f"verification.json case {case_id}: unknown requirement UID {identifier!r}")
            if identifier in case_requirements:
                raise StrictDocError(f"verification.json case {case_id}: duplicate requirement UID {identifier}")
            case_requirements.add(identifier)
            if method in VERIFICATION_METHODS[layers[identifier]]:
                covered.add(identifier)

    missing = sorted(layers.keys() - covered)
    if missing:
        detail = ", ".join(f"{identifier} ({layers[identifier]})" for identifier in missing)
        raise StrictDocError(f"verification.json: no compatible verification case for {detail}")


def validate(
    documents: list[dict[str, Any]], *, architecture: bool, verification_plan: Path | None = None,
) -> tuple[int, int]:
    """Check requirement allocation and traceable ADRs on parsed documents."""
    records: dict[str, dict[str, Any]] = {}
    no_adr_count = 0
    for document in documents:
        nodes = list(iter_nodes(document))
        node_types = {node["_NODE_TYPE"] for node in nodes}
        if "REQUIREMENT" in node_types and node_types & {"ADR", "NO_ADR"}:
            raise StrictDocError("Keep requirements and ADRs in their respective SDoc files")
        for node in nodes:
            if node["_NODE_TYPE"] == "NO_ADR":
                value(node, "RATIONALE")
                no_adr_count += 1
            if node["_NODE_TYPE"] not in {"REQUIREMENT", "ADR"}:
                continue
            identifier = value(node, "UID")
            if identifier.startswith("EXAMPLE-"):
                raise StrictDocError(f"{identifier}: replace the example with a feature-specific record")
            if identifier in records:
                raise StrictDocError(f"Duplicate record UID {identifier}")
            records[identifier] = node

    layers: dict[str, str] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for identifier, node in records.items():
        value(node, "TITLE")
        if node["_NODE_TYPE"] == "ADR":
            for field in ("CONTEXT", "DECISION", "CONSEQUENCES"):
                value(node, field)
            decisions[identifier] = node
            continue
        layer, kind = value(node, "LAYER"), value(node, "KIND")
        if layer not in LAYERS or kind not in KINDS:
            raise StrictDocError(f"{identifier}: invalid LAYER or KIND")
        value(node, "STATEMENT")
        value(node, "VERIFICATION")
        layers[identifier] = layer
    if not layers:
        raise StrictDocError("requirements.sdoc must contain at least one requirement")
    if not architecture and (decisions or no_adr_count):
        raise StrictDocError("Store ADRs in architecture.sdoc")
    if architecture and (no_adr_count > 1 or bool(decisions) == bool(no_adr_count)):
        raise StrictDocError("architecture.sdoc must contain ADRs or one NO_ADR rationale")

    known_goals: set[str] | None = None
    for identifier, layer in layers.items():
        node = records[identifier]
        links = parents(node, "Refines")
        goals = node.get("SAFETY_GOALS")
        if goals:
            if known_goals is None:
                hara, = export_documents([HARA])
                known_goals = {
                    value(goal, "UID")
                    for goal in iter_nodes(hara)
                    if goal["_NODE_TYPE"] == "SAFETY_GOAL"
                }
            requested_goals = {item.strip() for item in goals.split(",")}
            if layer != "SYS" or not requested_goals <= known_goals:
                raise StrictDocError(f"{identifier}: SAFETY_GOALS must reference known HARA goals from a SYS requirement")
        if layer == "STAKEHOLDER":
            if links:
                raise StrictDocError(f"{identifier}: stakeholder requirement cannot refine another layer")
            continue
        required_parent = "STAKEHOLDER" if layer == "SYS" else "SYS"
        if (not links and not goals) or any(layers.get(link) != required_parent for link in links):
            alternative = " or cite a HARA safety goal" if layer == "SYS" and not links else ""
            raise StrictDocError(f"{identifier}: {layer} requirement must refine {required_parent}{alternative}")

    for identifier, adr in decisions.items():
        links = parents(adr, "Addresses")
        if not links or any(layers.get(link) not in {"SYS", "SW"} for link in links):
            raise StrictDocError(f"{identifier}: ADR must address at least one SYS or SW requirement")
    if verification_plan is not None:
        try:
            plan = json.loads(verification_plan.read_text(encoding="utf-8"))
        except ValueError as error:
            raise StrictDocError(f"Invalid JSON in {verification_plan}: {error}") from error
        validate_verification_plan(plan, layers)
    return len(layers), len(decisions)


def main(argv: list[str] | None = None) -> int:
    """Check the artifacts required by the selected feature stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("requirements", "architecture"))
    parser.add_argument("feature", type=Path)
    parser.add_argument("--verification-plan", action="store_true", help="Validate the feature's verification.json")
    args = parser.parse_args(argv)
    feature = args.feature.resolve()
    architecture = args.stage == "architecture"
    if args.verification_plan and not architecture:
        parser.error("--verification-plan requires the architecture stage")
    paths = [feature / "requirements.sdoc"]
    if architecture:
        paths.append(feature / "architecture.sdoc")
    verification_plan = feature / "verification.json" if args.verification_plan else None
    try:
        for path in paths:
            if not path.is_file():
                raise StrictDocError(f"Missing StrictDoc artifact {path}")
        if verification_plan is not None and not verification_plan.is_file():
            raise StrictDocError(f"Missing required artifact {verification_plan}")
        requirements, decisions = validate(export_documents(paths[:1]), architecture=False)
        if architecture:
            # The combined export resolves ADR links against the separately validated requirements file.
            all_requirements, decisions = validate(
                export_documents(paths), architecture=True, verification_plan=verification_plan,
            )
            if all_requirements != requirements:
                raise StrictDocError("Store all feature requirements in requirements.sdoc")
    except (OSError, ValueError, StrictDocError) as error:
        print(f"StrictDoc validation failed: {error}", file=sys.stderr)
        return 2
    print(f"Validated {requirements} requirements and {decisions} architecture decisions")
    if verification_plan is not None:
        print("Validated verification.json coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
