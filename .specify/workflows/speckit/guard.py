"""Validate and identify the feature artifacts reviewed by a Spec Kit run."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
FEATURE_DIRECTORY = re.compile(r"docs/features/[0-9]{3,}-[a-z0-9]+(?:-[a-z0-9]+)*")
SPEC_ARTIFACTS = ("spec.md", "requirements.sdoc")
PLAN_ARTIFACTS = ("plan.md", "architecture.sdoc", "verification.json")
OPTIONAL_PLAN_ARTIFACTS = ("research.md", "data-model.md", "quickstart.md")


def feature_directory() -> Path:
    """Resolve the workflow input independently of the checkout feature pointer."""
    directory = os.environ.get("SAFETYCOMPONENT_WORKFLOW_FEATURE", "")
    if not FEATURE_DIRECTORY.fullmatch(directory):
        raise ValueError("feature_directory must use docs/features/<number>-<slug>.")
    path = REPO / directory
    if path.resolve() != path:
        raise ValueError("feature_directory must resolve directly under the repository.")
    return path


def revision(feature: Path, *, plan: bool = False) -> str:
    """Hash the reviewed document names and contents in deterministic order."""
    required = SPEC_ARTIFACTS + PLAN_ARTIFACTS if plan else SPEC_ARTIFACTS
    artifacts = [feature / name for name in required]
    if plan:
        artifacts.extend(
            feature / name
            for name in OPTIONAL_PLAN_ARTIFACTS
            if (feature / name).exists()
        )
        contracts = feature / "contracts"
        if contracts.resolve() != contracts:
            raise ValueError("The feature's contracts directory must resolve inside the feature.")
        artifacts.extend(sorted(path for path in contracts.rglob("*") if path.is_file()))

    digest = hashlib.sha256()
    for path in artifacts:
        if not path.resolve().is_relative_to(feature):
            raise ValueError(f"The reviewed artifact {path} resolves outside the feature.")
        content = path.read_bytes()
        if path.name in required and path.parent == feature and not content.strip():
            raise ValueError(f"The reviewed artifact {path} is empty.")
        digest.update(path.relative_to(feature).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def check_revision(feature: Path, name: str, *, plan: bool = False) -> None:
    """Stop when an approved artifact has changed since its review."""
    expected = os.environ.get(name)
    if not expected or revision(feature, plan=plan) != expected:
        raise ValueError("Reviewed artifacts have changed. Review the current revision in a new run.")


def run_guard(tool: str, *args: str) -> None:
    """Run an existing read-only validation tool and surface its errors."""
    result = subprocess.run(
        [sys.executable, str(REPO / "tools" / tool), *args],
        cwd=REPO,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"{tool} exited with code {result.returncode}. {detail}")


def validated_revision(feature: Path, *, plan: bool) -> str:
    """Validate the documents and only report a revision that stayed stable."""
    before = revision(feature, plan=plan)
    stage = "architecture" if plan else "requirements"
    options = ("--verification-plan",) if plan else ()
    run_guard("strictdoc_workflow.py", stage, str(feature), *options)
    if revision(feature, plan=plan) != before:
        raise ValueError("Feature artifacts changed during validation. Run the validation again.")
    return before


def main(mode: str) -> int:
    """Validate or check the relevant artifacts before advancing the workflow."""
    try:
        feature = feature_directory()
        if mode == "preflight":
            return 0
        if mode == "review-spec":
            print(json.dumps({"revision": validated_revision(feature, plan=False)}))
        elif mode == "approved-spec":
            check_revision(feature, "SAFETYCOMPONENT_SPEC_REVISION")
        elif mode == "review-plan":
            check_revision(feature, "SAFETYCOMPONENT_SPEC_REVISION")
            reviewed = validated_revision(feature, plan=True)
            check_revision(feature, "SAFETYCOMPONENT_SPEC_REVISION")
            print(json.dumps({"revision": reviewed}))
        elif mode in {"approved-plan", "implementation", "completed"}:
            check_revision(feature, "SAFETYCOMPONENT_PLAN_REVISION", plan=True)
            if mode in {"implementation", "completed"}:
                args = [str(feature), "--check"]
                if mode == "completed":
                    args.append("--require-closed")
                run_guard("register_speckit_tasks.py", *args)
        else:
            raise ValueError(f"Unknown workflow guard {mode!r}.")
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) == 2 else ""))
