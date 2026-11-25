---
name: "speckit-tasks"
description: "Register the approved feature's dependency graph directly in Beads."
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/tasks.md"
---

# Register the implementation graph in Beads

If the workflow passes `SPECIFY_FEATURE_DIRECTORY=<path>`, set that environment variable for the resolver command and verify its returned path matches the explicit input.

Use the approved feature in the current workflow. Run `python .specify/scripts/python/check_prerequisites.py --json` from the repository root and use its absolute `FEATURE_DIR`. Read the approved `spec.md`, `plan.md`, `requirements.sdoc`, `architecture.sdoc`, `verification.json`, and referenced contracts and scenarios. Before preparing tasks, run `python tools/strictdoc_workflow.py architecture "<FEATURE_DIR>" --verification-plan` and stop on failure. Cite the applicable case IDs in each verification task description.

Build the graph from the approved scope. Organize related work by story and phase, and include setup, foundation and final verification as applicable. Record exact repository-relative paths and referenced requirement UIDs. Include the observable completion criterion in each description. Preserve declared field constraints and order contract and safety regression tests before dependent implementation. Connect all direct prerequisites explicitly, including between phases. A ready task may run in parallel only when its files and write ownership are disjoint.

Use stable sequential IDs and submit one JSON object to `python tools/register_speckit_tasks.py "<FEATURE_DIR>" --stdin`. Pass JSON through stdin using a structured process call or a literal shell here-string. Keep Beads IDs, progress and dependency edges in Beads.

```json
{
  "tasks": [
    {
      "id": "T001",
      "phase": "story",
      "story": "US1",
      "description": "Verify the approved boundary with a deterministic clock",
      "files": ["backend/tests/test_heating_rules.py"],
      "requirements": ["SWR-HSM-018"],
      "dependencies": []
    }
  ]
}
```

Use phase values `setup`, `foundation`, `story` and `polish`, with `story: null` outside a story phase. Cite a requirement UID for work implementing or verifying a requirement. After successful registration run `python tools/register_speckit_tasks.py "<FEATURE_DIR>" --check`. Stop on any error. Retry interrupted registration with the same graph. Report Beads IDs, task and story counts, parallel opportunities and the smallest independently verifiable increment.
