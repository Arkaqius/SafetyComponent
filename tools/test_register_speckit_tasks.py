"""Exercise registration and retries without touching a real Beads workspace."""

import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import register_speckit_tasks

TASKS = (
    b"# Example\n"
    b"- [ ] T003 Run integration <!-- depends: T001,T002 -->\r\n"
    b"`<!-- depends: none -->` in prose\n"
    b"```markdown\n- [ ] T999 Example without annotation\n```\n"
    b"- [x] T001 Inspect input `%PATH% & echo !` <!-- depends: none -->\n"
    b"- [ ] T002 Review output <!-- depends: T001 -->\n"
)


class FixtureBeads:
    """The CLI operations used by the importer, backed only by test dictionaries."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.issues: dict[str, list[dict[str, Any]]] = {}
        self.edges: dict[str, dict[str, str]] = {}
        self.writes: list[str] = []
        self.fail_ref: str | None = None
        self.concurrent_ref: str | None = None

    def run(self, command: list[str], **settings: object) -> subprocess.CompletedProcess[str]:
        assert settings["cwd"] == self.directory
        assert not settings.get("shell")
        assert command[0] == "fixture-bd"
        assert command[-1] == "--json"
        code = 0
        if command[1] == "list":
            assert "--all" in command and "--readonly" in command
            if "--external-ref" in command:
                result: object = self.issues.get(command[command.index("--external-ref") + 1], [])
            else:
                substring = command[command.index("--external-contains") + 1]
                result = [issue for reference, issues in self.issues.items()
                          if substring in reference for issue in issues]
        elif command[1] == "where":
            assert "--readonly" in command
            result = {"prefix": "fixture"}
        elif command[1] == "create":
            reference = command[command.index("--external-ref") + 1]
            if reference == self.fail_ref:
                return subprocess.CompletedProcess(command, 1, '{"error": "fixture interrupted"}')
            assert reference not in self.issues
            assert "%PATH%" not in " ".join(command)
            assert "--stdin" in command
            issue_id = command[command.index("--id") + 1]
            raw_metadata = command[command.index("--metadata") + 1]
            if raw_metadata.startswith("@"):
                raw_metadata = (self.directory / raw_metadata[1:]).read_text(encoding="utf-8")
            issue = {
                "id": issue_id,
                "status": command[command.index("--status") + 1] if "--status" in command else "open",
                "external_ref": reference,
                "description": settings["input"],
                "metadata": json.loads(raw_metadata),
            }
            self.issues[reference] = [issue]
            self.writes.append(reference)
            prerequisites = command[command.index("--deps") + 1].split(",") if "--deps" in command else []
            assert all(any(records[0]["id"] == identifier for records in self.issues.values())
                       for identifier in prerequisites)
            self.edges[issue_id] = dict.fromkeys(prerequisites, "blocks")
            result = issue
            if reference == self.concurrent_ref:
                result = {"error": "another importer created this issue"}
                code = 1
        elif command[1] == "update":
            graph = self.issues["spec/901/graph"][0]
            assert graph["id"] == command[2]
            metadata_path = command[command.index("--metadata") + 1]
            assert metadata_path.startswith("@")
            graph["metadata"] = json.loads((self.directory / metadata_path[1:]).read_text(encoding="utf-8"))
            self.writes.append("update graph")
            result = graph
        elif command[1:3] == ["dep", "list"]:
            assert "--readonly" in command
            result = [{"id": target, "dependency_type": kind}
                      for target, kind in self.edges.get(command[3], {}).items()]
        elif command[1:3] == ["dep", "add"]:
            origin, target = command[3:5]
            assert command[5:7] == ["--type", "blocks"]
            assert target not in self.edges.setdefault(origin, {})
            self.edges[origin][target] = "blocks"
            self.writes.append(f"{origin} -> {target}")
            result = {"status": "added"}
        else:
            pytest.fail(f"Unexpected fixture Beads command: {command}")
        return subprocess.CompletedProcess(command, code, json.dumps(result))

    def issue(self, task_id: str) -> dict[str, Any]:
        return self.issues[f"spec/901/{task_id}"][0]


@pytest.fixture
def tasks_and_beads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, FixtureBeads]:
    path = tmp_path / "901-fixture" / "tasks.md"
    path.parent.mkdir()
    path.write_bytes(TASKS)
    beads = FixtureBeads(path.parent)
    monkeypatch.setattr(register_speckit_tasks, "beads_command", lambda: "fixture-bd")
    monkeypatch.setattr(register_speckit_tasks.subprocess, "run", beads.run)
    return path, beads


def test_register_creates_tasks_with_prerequisites_and_preserves_status_on_retry(
    tasks_and_beads: tuple[Path, FixtureBeads], capsys: pytest.CaptureFixture[str],
) -> None:
    path, beads = tasks_and_beads
    assert register_speckit_tasks.main([str(path)]) == 0
    assert "3 created, 0 reused, 3 blockers added" in capsys.readouterr().out
    assert beads.writes == ["spec/901/T001", "spec/901/T002", "spec/901/T003"]
    first = beads.issue("T001")
    second = beads.issue("T002")
    third = beads.issue("T003")
    assert first["description"] == "Inspect input `%PATH% & echo !`"
    assert first["status"] == "open"
    assert beads.edges[third["id"]] == {first["id"]: "blocks", second["id"]: "blocks"}
    first["status"] = "closed"
    first["description"] = "A human updated the issue description"
    beads.writes.clear()

    assert register_speckit_tasks.main([str(path)]) == 0
    assert "0 created, 3 reused, 0 blockers added" in capsys.readouterr().out
    assert beads.writes == []
    assert first["status"] == "closed"
    assert first["description"] == "A human updated the issue description"
    assert path.read_bytes() == TASKS


def structured_task(
    key: str, dependencies: list[str], phase: str = "setup", story: str | None = None,
) -> dict[str, object]:
    return {"id": key, "description": f"Check {key} in backend/api.py", "phase": phase,
            "story": story, "files": ["backend/api.py"], "requirements": ["FR-001"],
            "dependencies": dependencies}


def publish(
    directory: Path, monkeypatch: pytest.MonkeyPatch, tasks: list[dict[str, object]],
    append: bool = False,
) -> int:
    monkeypatch.setattr(register_speckit_tasks.sys, "stdin", io.StringIO(json.dumps({"tasks": tasks})))
    arguments = [str(directory), "--stdin"]
    if append:
        arguments.append("--append")
    return register_speckit_tasks.main(arguments)


def test_direct_publication_and_check_bind_the_graph_to_feature_artifacts(
    tasks_and_beads: tuple[Path, FixtureBeads], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, beads = tasks_and_beads
    path.unlink()
    plan = path.parent / "plan.md"
    plan.write_text("Approved plan", encoding="utf-8")
    requirements = path.parent / "requirements.sdoc"
    requirements.write_text("Approved requirements", encoding="utf-8")
    tasks = [structured_task("T002", ["T001"], "story", "US1"), structured_task("T001", [])]

    assert publish(path.parent, monkeypatch, tasks) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["tasks"][1]["dependencies"] == ["T001"]
    assert result["tasks"][1]["requirements"] == ["FR-001"]
    assert result["tasks"][1]["blocking_beads_ids"] == [beads.issue("T001")["id"]]
    assert beads.writes == ["spec/901/T001", "spec/901/T002", "spec/901/graph"]
    assert beads.issues["spec/901/graph"][0]["status"] == "closed"
    assert not path.exists()

    beads.writes.clear()
    beads.issue("T001")["status"] = "closed"
    assert publish(path.parent, monkeypatch, tasks) == 0
    assert beads.writes == []
    assert json.loads(capsys.readouterr().out)["tasks"][0]["status"] == "closed"

    args = [str(path.parent), "--check", "--require-closed"]
    assert register_speckit_tasks.main(args) == 2
    assert "unfinished feature tasks: T002" in capsys.readouterr().err
    beads.issue("T002")["status"] = "closed"
    assert register_speckit_tasks.main(args) == 0
    capsys.readouterr()

    requirements.write_text("Changed requirements", encoding="utf-8")
    assert register_speckit_tasks.main([str(path.parent), "--check"]) == 2
    assert "current feature artifact revisions" in capsys.readouterr().err


def test_interrupted_publication_and_convergence_retry_keep_gate_closed_until_complete(
    tasks_and_beads: tuple[Path, FixtureBeads], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, beads = tasks_and_beads
    (path.parent / "plan.md").write_text("Plan", encoding="utf-8")
    first = structured_task("T001", [])
    second = structured_task("T002", ["T001"])
    beads.fail_ref = "spec/901/T002"
    assert publish(path.parent, monkeypatch, [first, second]) == 2
    assert register_speckit_tasks.main([str(path.parent), "--check"]) == 2
    beads.fail_ref = None
    assert publish(path.parent, monkeypatch, [first, second]) == 0

    extension = [structured_task("T003", ["T002"], "convergence"),
                 structured_task("T004", ["T003"], "convergence")]
    beads.fail_ref = "spec/901/T004"
    assert publish(path.parent, monkeypatch, extension, append=True) == 2
    assert register_speckit_tasks.main([str(path.parent), "--check"]) == 2
    beads.fail_ref = None
    capsys.readouterr()
    assert publish(path.parent, monkeypatch, extension, append=True) == 0
    assert len(json.loads(capsys.readouterr().out)["tasks"]) == 4

    beads.writes.clear()
    beads.edges[beads.issue("T004")["id"]].clear()
    assert register_speckit_tasks.main([str(path.parent), "--check"]) == 2
    assert "membership or blockers" in capsys.readouterr().err
    assert beads.writes == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"files": ["../outside.py"]}, "repository-relative paths"),
        ({"phase": "story"}, "requires a USn story"),
        ({"dependencies": ["T009"]}, "unknown dependency T009"),
        ({"dependencies": ["T001"]}, "dependency cycle"),
    ],
)
def test_invalid_structured_task_cannot_publish(
    tasks_and_beads: tuple[Path, FixtureBeads], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], change: dict[str, object], expected: str,
) -> None:
    path, beads = tasks_and_beads
    (path.parent / "plan.md").write_text("Plan", encoding="utf-8")
    assert publish(path.parent, monkeypatch, [{**structured_task("T001", []), **change}]) == 2
    assert expected in capsys.readouterr().err
    assert beads.writes == []


@pytest.mark.parametrize(
    ("document", "error"),
    [
        (b"- [ ] T001 Old task\n", "expected a final"),
        (TASKS + b"- [ ] T001 Duplicate <!-- depends: none -->\n", "Duplicate task ID"),
        (TASKS.replace(b"T001,T002", b"T001,T001"), "duplicate dependency ID"),
        (TASKS.replace(b"T001,T002", b"T099"), "unknown dependency T099"),
        (TASKS.replace(b"depends: none", b"depends: T003"), "Task dependency cycle"),
        (TASKS.replace(b"T001,T002", b"T003"), "Task dependency cycle"),
    ],
)
def test_invalid_graph_is_rejected_before_beads_lookup(
    tasks_and_beads: tuple[Path, FixtureBeads], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], document: bytes, error: str,
) -> None:
    path, _ = tasks_and_beads
    path.write_bytes(document)

    def unexpected_lookup() -> str:
        pytest.fail("Importer accessed Beads before validating the complete graph")

    monkeypatch.setattr(register_speckit_tasks, "beads_command", unexpected_lookup)
    assert register_speckit_tasks.main([str(path)]) == 2
    assert error in capsys.readouterr().err


def test_partial_create_can_be_retried_and_missing_blocker_is_added(
    tasks_and_beads: tuple[Path, FixtureBeads], capsys: pytest.CaptureFixture[str],
) -> None:
    path, beads = tasks_and_beads
    beads.fail_ref = "spec/901/T002"
    assert register_speckit_tasks.main([str(path)]) == 2
    assert "fixture interrupted" in capsys.readouterr().err
    first = beads.issue("T001")
    first["status"] = "in_progress"
    beads.fail_ref = None
    beads.concurrent_ref = "spec/901/T002"
    assert register_speckit_tasks.main([str(path)]) == 0
    second = beads.issue("T002")
    assert beads.edges[second["id"]] == {first["id"]: "blocks"}
    assert first["status"] == "in_progress"

    beads.edges[second["id"]].clear()
    beads.writes.clear()
    assert register_speckit_tasks.main([str(path)]) == 0
    assert beads.writes == [f"{second['id']} -> {first['id']}"]


@pytest.mark.parametrize("conflict", ["identity", "duplicate", "edge"])
def test_conflicts_are_reported_before_creating_missing_issues(
    tasks_and_beads: tuple[Path, FixtureBeads], capsys: pytest.CaptureFixture[str], conflict: str,
) -> None:
    path, beads = tasks_and_beads
    assert register_speckit_tasks.main([str(path)]) == 0
    beads.writes.clear()
    del beads.issues["spec/901/T003"]
    first = beads.issue("T001")
    second = beads.issue("T002")

    if conflict == "identity":
        path.write_bytes(TASKS.replace(b"Inspect input", b"Replace input"))
        expected = "Task identity conflict for spec/901/T001"
    elif conflict == "duplicate":
        beads.issues["spec/901/T002"].append({"id": "fixture-duplicated"})
        expected = "Multiple Beads issues found for spec/901/T002"
    else:
        beads.edges[second["id"]][first["id"]] = "tracks"
        expected = "expected blocks"

    assert register_speckit_tasks.main([str(path)]) == 2
    assert expected in capsys.readouterr().err
    assert beads.writes == []
