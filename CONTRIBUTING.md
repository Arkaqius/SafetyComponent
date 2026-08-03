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
   - `backend/app_cfg.yaml`, code, and tests for current runtime evidence.
4. Ask before changing stable fault keys, Safety Mechanism IDs, MQTT topics,
   entity IDs, raw state codes, configuration contracts, or actuator behavior.

## Development setup

### Backend

Use Python 3.10 or newer from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
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

## Documentation changes

Normative documents state what the system shall do. Keep implementation status,
delivery phases, missing-provider notes, blockers, and review commentary in the
issue or pull request rather than HARA, SYS, SSRD, or feature requirements.

When a safety contract changes:

1. update HARA when the hazard, classification, or safety goal changes;
2. update SYS component allocation and traceability;
3. update SSRD and feature architecture as applicable;
4. update `backend/app_cfg.yaml` examples and schemas together when the
   deployable configuration contract changes;
5. update tests and README navigation;
6. verify every changed link, identifier, path, table, and command.

English is the source language for system, backend, requirements, and
architecture documents. The frontend operator README and UI use Polish.
User-facing runtime translations maintain English/Polish/German parity, while
technical IDs and raw state values remain language-independent.

## Local checks

Run backend checks from the repository root:

```powershell
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
git diff --check
```

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
intentional and do not mix generated artifacts, local environments, or unrelated
cleanup into the change.

## Conduct

Be respectful, discuss technical evidence rather than individuals, and treat
safety concerns as review inputs that require a concrete resolution or an
explicitly documented decision.
