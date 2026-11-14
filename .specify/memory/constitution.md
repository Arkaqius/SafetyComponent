<!--
Sync Impact Report (temporary review material; remove before committing)
Version change: unratified scaffold -> 1.0.0 (initial adoption)
Modified principles: replaced the five unnamed scaffold slots with:
  I. Documentation Before Implementation
  II. Typed and Documented Python
  III. Verification Before Deployment
  IV. Scoped Instructions and Frontend Standards
  V. Explicit Safety Contracts
Added sections: Documentation and Repository Boundaries;
  Development Workflow and Quality Gates; concrete Governance rules.
Removed sections: none; illustrative scaffold comments removed.
Deferred TODOs: none.
Scope: constitution only; dependent templates and commands are unchanged.
-->

# SafetyComponent Constitution

## Core Principles

### I. Documentation Before Implementation

Contributors MUST document the intended behavior and acceptance criteria before
implementing a behavior change. Product requirements and architecture MUST live
under `docs/`: hazard analysis and system/software requirements in `docs/sys/`,
feature contracts in `docs/features/`, and supporting references and examples in
their existing directories. Changes MUST update the affected HARA, SYS, SSRD,
and feature contracts before implementation, preserving traceability from the
requirement to configuration, code, and verification evidence.

Normative documents MUST describe required behavior without delivery-phase
commentary. Implementation status and gaps MUST be reported separately in issues,
reviews, or pull requests. Documentation alone MUST NOT be presented as evidence
that behavior is implemented or deployed. This separation keeps safety intent
reviewable before code changes and prevents unsupported operational claims.

### II. Typed and Documented Python

Backend changes MUST use Python 3.10 or newer, type hints for function signatures,
class attributes, and complex values, and purpose-oriented docstrings for public
modules, classes, and functions. Contributors MUST follow PEP 8 naming, group
standard-library, third-party, and local imports, and prefer explicit safety logic.

Backend changes MUST pass Ruff and mypy using the repository configuration.
Contributors MUST include new typed backend modules in the configured mypy scope
and extend coverage to changed legacy modules as their boundaries gain explicit
types. They MUST NOT remove modules or weaken checks to conceal new failures.
The configured scope in `mypy.ini` MUST be reported accurately; a passing scoped
check MUST NOT be described as verification of the entire backend. Types and
docstrings make safety assumptions explicit and support automated review.

### III. Verification Before Deployment

Every change MUST be verified before deployment. Behavior changes MUST have
automated tests appropriate to the affected contract; safety-contract changes and
defect fixes MUST include regression tests. Provider schemas, configuration
boundaries, failure handling, and frontend consumption MUST receive contract or
integration coverage when affected. Backend tests MUST use the bundled AppDaemon
Hass stub for local verification rather than requiring a live household.

Required checks MUST pass for the change, and reviewers MUST receive the commands,
results, and unresolved limitations. Failures affecting the change MUST block
deployment. Unrelated baseline failures MUST be recorded and assessed explicitly;
they MUST NOT be silently treated as successful verification. Documentation-only
changes MUST pass whitespace, link, path, table, and command validation as applicable.
Deployment, live Home Assistant actions, and actuator tests MUST require explicit
user authorization, even after local checks pass.

### IV. Scoped Instructions and Frontend Standards

Before editing, contributors MUST read the root [agent instructions](../../AGENTS.md),
the [contribution guide](../../CONTRIBUTING.md), and any applicable nested
`AGENTS.md`. A nested instruction file MUST add directory-specific guidance without
weakening repository safety boundaries. Contributors MUST inspect the relevant
source, configuration, and tests and preserve unrelated work.

Frontend changes MUST follow the frontend's React, TypeScript, and Vite stack,
strict TypeScript configuration, package scripts, Node.js version declared in
`frontend/.nvmrc`, and [frontend guidance](../../frontend/README.md). Frontend
verification MUST include tests, type checking, ESLint, Prettier, and the production
build; changes affecting browser behavior MUST also exercise the relevant mock
Playwright regressions. Frontend rules MUST be derived from its actual stack and
applicable instruction files rather than applying Python tooling to frontend code.

### V. Explicit Safety Contracts

Contributors MUST preserve requirement IDs, fault names, Safety Mechanism IDs,
MQTT topics, entity IDs, raw state codes, and configuration contracts unless the
user explicitly approves a coordinated breaking change. Approved contract changes
MUST synchronize requirements, configuration, implementation, tests, and migration
instructions before deployment.

