# SafetyComponent for Home Assistant

SafetyComponent is an AppDaemon safety-monitoring application for Home
Assistant. It validates installation configuration, evaluates independent
safety mechanisms, aggregates symptoms into stable faults, publishes diagnostic
entities through MQTT, and coordinates notifications and supported recovery
actions.

## Capabilities

- Temperature monitoring for direct and forecast low/high conditions across
  configured rooms.
- Safety Doors monitoring with independent open-duration timeouts and optional
  condition gating for each door or gate.
- Fault aggregation, severity calculation, same-tag notification refresh, and
  explicit recovery confirmation.
- MQTT discovery, non-retained runtime state, availability, diagnostics, stale
  retained-state cleanup, and heartbeat publication.
- Localized Home Assistant presentation in English, Polish, and German while
  runtime IDs and raw state codes remain stable.
- SafetyHome React/Vite frontend with Dashboard, Temperature, Safety Doors, and
  History views connected through `@hakit/core`.

The repository also defines the safety contract and provider-isolated
architecture for External Hazard Monitoring: weather, official IMGW warnings,
outdoor air quality, and ionizing-radiation information correlated with
configured windows and external doors. That contract is notification-only and
permits no actuator calls.

The safety contract also defines Entity Health Monitoring for explicitly
configured safety dependencies, dependencies declared by Safety Components, and
an information-only inventory of other Home Assistant entities and devices.

## Repository layout

- `backend/SafetyFunctions.py` — AppDaemon application lifecycle and wiring.
- `backend/components/core` — EventBus, MQTT entities, localization, common
  types, and `DerivativeMonitor`.
- `backend/components/safetycomponents` — base safety framework plus
  `TemperatureComponent` and `SafetyDoorsComponent`.
- `backend/components/faults_manager` — fault catalog and symptom aggregation.
- `backend/components/notification_manager` — user notification lifecycle.
- `backend/components/recovery_manager` — supported recovery execution and
  confirmation.
- `backend/app_cfg.yaml` — annotated deployable configuration contract.
- `backend/tests` — isolated backend tests with the bundled AppDaemon Hass stub.
- `frontend` — SafetyHome React/Vite application.
- `docs/sys` — HARA, system requirements, and software safety requirements.
- `docs/features` — feature-level architecture documents.

Feature architecture documents include
[`External Hazard Monitoring`](docs/features/External%20Hazard%20Monitoring%20-%20Architecture.md)
and
[`Entity Health Monitoring`](docs/features/Entity%20Health%20Monitoring%20-%20Architecture.md).

## Backend quick start

Use Python 3.10 or newer:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
pytest backend/tests
```

Deploy the application by making `backend/SafetyFunctions.py` and
`backend/components/` available in the AppDaemon apps directory. Merge the
`SafetyFunctions` block from `backend/app_cfg.yaml` into AppDaemon `apps.yaml`,
then replace the installation-specific entity IDs and area IDs under
`user_config`.

After startup, verify that Home Assistant discovers
`sensor.safety_app_health` through MQTT and that it reports `running`.

## Configuration

`backend/app_cfg.yaml` separates:

- `app_config` — installation-independent policy, validation behavior,
  calibration, and the stable fault catalog;
- `user_config` — component enablement, Home Assistant entity/area bindings,
  localization, notification bindings, MQTT settings, and per-room/per-door
  calibration.

`config_version` must match the schema supported by the backend. Stable fault
keys, Safety Mechanism IDs, entity IDs, MQTT topics, and raw state codes are
machine contracts and require coordinated requirements, code, test, and
deployment changes.

## Frontend

SafetyHome requires the Node.js version declared in `frontend/.nvmrc` (Node 20):

```powershell
Set-Location frontend
nvm install 20
nvm use 20
npm ci
npm run dev
```

The frontend reads authenticated Home Assistant state through `@hakit/core`.
For mock mode, verification, static deployment, and secret-handling rules, see
the [frontend README](frontend/README.md).

## Documentation

- [Hazard analysis and risk assessment](<docs/sys/SafetyConcept - HARA.md>)
- [System safety architecture and requirements](<docs/sys/SafetyConcept - SYS.md>)
- [Software safety requirements](<docs/sys/SafetyComponent - SSRD.md>)
- [External Hazard Monitoring architecture](<docs/features/External Hazard Monitoring - Architecture.md>)
- [Backend coding standards](backend/README.md)
- [Contribution workflow](CONTRIBUTING.md)
- [Agent instructions](AGENTS.md)

System, backend, requirements, and architecture documents use English as the
technical source language. The frontend operator README and UI use Polish.
User-facing runtime text maintains English/Polish/German localization parity;
commands, paths, IDs, and raw state values remain language-independent.

## Verification

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Changes to
safety behavior, stable identifiers, configuration contracts, notification
semantics, or recovery actions require synchronized requirements and automated
regression tests.

## License and support

Distributed under the MIT License. Open a GitHub issue for defects, proposals,
or support questions.
