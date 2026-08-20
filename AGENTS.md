# Project Agent Instructions

These instructions apply to the entire `SafetyComponent` repository. User and
system instructions take precedence. A nested `AGENTS.md`, if introduced later,
may add rules for its own directory but must not weaken the safety boundaries in
this file.

## Repository purpose

SafetyComponent is a Home Assistant safety-monitoring system composed of:

- an AppDaemon backend under `backend/`;
- a React/Vite frontend under `frontend/`;
- safety analysis and requirements under `docs/sys/`;
- feature architecture documents under `docs/features/`.

Contributor setup, issue/PR flow, and review expectations are defined in
`CONTRIBUTING.md`. Read it together with this file before changing the
repository.

Treat backend code, validated configuration, and automated tests as evidence of
implemented behavior. Treat HARA, SYS, SSRD, and feature architecture documents
as the normative description of required behavior.

## Required documentation workflow

Always use the `technical-documentation` skill when creating, restructuring, or
reviewing repository documentation, including `AGENTS.md`, `CONTRIBUTING.md`,
README files, HARA, SYS, SSRD, and feature architecture documents.

For documentation work:

1. Classify the task as build or review and use brownfield mode by default.
2. Inventory the affected documentation and governance surfaces before editing.
3. Verify implementation claims against current code,
   `backend/config/system_config.yml`, `backend/config/user_config.yml`, the
   generated `backend/app_cfg.yaml`, and relevant tests.
4. Preserve the existing docs-as-code layout unless a migration is explicitly
   requested.
5. Keep identifiers, requirements, links, examples, and configuration consistent
   across HARA, SYS, SSRD, feature documents, and README navigation.
6. Validate local links, Markdown tables, referenced paths, and commands after
   editing.
7. Report validation performed, remaining gaps, and language-parity status.

English is the source language for system, backend, requirements, architecture,
and contributor documentation. The frontend operator README and UI use Polish.
Maintain English/Polish/German parity for user-facing runtime translations.
Stable identifiers, paths, commands, and raw state codes remain
language-independent.

Normative safety documentation states what the system shall do. Do not put
development-phase commentary such as `Version 1`, `planned`, `not implemented`,
missing-provider notes, review blockers, or internal delivery problems into
requirements. Report implementation status separately in reviews, issues, or PR
descriptions.

BMAD is not part of this repository. Do not recreate BMAD directories, packages,
generated documents, workflows, or agent definitions unless the user explicitly
requests a new BMAD installation.

## Always

- Inspect `git status` and the relevant source, configuration, and tests before
  changing files.
- Preserve unrelated user changes and keep edits scoped to the requested task.
- Use `rg` or `rg --files` for repository discovery.
- Use `apply_patch` for manual file edits.
- Preserve stable runtime identifiers, MQTT topics, entity IDs, raw state codes,
  fault names, and requirement IDs unless a coordinated breaking change is
  explicitly approved.
- Keep user-facing Home Assistant names friendly and localized while retaining
  stable technical identifiers for contracts and diagnostics.
- Add or update automated tests when a code change affects a safety contract.
- Keep external API integrations isolated by provider. Each provider owns its
  schema, polling lifecycle, cache, health, and contract tests; household safety
  policy belongs to the relevant Safety Component.

## Ask first

- Changing or removing stable runtime identifiers or configuration contracts.
- Executing live Home Assistant actions, deployments, or actuator tests.
- Deleting data or directories that the user did not explicitly place in scope.
- Rewriting unrelated documentation or code outside the requested feature.

## Never

- Commit secrets, tokens, credentials, private keys, or production `.env` files.
- Treat stale, unavailable, malformed, or failed provider data as positive clear
  evidence for an active safety condition.
- Claim deployed or implemented behavior from documentation alone.
- Trigger household routines or safety actuators merely to verify documentation.
- Reintroduce BMAD as an implicit dependency.

## Backend standards

- Use Python 3.10+ and type hints for signatures, attributes, and complex values.
- Follow PEP 8 naming conventions.
- Add purpose-oriented docstrings to public modules, classes, and functions.
- Group and order standard-library, third-party, and local imports.
- Prefer explicit, readable safety logic over terse constructs.
- The backend tests use the bundled AppDaemon Hass stub under
  `backend/tests/appdaemon`.

## Validation commands

Run backend checks from the repository root:

```powershell
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
```

Run frontend checks from `frontend/`:

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
```

For documentation-only changes, also run:

```powershell
git diff --check
```

Verify every newly introduced relative link and referenced local path. Run the
full backend/frontend suites when documentation changes a runtime contract,
configuration example, test command, or implementation claim.

## Git and delivery

- Work on the current task branch unless the user requests another branch.
- Stage only files belonging to the requested change.
- Use concise, intentional commit messages.
- Push only when requested or when continuing an explicitly authorized publish
  workflow.
- Report the branch, commit, validation results, and any remaining gaps.