Stale, unavailable, malformed, or failed provider data MUST NOT constitute positive
clear evidence for an active safety condition. External integrations MUST remain
isolated by provider: each provider owns its schema, polling lifecycle, cache,
health, and contract tests; the owning Safety Component makes household safety
decisions. Friendly localized names MUST remain separate from stable technical
identifiers. These boundaries prevent integration failures and presentation changes
from silently altering safety policy.

## Documentation and Repository Boundaries

- The [hazard analysis](<../../docs/sys/SafetyConcept - HARA.md>),
  [system requirements](<../../docs/sys/SafetyConcept - SYS.md>),
  [software requirements](<../../docs/sys/SafetyComponent - SSRD.md>), and
  `docs/features/` define required safety behavior. Current source, validated
  configuration, and tests provide implementation evidence.
- Evidence reviews MUST inspect `backend/config/system_config.yml`,
  `backend/config/user_config.example.yml`, and any applicable local ignored
  installation configuration without publishing private values.
- The existing docs-as-code layout MUST be preserved. Root and module READMEs
  remain entry points and operator guides; `.specify/` holds Spec Kit governance
  and workflow artifacts rather than replacing product documentation in `docs/`.
- System, backend, requirements, architecture, and contributor documentation MUST
  use English. The frontend operator README and UI MUST use Polish. User-facing
  runtime translations MUST maintain English/Polish/German parity. Paths,
  commands, identifiers, and raw state codes MUST remain language-independent.
- Documentation work MUST use the `technical-documentation` skill, default to
  brownfield mode, and validate changed links, paths, tables, examples, and
  commands. Runtime contract changes MUST remain consistent across requirements,
  architecture, configuration, and README navigation.
- Secrets, tokens, credentials, private keys, production `.env` files, and
  installation-owned configuration MUST NOT be committed. Out-of-scope data or
  directory deletion MUST require explicit authorization. BMAD MUST NOT be
  introduced unless the user explicitly requests a new installation.

## Development Workflow and Quality Gates

1. Inspect Git status and the applicable instructions. Identify the issue or
   change request, controlling requirements, affected configuration, and tests.
   Work on the current task branch unless the user requests another branch.
2. Update the affected documents first. Define acceptance criteria, safety and
   configuration impacts, stable identifiers, and verification evidence needed.
3. Implement the documented scope and add or update the required automated tests.
   Preserve unrelated user changes and use repository conventions.
4. Run the applicable [local checks](../../CONTRIBUTING.md#local-checks).
   Backend work MUST pass Ruff, scoped mypy, pytest, and coverage checks from the
   repository root. Frontend work MUST pass the checks in Principle IV from
   `frontend/`. Cross-layer contract changes MUST pass both suites.
5. Documentation-only work MUST run `git diff --check` and validate every newly
   introduced relative link and local path. Changes to a runtime contract,
   configuration example, test command, or implementation claim MUST also run the
   full backend and frontend suites required by the root agent instructions.
6. Before deployment, review compliance and record the branch, commit when
   created, changed contracts, validation results, remaining gaps, and language
   parity. Push only when requested or within an explicitly authorized publishing
   workflow. Obtain explicit authorization for deployment or live actions.

## Governance

This constitution defines project-wide development principles. The root
`AGENTS.md` and `CONTRIBUTING.md` supply operational guidance, and applicable
nested instructions refine it for their directories. Contributors MUST apply
these documents together. Conflicts MUST be surfaced and resolved explicitly;
they MUST NOT be used to weaken safety boundaries or bypass user authorization.

Every plan, implementation review, and pull request MUST check compliance with
the principles and applicable quality gates. Any proposed exception MUST identify
the affected rule, rationale, safety impact, verification evidence, and remediation
or migration plan, and MUST receive explicit maintainer approval before acceptance.
An exception MUST NOT bypass user authorization or the prohibition on using
unreliable data as positive clear evidence.

Amendments MUST state the proposed rule changes, rationale, affected workflows,
and migration impact, receive maintainer approval, and update this file's version
and amendment date. Related guidance MUST be reviewed for consistency; any required
follow-up MUST be tracked explicitly rather than silently modifying unrelated
artifacts. Use semantic versioning: MAJOR for incompatible principle removals or
redefinitions, MINOR for new principles or materially expanded guidance, and PATCH
for clarifications without a semantic change. Preserve the original ratification
date and use ISO dates for all governance metadata.

**Version**: 1.0.0 | **Ratified**: 2026-11-12 | **Last Amended**: 2026-11-12
