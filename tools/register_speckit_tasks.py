"""Register dependency-annotated Spec Kit tasks and their blockers in Beads."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from tempfile import NamedTemporaryFile

from speckit_beads import FEATURE_PREFIX, TASK_LINE, ProjectionError, beads_command, task_markers

DEPENDENCIES = re.compile(rb"[ \t]+<!-- depends: (none|T[0-9]{3,}(?:,[ \t]*T[0-9]{3,})*) -->[ \t]*$")
SAFE_BEADS_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
FINGERPRINT_KEY = "speckit_task_fingerprint"
TASK_METADATA = "speckit_task"
GRAPH_METADATA = "speckit_graph"
TASK_ID = re.compile(r"T[0-9]{3,}")
STORY_ID = re.compile(r"US[1-9][0-9]*")
PHASES = {"setup", "foundation", "story", "polish", "convergence"}


@dataclass(frozen=True)
class Task:
    """The identity and direct prerequisites of one planned task."""

    description: str
    dependencies: tuple[str, ...]
    phase: str | None = None
    story: str | None = None
    files: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()

    @property
    def metadata(self) -> dict[str, object]:
        """Return the task structure stored alongside the Beads issue."""
        return {"phase": self.phase, "story": self.story, "files": list(self.files),
                "requirements": list(self.requirements)}

    @property
    def fingerprint(self) -> str:
        """Bind the ID to the planned description independently of issue edits."""
        if self.phase is None:
            return hashlib.sha256(self.description.encode("utf-8")).hexdigest()
        return hash_json({"description": self.description, **self.metadata})


def hash_json(value: object) -> str:
    """Hash a canonical JSON value for comparison across invocations."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def read_graph(document: bytes) -> dict[str, Task]:
    """Parse and validate the complete task graph before opening Beads."""
    task_offsets = {offset: task_id for task_id, offset, _ in task_markers(document)}
    tasks: dict[str, Task] = {}
    offset = 0
    for line in document.splitlines(keepends=True):
        match = TASK_LINE.match(line)
        if match and (task_id := task_offsets.get(offset + match.start(1))):
            content = line[match.end():].strip()
            depends = DEPENDENCIES.search(content)
            if depends is None:
                raise ProjectionError(f"{task_id}: expected a final <!-- depends: ... --> comment")
            description = content[:depends.start()].strip().decode("utf-8")
            if not description or "<!-- depends:" in description:
                raise ProjectionError(f"{task_id}: expected a description and exactly one depends comment")
            entries = depends[1].decode("ascii")
            dependencies = () if entries == "none" else tuple(item.strip() for item in entries.split(","))
            if len(dependencies) != len(set(dependencies)):
                raise ProjectionError(f"{task_id}: duplicate dependency ID")
            tasks[task_id] = Task(description, dependencies)
        offset += len(line)

    return ordered_graph(tasks)


def ordered_graph(tasks: dict[str, Task]) -> dict[str, Task]:
    """Validate prerequisites and return the tasks in dependency order."""
    for task_id, task in tasks.items():
        for dependency in task.dependencies:
            if dependency not in tasks:
                raise ProjectionError(f"{task_id}: unknown dependency {dependency}")
    try:
        order = list(TopologicalSorter({key: task.dependencies for key, task in tasks.items()}).static_order())
    except CycleError as error:
        raise ProjectionError(f"Task dependency cycle: {' -> '.join(error.args[1])}") from error
    return {task_id: tasks[task_id] for task_id in order}


