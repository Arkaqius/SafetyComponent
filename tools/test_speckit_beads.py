"""Verify checkbox projection without accessing a real Beads database."""

import json
import subprocess
from pathlib import Path

import pytest

import speckit_beads


@pytest.fixture
def task_file(tmp_path: Path) -> Path:
    path = tmp_path / "003-heating-monitoring" / "tasks.md"
    path.parent.mkdir()
    path.write_bytes(
        b"# Tasks\r\n\n"
        b"- [ ] T001 [US1] Inspect the inputs\r\n"
        b"```text\n- [ ] T999 Example only\n```\r\n"
        b"- [ ] A regular checklist item\n"
        b"- [x] T002 Check the output\n"
        b"- [x] T003 Keep an already closed marker\n"
        b"- [X] T004 Reopen the task"
    )
    return path


@pytest.fixture(autouse=True)
def mock_beads(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_lookup(*args: object, **kwargs: object) -> None:
        pytest.fail("Test did not configure its Beads lookup")

    monkeypatch.setattr(speckit_beads, "beads_command", lambda: "fixture-bd")
    monkeypatch.setattr(speckit_beads.subprocess, "run", unexpected_lookup)


def test_check_and_write_preserve_other_bytes(
    task_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original = task_file.read_bytes()
    statuses = dict(T001="closed", T002="blocked", T003="closed", T004="open")

    def list_issues(command: list[str], **settings: object) -> subprocess.CompletedProcess[str]:
        prefix, feature, task_id = command[4].split("/")
        assert (prefix, feature) == ("spec", "003")
        assert command == [
            "fixture-bd", "list", "--all", "--external-ref", command[4],
            "--limit", "2", "--brief", "--json", "--readonly",
        ]
        assert settings["cwd"] == task_file.parent
        assert not settings.get("shell")
        return subprocess.CompletedProcess(command, 0, json.dumps([{"status": statuses[task_id]}]))

    monkeypatch.setattr(speckit_beads.subprocess, "run", list_issues)

    assert speckit_beads.main([str(task_file)]) == 1
    assert "T001, T002, T004" in capsys.readouterr().out
    assert task_file.read_bytes() == original
    assert speckit_beads.main([str(task_file), "--write"]) == 0
    expected = original.replace(b"[ ] T001", b"[X] T001").replace(b"[x] T002", b"[ ] T002")
    expected = expected.replace(b"[X] T004", b"[ ] T004")
    assert task_file.read_bytes() == expected
    assert speckit_beads.main([str(task_file)]) == 0


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ("[]", "No Beads issue found"),
        ('[{"status": "closed"}, {"status": "open"}]', "Multiple Beads issues found"),
        ('[{"status": "typo"}]', "unsupported status"),
        ("garbled", "invalid JSON"),
        (None, "Beads lookup failed"),
    ],
)
def test_write_is_all_or_nothing_on_lookup_failure(
    task_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    response: str | None,
    message: str,
) -> None:
    original = task_file.read_bytes()

    def list_issues(command: list[str], **settings: object) -> subprocess.CompletedProcess[str]:
        if command[4] == "spec/003/T001":
            return subprocess.CompletedProcess(command, 0, '[{"status": "closed"}]')
        if response is None:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, response)

    monkeypatch.setattr(speckit_beads.subprocess, "run", list_issues)
    assert speckit_beads.main([str(task_file), "--write"]) == 2
    error = capsys.readouterr().err
    assert message in error
    assert "spec/003/T002" in error
    assert task_file.read_bytes() == original


def test_duplicate_task_ids_are_rejected_before_lookup(
    task_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file.write_bytes(b"- [ ] T001 One\n- [x] T001 Two\n")
    assert speckit_beads.main([str(task_file), "--write"]) == 2
    assert "Duplicate task ID in tasks.md: T001" in capsys.readouterr().err


def test_write_preserves_intervening_changes(task_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    edited = task_file.read_bytes() + b"\nAn intervening edit\n"

    def list_issues(command: list[str], **settings: object) -> subprocess.CompletedProcess[str]:
        task_file.write_bytes(edited)
        return subprocess.CompletedProcess(command, 0, '[{"status": "closed"}]')

    monkeypatch.setattr(speckit_beads.subprocess, "run", list_issues)
    assert speckit_beads.main([str(task_file), "--write"]) == 2
    assert task_file.read_bytes() == edited
    assert list(task_file.parent.iterdir()) == [task_file]
