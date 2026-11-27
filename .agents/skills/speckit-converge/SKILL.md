---
name: "speckit-converge"
description: "Find unbuilt approved scope and register missing work in Beads."
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/converge.md"
---

# Register remaining approved work in Beads

If the workflow passes `SPECIFY_FEATURE_DIRECTORY=<path>`, set that environment variable for the resolver command and verify its returned path matches the explicit input.

Resolve the active feature with `python .specify/scripts/python/check_prerequisites.py --json`. Use its absolute `FEATURE_DIR`. Validate `python tools/strictdoc_workflow.py architecture "<FEATURE_DIR>"` and get the existing graph from `python tools/register_speckit_tasks.py "<FEATURE_DIR>" --check`. Stop and report an invalid or missing input.

Compare the approved requirements, ADRs, plan, contracts and graph against code and reproducible evidence. Remain read-only with respect to implementation. For each demonstrable gap, check whether an existing Beads task already covers it. Report proposed requirement or architecture changes for the corresponding approval stage.

When new work is needed within the approved scope, use the same JSON schema as `speckit-tasks` with `phase: "convergence"`, `story: null`, fresh task IDs after the highest existing ID, requirement UIDs, evidence, file paths and direct dependencies. Pass the JSON object through stdin to `python tools/register_speckit_tasks.py "<FEATURE_DIR>" --append --stdin`. Recheck the graph and report the new Beads IDs. If every gap is already covered, report the evidence and linked issues.