def bd_json(executable: str, directory: Path, args: list[str], body: str | None = None) -> object:
    """Run Beads with a fixed argument vector and optional UTF-8 stdin."""
    try:
        result = subprocess.run(
            [executable, *args, "--json"], cwd=directory, input=body,
            capture_output=True, encoding="utf-8", timeout=30,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise ProjectionError(f"Beads {args[0]} failed: {error}") from error

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProjectionError(f"Beads {args[0]} returned invalid JSON (exit {result.returncode})") from error
    if result.returncode:
        details = data.get("error") if isinstance(data, dict) else None
        raise ProjectionError(f"Beads {args[0]} failed (exit {result.returncode}): {details or 'no JSON error detail'}")
    return data


def find_issue(executable: str, directory: Path, reference: str, task: Task) -> str | None:
    """Resolve at most one compatible issue for a stable task reference."""
    entries = bd_json(executable, directory, [
        "list", "--all", "--external-ref", reference, "--limit", "2", "--brief", "--readonly",
    ])
    if not isinstance(entries, list):
        raise ProjectionError(f"Invalid Beads lookup result for {reference}")
    if not entries:
        return None
    if len(entries) != 1:
        raise ProjectionError(f"Multiple Beads issues found for {reference}")
    issue = entries[0]
    issue_id = issue.get("id") if isinstance(issue, dict) else None
    if not isinstance(issue_id, str) or not SAFE_BEADS_ID.fullmatch(issue_id):
        raise ProjectionError(f"Invalid Beads issue ID for {reference}")
    metadata = issue.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ProjectionError(f"Invalid Beads task metadata for {reference}")
    if task.phase and (not metadata or TASK_METADATA not in metadata):
        raise ProjectionError(f"{reference} is a legacy binding; reconcile it before using the Beads graph")
    if metadata and FINGERPRINT_KEY in metadata and metadata[FINGERPRINT_KEY] != task.fingerprint:
        raise ProjectionError(f"Task identity conflict for {reference} ({issue_id}): the planned description has changed")
    return issue_id


def write_with_metadata(
    executable: str, directory: Path, args: list[str], metadata: dict[str, object], body: str | None = None,
) -> object:
    """Pass structured metadata without exposing its contents to a Windows command shim."""
    path = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, prefix="skmeta-", suffix=".json",
                                delete=False) as temporary:
            path = Path(temporary.name)
            json.dump(metadata, temporary)
        return bd_json(executable, directory, [*args, "--metadata", f"@{path.name}"], body)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def read_dependencies(executable: str, directory: Path, issue_id: str) -> dict[str, str]:
    """Read the current direct dependencies of one issue, including non-blocking links."""
    entries = bd_json(executable, directory, ["dep", "list", issue_id, "--direction", "down", "--readonly"])
    if not isinstance(entries, list):
        raise ProjectionError(f"Invalid Beads dependency list for {issue_id}")
    dependencies: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ProjectionError(f"Invalid Beads dependency ID for {issue_id}")
        kind = entry.get("dependency_type")
        if not isinstance(kind, str):
            raise ProjectionError(f"Invalid Beads dependency type for {issue_id}")
        dependencies[entry["id"]] = kind
    return dependencies


def stable_issue_id(prefix: str, reference: str) -> str:
    """Derive an issue ID from the stable feature reference."""
    digest = hashlib.sha256(reference.encode("ascii")).hexdigest()[:20]
    return f"{prefix}-sk{digest}"


def workspace_prefix(executable: str, directory: Path) -> str:
    """Read the safe issue ID prefix of the selected Beads workspace."""
    workspace = bd_json(executable, directory, ["where", "--readonly"])
    prefix = workspace.get("prefix") if isinstance(workspace, dict) else None
    if not isinstance(prefix, str) or not SAFE_BEADS_ID.fullmatch(prefix):
        raise ProjectionError("Beads returned an invalid workspace prefix")
    return prefix


def create_issue(
    executable: str, directory: Path, feature: str, task_id: str,
    task: Task, prefix: str, dependencies: list[str],
) -> tuple[str, bool]:
    """Create an issue with its blockers, or reuse it after a concurrent import."""
    reference = f"spec/{feature}/{task_id}"
    issue_id = stable_issue_id(prefix, reference)
    args = [
        "create", f"Spec Kit {feature} {task_id}", "--id", issue_id, "--type", "task",
        "--external-ref", reference, "--stdin",
    ]
    if dependencies:
        args.extend(["--deps", ",".join(dependencies)])
    # Keep arbitrary Markdown out of the Windows command shim's arguments.
    try:
        if task.phase is None:
            result = bd_json(executable, directory, [
                *args, "--metadata", json.dumps({FINGERPRINT_KEY: task.fingerprint}, separators=(",", ":")),
            ], body=task.description)
        else:
            result = write_with_metadata(executable, directory, args, {
                FINGERPRINT_KEY: task.fingerprint, TASK_METADATA: task.metadata,
            }, body=task.description)
    except ProjectionError as error:
        if find_issue(executable, directory, reference, task) == issue_id:
            return issue_id, False
        raise ProjectionError(f"Could not register {reference}: {error}") from error
    if not isinstance(result, dict) or result.get("id") != issue_id:
        raise ProjectionError(f"Unexpected Beads creation result for {reference}; rerun to reconcile")
    return issue_id, True


