"""Project Beads completion onto Spec Kit task checkboxes."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

FEATURE_PREFIX = re.compile(r"([0-9]{3,})(?:-|$)")
TASK_LINE = re.compile(rb"^[ \t]*- \[([ xX])\] (T[0-9]{3,})(?=[ \t])")
FENCE = re.compile(rb"^ {0,3}(`{3,}|~{3,})(.*)")
BEADS_STATUSES = {"open", "in_progress", "blocked", "deferred", "closed"}


class ProjectionError(Exception):
    """A Beads reference or task document could not be reconciled."""


def task_markers(document: bytes) -> list[tuple[str, int, bytes]]:
    """Find task identifiers and checkbox byte offsets outside fenced examples."""
    markers: list[tuple[str, int, bytes]] = []
    seen: set[str] = set()
    offset = 0
    open_fence = b""
    for line in document.splitlines(keepends=True):
        fence = FENCE.match(line)
        if fence:
            delimiter, text = fence.groups()
            if not open_fence:
                open_fence = delimiter
            elif delimiter.startswith(open_fence) and not text.strip():
                open_fence = b""
        elif not open_fence and (task := TASK_LINE.match(line)):
            task_id = task[2].decode("ascii")
            if task_id in seen:
                raise ProjectionError(f"Duplicate task ID in tasks.md: {task_id}")
            seen.add(task_id)
            markers.append((task_id, offset + task.start(1), task[1]))
        offset += len(line)

    if not markers:
        raise ProjectionError("No Spec Kit task checkboxes found in tasks.md")
    return markers


def beads_command() -> str:
    """Locate the Beads CLI, accepting the Windows command shim if needed."""
    candidates = ("bd.exe", "bd.cmd") if os.name == "nt" else ("bd",)
    for candidate in candidates:
        if executable := shutil.which(candidate):
            return executable
    raise ProjectionError("Beads CLI not found on PATH")


def lookup_closed(executable: str, directory: Path, reference: str) -> bool:
    """Read one exact Beads reference and return whether its issue is closed."""
    # All arguments passed to the Windows shim are fixed or derived from numeric IDs.
    command = [
        executable, "list", "--all", "--external-ref", reference,
        "--limit", "2", "--brief", "--json", "--readonly",
    ]
    try:
        result = subprocess.run(
            command, cwd=directory, capture_output=True, check=True, encoding="utf-8", timeout=30
        )
    except subprocess.CalledProcessError as error:
        raise ProjectionError(f"Beads lookup failed for {reference} (exit {error.returncode})") from error
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise ProjectionError(f"Beads lookup failed for {reference}: {error}") from error

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProjectionError(f"Beads returned invalid JSON for {reference}") from error
    if not isinstance(issues, list):
        raise ProjectionError(f"Beads returned an invalid result for {reference}")
    if not issues:
        raise ProjectionError(f"No Beads issue found for {reference}")
    if len(issues) != 1:
        raise ProjectionError(f"Multiple Beads issues found for {reference}")

    issue = issues[0]
    status = issue.get("status") if isinstance(issue, dict) else None
    if not isinstance(status, str) or status not in BEADS_STATUSES:
        raise ProjectionError(f"Beads returned an unsupported status for {reference}")
    return status == "closed"


def write_projection(path: Path, original: bytes, projected: bytes) -> None:
    """Replace the complete document after checking for intervening edits."""
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(projected)
        temporary_path.chmod(path.stat().st_mode)
        if path.read_bytes() != original:
            raise ProjectionError(f"{path} changed during lookup. Run the projection again.")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Return 1 for drift in check mode and 2 when projection is impossible."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path, help="Path to a feature's tasks.md")
    parser.add_argument("--write", action="store_true", help="Write the projected checkboxes")
    arguments = parser.parse_args(argv)
    try:
        path = arguments.tasks.resolve()
        feature = FEATURE_PREFIX.match(path.parent.name)
        if path.name != "tasks.md" or feature is None:
            raise ProjectionError("Expected tasks.md inside a numerically prefixed feature directory")
        original = path.read_bytes()
        markers = task_markers(original)
        executable = beads_command()
        projected = bytearray(original)
        changed: list[str] = []
        for task_id, offset, marker in markers:
            reference = f"spec/{feature[1]}/{task_id}"
            closed = lookup_closed(executable, path.parent, reference)
            if closed != (marker != b" "):
                projected[offset] = ord("X") if closed else ord(" ")
                changed.append(task_id)
        if arguments.write and changed:
            write_projection(path, original, bytes(projected))
    except (OSError, ProjectionError) as error:
        print(f"Beads projection error: {error}", file=sys.stderr)
        return 2

    if not changed:
        print(f"{len(markers)} task checkboxes match Beads.")
        return 0
    if arguments.write:
        print(f"Updated {len(changed)} task checkboxes from Beads: {', '.join(changed)}")
        return 0
    print(f"Checkbox drift in {len(changed)} tasks: {', '.join(changed)}. Rerun with --write.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
