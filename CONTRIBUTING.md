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

| Name | Codex role | Responsibility |
| --- | --- | --- |
| Irena | [`project_leader`](.codex/agents/project-leader.toml) | Coordinates dependencies, owners, and readiness across workstreams |
| Bożena | [`requirements_writer`](.codex/agents/requirements-writer.toml) | Traces requirements and makes acceptance criteria observable |
| Antek | [`system_architect`](.codex/agents/system-architect.toml) | Allocates safety responsibilities across components and dependencies |
| Ewa | [`software_architect`](.codex/agents/software-architect.toml) | Designs interfaces, data flows, and compatibility boundaries |
| Wiesiek | [`backend_engineer`](.codex/agents/backend-engineer.toml) | AppDaemon behavior, configuration, and backend tests |
| Miro | [`frontend_engineer`](.codex/agents/frontend-engineer.toml) | React UI, operator workflows, and frontend tests |
| Ola | [`ui_designer`](.codex/agents/ui-designer.toml) | Designs visual hierarchy, components, and accessible interaction states |
| Magda | [`ux_manager`](.codex/agents/ux-manager.toml) | Defines operator journeys and prioritizes usability findings |
| Kazek | [`safety_reviewer`](.codex/agents/safety-reviewer.toml) | Independently reviews safety behavior and test evidence |
| Zdzisława | [`safety_manager`](.codex/agents/safety-manager.toml) | Evaluates safety evidence and recommends readiness |
| Jurek | [`target_integration_tester`](.codex/agents/target-integration-tester.toml) | Checks end-to-end integration on an authorized deployment target |
| Basia | [`target_recovery_tester`](.codex/agents/target-recovery-tester.toml) | Checks degradation and recovery on an authorized deployment target |
| Hania | [`end_user_validator`](.codex/agents/end-user-validator.toml) | Walks through the finished product as a household operator |

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

- **Specify.** Ask `requirements_writer` to trace affected requirements and
  surface ambiguities. Involve `ux_manager` for operator-facing acceptance
  criteria and `safety_manager` for safety evidence needs.
- **Plan.** Ask the architects and relevant engineering roles to check
  component responsibilities, interfaces, compatibility, and test coverage.
  Involve `ui_designer` for visual interaction changes and the target testers
  for required deployment verification. Record decisions before plan review.
- **Tasks.** Use `project_leader` for cross-role dependencies and ownership
  when needed. Capture them in `tasks.md`. Mark tasks `[P]` only when they
  touch different files and have no dependencies on unfinished work.
- **Implement.** Assign tasks to the owning roles and run eligible `[P]`
  tasks together. The primary agent updates completion checkboxes in
  `tasks.md` after verifying each result. Have `safety_reviewer` independently
  review the combined diff for safety contract changes and report the outcome
  with verification results. Collect applicable target and operator evidence
  from the assigned testers and `end_user_validator`. Ask `safety_manager`
  for a readiness recommendation when the change affects a safety contract.

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
| Operator scenarios and acceptance criteria | `spec.md` |
| Design decisions, rationale, and interfaces | `plan.md`, `research.md`, or `contracts/` |
| Task dependencies, assigned roles, and progress | `tasks.md` |
| Reproducible verification scenarios | `quickstart.md` |
| Run evidence, open blockers, and readiness summary | Final report or the associated issue or PR when authorized |

### Target verification and acceptance

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
Zdzisława assesses the collected safety evidence. Human approval governs Spec
Kit review gates, live actions, and release decisions.

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