def register(executable: str, directory: Path, feature: str, tasks: dict[str, Task]) -> tuple[int, int]:
    """Reuse existing issues and fill missing issues and blocking edges."""
    issue_ids = {
        task_id: find_issue(executable, directory, f"spec/{feature}/{task_id}", task)
        for task_id, task in tasks.items()
    }
    existing_edges: dict[str, dict[str, str]] = {}
    for task_id, task in tasks.items():
        issue_id = issue_ids[task_id]
        if issue_id and task.dependencies:
            edges = read_dependencies(executable, directory, issue_id)
            existing_edges[task_id] = edges
            for dependency in task.dependencies:
                target = issue_ids[dependency]
                if target and target in edges and edges[target] != "blocks":
                    raise ProjectionError(f"{task_id} already links to {dependency} with type {edges[target]}, expected blocks")

    prefix = workspace_prefix(executable, directory) if None in issue_ids.values() else ""

    created = 0
    added_edges = 0
    resolved: dict[str, str] = {}
    for task_id, task in tasks.items():
        dependencies = [resolved[dependency] for dependency in task.dependencies]
        issue_id = issue_ids[task_id]
        if issue_id is None:
            issue_id, was_created = create_issue(executable, directory, feature, task_id, task, prefix, dependencies)
            if was_created:
                created += 1
                added_edges += len(dependencies)
                resolved[task_id] = issue_id
                continue
            if dependencies:
                existing_edges[task_id] = read_dependencies(executable, directory, issue_id)
        for dependency in dependencies:
            edge = existing_edges.get(task_id, {}).get(dependency)
            if edge is None:
                bd_json(executable, directory, ["dep", "add", issue_id, dependency, "--type", "blocks"])
                added_edges += 1
            elif edge != "blocks":
                raise ProjectionError(f"{issue_id} already links to {dependency} with type {edge}, expected blocks")
        resolved[task_id] = issue_id
    return created, added_edges


def strings(value: object, field: str) -> tuple[str, ...]:
    """Validate a sequence of distinct nonempty strings."""
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() or item != item.strip() for item in value
    ):
        raise ProjectionError(f"{field} must contain nonempty strings")
    if len(set(value)) != len(value):
        raise ProjectionError(f"{field} contains duplicates")
    return tuple(value)


def graph_task(task_id: str, fields: dict[str, object]) -> Task:
    """Build one structured task from a proposed or stored Beads payload."""
    description = fields.get("description")
    phase = fields.get("phase")
    story = fields.get("story")
    if not isinstance(description, str) or not description.strip():
        raise ProjectionError(f"{task_id}: description is required")
    if not isinstance(phase, str) or phase not in PHASES:
        raise ProjectionError(f"{task_id}: invalid phase")
    if phase == "story":
        if not isinstance(story, str) or not STORY_ID.fullmatch(story):
            raise ProjectionError(f"{task_id}: story phase requires a USn story")
    elif story is not None:
        raise ProjectionError(f"{task_id}: use a null story outside the story phase")
    files = strings(fields.get("files"), f"{task_id} files")
    if not files or any(
        "\\" in filename or ":" in filename or filename.startswith("/") or
        any(part in {"", ".", ".."} for part in filename.split("/"))
        for filename in files
    ):
        raise ProjectionError(f"{task_id}: files must contain repository-relative paths")
    requirements = strings(fields.get("requirements"), f"{task_id} requirements")
    dependencies = strings(fields.get("dependencies"), f"{task_id} dependencies")
    if any(not TASK_ID.fullmatch(dependency) for dependency in dependencies):
        raise ProjectionError(f"{task_id}: invalid dependency ID")
    normalized_description = description.replace("\r\n", "\n").strip()
    return Task(normalized_description, dependencies, phase, story, files, requirements)


def proposed_graph(raw: object) -> dict[str, Task]:
    """Read a nonempty proposal from the task-generation command's JSON."""
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list) or not raw["tasks"]:
        raise ProjectionError("Expected a JSON object containing a nonempty tasks array")
    tasks: dict[str, Task] = {}
    for fields in raw["tasks"]:
        task_id = fields.get("id") if isinstance(fields, dict) else None
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
            raise ProjectionError("Every task requires a Txxx id")
        if task_id in tasks:
            raise ProjectionError(f"Duplicate task ID: {task_id}")
        tasks[task_id] = graph_task(task_id, fields)
    return tasks


def artifact_revisions(directory: Path) -> dict[str, str]:
    """Identify the exact feature inputs from which the graph is derived."""
    revisions = {"plan.md": hashlib.sha256((directory / "plan.md").read_bytes()).hexdigest()}
    for filename in ("spec.md", "requirements.sdoc", "architecture.sdoc", "verification.json"):
        artifact = directory / filename
        if artifact.is_file():
            revisions[filename] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return revisions


