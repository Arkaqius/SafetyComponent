---
name: "speckit-analyze"
description: "Review requirements, architecture, plan and Beads graph for inconsistencies."
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/analyze.md"
---

# Analyze feature consistency

If the workflow passes `SPECIFY_FEATURE_DIRECTORY=<path>`, set that environment variable for the resolver command and verify its returned path matches the explicit input.

Resolve the active feature with `python .specify/scripts/python/check_prerequisites.py --json`. Use its absolute `FEATURE_DIR`. Run `python tools/strictdoc_workflow.py architecture "<FEATURE_DIR>"` and `python tools/register_speckit_tasks.py "<FEATURE_DIR>" --check`. Stop and report an invalid or missing input.

Read `spec.md`, `plan.md`, `requirements.sdoc`, `architecture.sdoc`, relevant design contracts and the checked Beads graph. Review only. Find contradictory requirements, unallocated design decisions, orphan tasks, missing requirement coverage, and dependency or file ownership conflicts. Distinguish missing verification from missing implementation. Trace findings to requirement and Beads IDs and record the relevant input revisions. Prioritize findings that would permit unsafe behavior or make independent acceptance impossible. Report proposed resolutions and affected roles.
