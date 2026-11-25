# Contributing to SafetyComponent

SafetyComponent changes can affect household safety decisions. Keep each change
small, traceable, and verifiable against the current code, configuration, tests,
and safety requirements.

Automated agents must also follow [AGENTS.md](AGENTS.md). Documentation work by
an agent must use the `technical-documentation` skill in brownfield mode.

## Before changing the repository

1. Open or reference an issue that states the observed behavior, desired safety
   contract, and affected installation surfaces.
2. Inspect `git status` and preserve unrelated work.
3. Identify the controlling documents and implementation evidence:
   - HARA for hazards and safety goals;
   - SYS for system/component requirements;
   - SSRD for software requirements;
   - feature architecture for detailed component/provider contracts;
   - `backend/config/system_config.yml`, `backend/config/user_config.example.yml`,
     any local ignored generated configuration, code, and tests for runtime
     evidence.
4. Ask before changing stable fault keys, Safety Mechanism IDs, MQTT topics,
   entity IDs, raw state codes, configuration contracts, or actuator behavior.

## Development setup

### Backend

Use Python 3.10 or newer from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
```

### Frontend

Use the Node.js version in `frontend/.nvmrc`:

```powershell
Set-Location frontend
nvm install 20
nvm use 20
npm ci
```

Do not commit `.env` files, Home Assistant tokens, SSH credentials, private
keys, or deployment secrets.

## Making changes

- Create a focused branch such as `feature/<topic>`, `fix/<topic>`, or
  `docs/<topic>`.
- Follow existing backend and frontend patterns; avoid unrelated refactors.
- Add regression tests for every defect or behavior change that affects a
  safety contract.
- Keep external API providers isolated. Provider adapters normalize data and
  health; the owning Safety Component makes household safety decisions.
- Do not treat stale, malformed, unavailable, or failed provider input as
  positive clear evidence.
- Do not deploy to Home Assistant, call household actuators, or manually trigger
  household routines as part of local verification without explicit approval.

## Working with Codex subagents

Codex loads the project roles from [.codex/agents](.codex/agents) in a
trusted workspace. The primary agent assigns work to the roles the task needs.
See [Codex subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents).

| Name | Job title | Codex role | Responsibility |
| --- | --- | --- | --- |
| Irena | Project Lead | [`project_leader`](.codex/agents/project-leader.toml) | Coordinates workstream owners and dependencies and reports readiness for the current stage. |
| Kaśka | AR (AiResources) | [`ai_resources`](.codex/agents/ai-resources.toml) | Maintains the agent roster and role responsibilities, reviews how agents work together, and facilitates onboarding and introductions. |
| Jurand | AI Workflow & Harness Engineer | [`ai_harness_engineer`](.codex/agents/ai-harness-engineer.toml) | Maintains AI workflows and their execution tooling, including orchestration, approval gates, handoffs, and verification. |
| Bożena | Safety Requirements Writer | [`requirements_writer`](.codex/agents/requirements-writer.toml) | Traces safety requirements through related documents and defines observable acceptance criteria. |
| Antek | Safety System Architect | [`system_architect`](.codex/agents/system-architect.toml) | Assigns safety responsibilities across components and defines how faults affect their dependencies. |
| Ewa | Software Architect | [`software_architect`](.codex/agents/software-architect.toml) | Designs software interfaces and data flows and identifies compatibility and integration checks. |
| Wiesiek | Backend Engineer | [`backend_engineer`](.codex/agents/backend-engineer.toml) | Implements and tests AppDaemon behavior, configuration, and provider integrations. |
| Miro | Frontend Engineer | [`frontend_engineer`](.codex/agents/frontend-engineer.toml) | Implements and tests the React UI, operator workflows, and their integration with the backend. |
| Ola | UI Designer | [`ui_designer`](.codex/agents/ui-designer.toml) | Designs accessible components, visual hierarchy, and how the UI presents alarms and degraded states. |
| Magda | UX Manager | [`ux_manager`](.codex/agents/ux-manager.toml) | Defines operator journeys and usability criteria and prioritizes findings by operator impact. |
| Kazek | Independent Safety Reviewer | [`safety_reviewer`](.codex/agents/safety-reviewer.toml) | Reviews changes for safety regressions and checks whether tests cover failure and recovery paths. |
| Jurek | Target Integration Tester | [`target_integration_tester`](.codex/agents/target-integration-tester.toml) | Verifies the assigned build and follows end-to-end behavior on an authorized deployment target. |
| Basia | Target Recovery Tester | [`target_recovery_tester`](.codex/agents/target-recovery-tester.toml) | Verifies degradation and recovery on an authorized isolated target and checks that the agreed baseline is restored. |
| Hania | End-User Validator | [`end_user_validator`](.codex/agents/end-user-validator.toml) | Simulates household operator tasks in an approved preview or test environment and records where the UI is unclear. |

When using Agent Mail for local handoffs, include the roster name, job title,
and Codex role ID at the start of the mailbox profile's `task_description`,
followed by the current task. For example, use
`Wiesiek — Backend Engineer (backend_engineer). Investigate SQLite write contention.`
Reuse the existing mailbox for that role in the local Agent Mail project so
earlier handoffs remain accessible.

1. The primary agent assigns each subagent an outcome, files it may edit, and
   the checks or evidence expected. Give each file one writer at a time.
   Run independent tasks in parallel and sequence tasks that depend on a
   shared contract or another agent's changes.
2. Subagents send decisions, contract dependencies, and blockers to the
   primary agent as they arise. The primary agent forwards each update to the
   affected roles and resolves conflicting assumptions before dependent edits
   continue. For example, the backend engineer supplies the confirmed payload
   shape and state codes before the frontend engineer integrates them.
3. Each subagent returns changed paths or findings, relevant requirement IDs,
   verification results, and open questions. For changes affecting a safety
   contract, commission a safety review of the combined diff. The primary
   agent routes findings back to the responsible role, verifies the combined
   result, and reports remaining gaps.

### Using subagents with Spec Kit

The [Spec Kit workflow](.specify/workflows/speckit/workflow.yml) runs
`specify → plan → tasks → implement`, with approval gates after `specify` and
`plan`. The primary agent delegates work within each stage and uses each
stage's artifact as the handoff to the next.

Pass the feature directory explicitly when starting a run. Use an unused
feature number for a new feature.

```powershell
specify workflow run speckit --input 'feature_directory=docs/features/005-example' --input 'spec=Describe the desired behavior'
```

Deterministic checks validate the StrictDoc files before review, pin the
reviewed artifact revisions across approvals, and verify the Beads graph
before implementation and at completion.

| Gate | Executable check | Human review |
| --- | --- | --- |
| Requirements decomposition | Validate StrictDoc fields, kinds, UIDs, stakeholder and HARA links, and SYS-to-SW allocation. | Review scope, completeness, measurable acceptance and the suitability of the allocation. |
| Planning | Validate the approved requirements revision, ADR links and verification coverage. Bind the plan, design artifacts and verification plan to the approved revision. | Review interfaces, architectural decisions, case expectations and target conditions. |
| Dispatch and completion | Verify the published Beads graph against the approved feature artifacts, then require its tasks to be closed at completion. | Review acceptance evidence and unresolved issues for the change. |

- **Specify.** Ask `requirements_writer` to author and trace requirements in
  `requirements.sdoc` and surface ambiguities. Use `spec.md` for scope, scenarios
  and requirement references. Involve `ux_manager` for operator-facing acceptance
  criteria and ask the system architect to identify the evidence required for
  affected safety goals.
- **Plan.** Ask the architects and relevant engineering roles to check
  component responsibilities, interfaces, compatibility, and test coverage.
  Involve `ui_designer` for visual interaction changes and the target testers
  for required deployment verification. Record ADRs in `architecture.sdoc`
  and reference their UIDs in the plan before plan review.
- **Tasks.** Irena identifies independently testable work and its prerequisites.
  The Spec Kit tasks stage registers the generated work and its blocking
  dependencies directly in Beads. Run work in parallel when the graph marks it
  ready and the tasks touch disjoint files.
- **Implement.** Select ready work in Beads that belongs to the current stage.
  Run eligible tasks together and record their verified status in Beads.
  Have `safety_reviewer` independently
  review the combined diff for safety contract changes and report the outcome
  with verification results. Collect applicable target and operator evidence
  from the assigned testers and `end_user_validator`. For a change affecting a
  safety contract, have Irena collect the evidence and Kazek's findings for
  the human release decision.

[GitHub Actions](.github/workflows/safety-component-app.yml) runs the
repository's CI checks. The Codex session coordinates subagents and resolves
their findings during the feature workflow.

### Sharing decisions and evidence

Send handoffs through the primary agent with the task or requirement ID,
decision or blocker, evidence reference, affected roles, and next action.
The receiving role checks the linked artifact before acting. The primary agent
or assigned artifact owner records decisions needed in later sessions in the
current feature's Spec Kit artifacts:

| Information | Where to record it |
| --- | --- |
| Scope and operator scenarios | `spec.md` with requirement UID references |
| Stakeholder, SYS and SW requirements and acceptance criteria | `requirements.sdoc` |
| Architectural decisions and rationale | `architecture.sdoc` |
| Design interfaces and implementation strategy | `plan.md` and `contracts/` with ADR references |
| Task decomposition, dependencies, owners, blockers, completion and evidence references | Beads issues and dependency edges |
| Role-to-role findings, acknowledgements and requests for a decision | Project Agent Mail thread keyed by Beads issue ID |
| Reproducible verification scenarios | `quickstart.md` |
| Run evidence, open blockers, and readiness summary | Final report or the associated issue or PR when authorized |

Give each independent role a fresh conversation with the assignment, input
revision, relevant requirement IDs, permitted files, expected output and
recipient. With Codex delegation use `fork_turns="none"` for this assignment.
The workspace and tools are shared. Use one writer per file and keep peer
opinions and implementation proposals out of the initial acceptance brief.
Give the tester the approved requirement, operating conditions and observable
interface. Have the tester record the expected result and a counterexample
before inspecting the patch. The author can share implementation details for
diagnosis after that first assessment. Preserve differing assessments with their
evidence until the responsible specialist resolves them or identifies a decision
for the human approver.

Use the Beads issue ID as the Agent Mail `thread_id` and prefix the subject
with that ID in brackets. Address the role that must act and copy the
coordinator when a dependency or decision affects another task. Write findings
in the first person. Include the requirement and artifact revision, what you
observed, what you conclude, supporting evidence, uncertainty and the requested
next action. Request an acknowledgement when another role depends on the
handoff. On resumption, read the assigned issue and its thread before acting.
For a result consumed by another role, the coordinator checks the message
ID, linked evidence and the recipient's response before marking the handoff
complete. If Mail is unavailable, relay the same fields in the session and
record the delivery method in Beads so the next session can recover the result.
An acknowledgement records receipt. Record a human gate decision separately
with its outcome and the artifact revision it covers.

For example, a heating verification handoff from Basia to Wiesiek could read:

> **[issue ID] T019 · FR-005 · changed target**
>
> I derived the deadline from FR-005 at the attached spec revision. At the
> original deadline the room was still below the new target. I observed a
> pending decision in the local fixture. I attached the timestamps and the
> failing assertion. Wiesiek, please investigate the decision at that boundary.

In an actual message replace the issue ID and attach or link the cited
revision and evidence. Keep the raw discussion in the thread. Forward the
conclusion and the artifact reference to roles that need the result.

### Validating requirements and architecture

Install StrictDoc in the development environment and run the same checks used
by the specification and planning stages. Substitute the active feature path.

```powershell
python -m pip install -r tools/requirements-strictdoc.txt
python tools/strictdoc_workflow.py requirements docs/features/<feature>
python tools/strictdoc_workflow.py architecture docs/features/<feature>
```

Use the [requirements](.specify/templates/overrides/strictdoc-requirements.sdoc)
and [ADR](.specify/templates/overrides/strictdoc-architecture.sdoc) examples.
Preserve published IDs when adopting an existing requirement. Review the
feature brief and requirements together, then review the plan and ADRs together.
Legacy features may still use their original Markdown artifacts. Reconcile
their requirement IDs and task evidence during explicit adoption of the new flow.

### Planning verification

Write `verification.json` in the feature directory before plan approval.
Give each case a stable ID, the requirement UIDs it verifies, its method
and the expected result. Cover each stakeholder requirement with a
`stakeholder` case, each SYS requirement with a `system` case, and each SW
requirement with at least one `static`, `unit` or `integration` case.
A requirement can have additional cases. Record case procedures, inputs
and authorized target conditions in `quickstart.md`.

```json
{
  "cases": [
    {
      "id": "HSM-SYS-TIME-001",
      "requirements": ["SYS-SR-HSM-012"],
      "method": "system",
      "expected": "For an allocated supervision failure, HA accepts the notification within 60 seconds."
    }
  ]
}
```

The planning guard checks case IDs, requirement references, method
compatibility and expected results. It checks the planned coverage.
Record observed results separately after executing the relevant checks.

### Executing Spec Kit tasks with Beads

After plan approval, `speckit-tasks` passes a graph through standard input to
the [registrar](tools/register_speckit_tasks.py). It validates the graph and
registers each task with a stable external reference such as `spec/003/T019`.
Keep task numbers stable and retry interrupted registration with the same
graph. Review the graph before dispatch and resolve binding conflicts in Beads.

```powershell
python tools/register_speckit_tasks.py docs/features/<feature> --check
```

The check confirms that the graph matches the current approved inputs before
implementation. Treat previously written task lists as migration inputs.
Consult Beads for work state and handoffs after migration.

Use `bd ready` to select work, `bd show <id>` to read its contract, and
`bd update <id> --claim` as the assigned role with its own Beads actor.
If a new blocker appears, record its issue and edge and notify the dependent
role. Close verified work with `bd close <id> --reason "<outcome and evidence reference>"`.

For a bug against an existing contract, open a Beads bug with the requirement,
symptom, affected revision and reproduction conditions. Have an independent
role derive the expected result, then reproduce the failure locally. Hand
the evidence to the implementer. Verify the fix against the original case
and relevant regressions and attach the evidence to the issue before closure.
If triage reveals a change to required behavior, return that decision to the
Spec Kit specification and plan review gates. A standalone bug can use its
Beads ID directly as its mail thread.

### Target verification and acceptance

Follow the [release workflow](docs/RELEASE_WORKFLOW.md) from candidate checks
through isolated target verification, household promotion and post-deploy
verification.

Use the [Home Assistant App verification runbook](safety_component/DOCS.md#verification)
for target smoke checks and its [backup and recovery procedure](safety_component/DOCS.md#backup-and-recovery)
for recovery scenarios. Follow the [approval rules](AGENTS.md#ask-first).
Prepare scenarios before target access and confirm the exact build, target, and
allowed actions before running approved checks. Use an isolated test target for
fault injection or restart exercises. Record the target alias, build, scenario
or requirement ID, expected and observed outcomes, and redacted evidence.
Report checks as pass, fail, or blocked and identify the environment used.

Hania validates the finished workflow in an approved preview or test environment
and reports simulated operator acceptance separately from human acceptance.
Irena collects the safety evidence and Kazek independently reviews it. Human
approval governs Spec Kit review gates, live actions, and release decisions.

## Documentation changes

Normative documents state what the system shall do. Keep implementation status,
delivery phases, missing-provider notes, blockers, and review commentary in the
issue or pull request rather than HARA, SYS, SSRD, or feature requirements.

When a safety contract changes:

1. update HARA when the hazard, classification, or safety goal changes;
2. update SYS component allocation and traceability;
3. update SSRD and feature architecture as applicable;
4. update the public system configuration, installation example, compiler,
   and schemas together when the deployable contract changes;
5. update tests and README navigation;
6. verify every changed link, identifier, path, table, and command.

English is the source language for system, backend, requirements, and
architecture documents. The frontend operator README and UI use Polish.
User-facing runtime translations maintain English/Polish/German parity, while
technical IDs and raw state values remain language-independent.

## Local checks

Run backend checks from the repository root:

```powershell
python -m ruff check backend
python -m mypy
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
git diff --check
```

Ruff checks backend and test code for correctness issues and selected PEP 8
rules. Mypy initially checks the typed configuration compiler and source
schemas listed in `mypy.ini`; expand this scope as legacy AppDaemon boundaries
gain explicit types. Both checks run in the backend CI job before the tests.

Run frontend checks from `frontend/`:

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
```

Do not rewrite unrelated files solely to fix a repository-wide baseline warning.
If an unchanged baseline check fails, record the exact failure in the pull
request and ensure the changed files introduce no additional failure.

## Pull requests

A pull request should include:

- the safety/user outcome and scope;
- affected requirement and runtime IDs;
- configuration or migration impact;
- tests and documentation checks executed, with exact results;
- any remaining implementation gap or deployment verification still required;
- screenshots only when a visible frontend change needs them.

Reviewers should be able to trace a behavior change from hazard or requirement
through configuration, implementation, and automated evidence. Keep commits
intentional and do not commit installation-owned `user_config.yml`, generated
`app_cfg.yaml`, local environments, or unrelated cleanup.

## Conduct

Be respectful, discuss technical evidence rather than individuals, and treat
safety concerns as review inputs that require a concrete resolution or an
explicitly documented decision.