def feature_issues(executable: str, directory: Path, feature: str) -> dict[str, dict[str, object]]:
    """Read all tasks and the completion record for just one feature."""
    prefix = f"spec/{feature}/"
    rows = bd_json(executable, directory, ["list", "--all", "--external-contains", prefix,
                                          "--limit", "0", "--readonly"])
    if not isinstance(rows, list):
        raise ProjectionError("Beads returned an invalid feature issue list")
    issues: dict[str, dict[str, object]] = {}
    for row in rows:
        reference = row.get("external_ref") if isinstance(row, dict) else None
        if not isinstance(reference, str):
            raise ProjectionError("Beads returned an issue without an external reference")
        if reference.startswith(prefix):
            key = reference.removeprefix(prefix)
            if key == "graph" or TASK_ID.fullmatch(key):
                issue_id = row.get("id")
                if key in issues or not isinstance(issue_id, str) or not SAFE_BEADS_ID.fullmatch(issue_id):
                    raise ProjectionError(f"Duplicate or invalid Beads issue for {reference}")
                issues[key] = row
    return issues


def stored_graph(
    executable: str, directory: Path, issues: dict[str, dict[str, object]],
) -> tuple[dict[str, Task], list[dict[str, object]]]:
    """Reconstruct task data and the active dependency graph from Beads."""
    by_id = {issue["id"]: key for key, issue in issues.items() if key != "graph"}
    tasks: dict[str, Task] = {}
    result: list[dict[str, object]] = []
    for task_id, issue in sorted(issues.items()):
        if task_id == "graph":
            continue
        issue_id = str(issue["id"])
        metadata = issue.get("metadata")
        fields = metadata.get(TASK_METADATA) if isinstance(metadata, dict) else None
        if not isinstance(fields, dict):
            raise ProjectionError(f"{issue_id} is a legacy binding; reconcile it before using the Beads graph")
        blockers = [key for key, kind in read_dependencies(executable, directory, issue_id).items()
                    if kind == "blocks"]
        dependencies = sorted(by_id[key] for key in blockers if key in by_id)
        task = graph_task(task_id, {
            **fields, "description": issue.get("description"), "dependencies": dependencies,
        })
        fingerprint = metadata.get(FINGERPRINT_KEY) if isinstance(metadata, dict) else None
        if fingerprint != task.fingerprint:
            raise ProjectionError(f"{issue_id} changed its planned description or task metadata")
        tasks[task_id] = task
        result.append({
            "id": task_id, "beads_id": issue_id, "external_ref": issue["external_ref"],
            "status": issue.get("status"), "description": task.description, **task.metadata,
            "dependencies": dependencies, "blocking_beads_ids": blockers, "fingerprint": fingerprint,
        })
    return ordered_graph(tasks), result


def graph_digest(rows: list[dict[str, object]]) -> str:
    """Bind planned membership and internal edges independent of operational status."""
    return hash_json(sorted(
        [(str(row["id"]), row["fingerprint"], row["dependencies"]) for row in rows]
    ))


def graph_record(issues: dict[str, dict[str, object]]) -> dict[str, object]:
    """Read the last completed graph publication record."""
    metadata = issues.get("graph", {}).get("metadata")
    record = metadata.get(GRAPH_METADATA) if isinstance(metadata, dict) else None
    return record if isinstance(record, dict) else {}


def check_graph(
    executable: str, directory: Path, feature: str, revisions: dict[str, str],
    require_closed: bool = False,
) -> dict[str, object]:
    """Require a complete published graph for the current feature input bytes."""
    issues = feature_issues(executable, directory, feature)
    record = graph_record(issues)
    if record.get("artifact_revisions") != revisions:
        raise ProjectionError("No completed Beads graph for the current feature artifact revisions")
    _, rows = stored_graph(executable, directory, issues)
    if not rows or record.get("digest") != graph_digest(rows):
        raise ProjectionError("The Beads graph membership or blockers differ from the completed publication")
    remaining = [str(row["id"]) for row in rows if row["status"] != "closed"]
    if require_closed and remaining:
        raise ProjectionError(f"Beads still has unfinished feature tasks: {', '.join(remaining)}")
    return {"feature": feature, "plan_revision": revisions["plan.md"], "artifact_revisions": revisions,
            "tasks": rows}


def publish_graph(
    executable: str, directory: Path, feature: str, revisions: dict[str, str],
    proposal: dict[str, Task], append: bool,
) -> dict[str, object]:
    """Register the graph and seal it only after verifying the Beads copy."""
    issues = feature_issues(executable, directory, feature)
    original, rows = stored_graph(executable, directory, issues)
    record = graph_record(issues)
    if append:
        if any(task.phase != "convergence" for task in proposal.values()):
            raise ProjectionError("--append accepts convergence tasks only")
        # After an interrupted append, its proposed nodes may already exist.
        previous_rows = [row for row in rows if row["id"] not in proposal]
        if record.get("artifact_revisions") != revisions or record.get("digest") not in (
            graph_digest(rows), graph_digest(previous_rows),
        ):
            raise ProjectionError("Convergence requires a complete Beads graph for the current artifact revisions")
        tasks = ordered_graph({**original, **proposal})
    else:
        if original.keys() - proposal.keys():
            raise ProjectionError("The proposal omits existing Beads tasks; reconcile the plan before replacing it")
        tasks = ordered_graph(proposal)
    expected = graph_digest([
        {"id": key, "fingerprint": task.fingerprint, "dependencies": sorted(task.dependencies)}
        for key, task in tasks.items()
    ])
    for task_id, existing in original.items():
        if set(existing.dependencies) - set(tasks[task_id].dependencies):
            raise ProjectionError(f"{task_id} has additional Beads blockers; reconcile the plan and graph")
    register(executable, directory, feature, tasks)
    issues = feature_issues(executable, directory, feature)
    _, rows = stored_graph(executable, directory, issues)
    if expected != graph_digest(rows) or artifact_revisions(directory) != revisions:
        raise ProjectionError("The Beads graph or feature artifacts changed during registration; review and retry")
    completed = {"artifact_revisions": revisions, "digest": expected}
    if record != completed:
        metadata: dict[str, object] = {GRAPH_METADATA: completed}
        if "graph" in issues:
            write_with_metadata(executable, directory, ["update", str(issues["graph"]["id"])], metadata)
        else:
            # A closed record never appears as ready implementation work.
            reference = f"spec/{feature}/graph"
            issue_id = stable_issue_id(workspace_prefix(executable, directory), reference)
            args = ["create", f"Spec Kit {feature} graph", "--type", "epic",
                    "--id", issue_id, "--external-ref", reference,
                    "--status", "closed", "--stdin"]
            try:
                write_with_metadata(executable, directory, args, metadata,
                                    body="Completed Spec Kit task graph and bound artifact revisions.")
            except ProjectionError:
                # Another publisher may have sealed exactly this graph first.
                if graph_record(feature_issues(executable, directory, feature)) != completed:
                    raise
    return check_graph(executable, directory, feature, revisions)


def main(argv: list[str] | None = None) -> int:
    """Publish, check, or explicitly import a feature task graph."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path, help="Feature directory, or an annotated tasks.md for legacy import")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stdin", action="store_true", help="Publish a JSON graph read from stdin")
    mode.add_argument("--check", action="store_true", help="Check and print the published Beads graph as JSON")
    parser.add_argument("--append", action="store_true", help="Append convergence tasks with --stdin")
    parser.add_argument("--require-closed", action="store_true", help="Require every task to be closed with --check")
    arguments = parser.parse_args(argv)
    try:
        path = arguments.tasks.resolve()
        if arguments.append and not arguments.stdin:
            raise ProjectionError("--append requires --stdin")
        if arguments.require_closed and not arguments.check:
            raise ProjectionError("--require-closed requires --check")
        if arguments.stdin or arguments.check:
            feature_dir = FEATURE_PREFIX.match(path.name)
            if feature_dir is None or not path.is_dir():
                raise ProjectionError("Expected a numerically prefixed feature directory")
            revisions = artifact_revisions(path)
            feature_id = feature_dir[1]
            if arguments.stdin:
                try:
                    proposal = proposed_graph(json.load(sys.stdin))
                except json.JSONDecodeError as error:
                    raise ProjectionError(f"Invalid task graph JSON: {error}") from error
                result = publish_graph(beads_command(), path, feature_id, revisions, proposal, arguments.append)
            else:
                result = check_graph(beads_command(), path, feature_id, revisions, arguments.require_closed)
            print(json.dumps(result))
            return 0
        feature = FEATURE_PREFIX.match(path.parent.name)
        if path.name != "tasks.md" or feature is None:
            raise ProjectionError("Expected tasks.md inside a numerically prefixed feature directory")
        tasks = read_graph(path.read_bytes())
        created, edges = register(beads_command(), path.parent, feature[1], tasks)
    except (OSError, UnicodeError, ProjectionError) as error:
        print(f"Spec Kit registration error: {error}", file=sys.stderr)
        return 2
    print(f"Registered {len(tasks)} tasks: {created} created, {len(tasks) - created} reused, {edges} blockers added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
