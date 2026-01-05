# Safety Component for Home Assistant

This repository is dedicated to developing a Safety Component for the Home Assistant system. The component is designed to monitor, assess, and mitigate safety and security risks in a home environment. The repository includes documentation on hazard analysis, risk assessment, safety goals, and risk mitigation strategies for a wide range of potential hazards.

## Features
- AppDaemon app (`SafetyFunctions`) that manages safety mechanisms, faults, notifications, and recovery flows.
- Component framework for domain-specific safety logic (e.g., temperature monitoring).
- Configuration schema validation with strict mode and runtime entity checks.
- In-repo system documentation for safety concept and system requirements.

## Documentation
- `docs/sys/SafetyConcept - HARA.md`: hazard analysis and risk assessment.
- `docs/sys/SafetyConcept - SYS.md`: system-level safety concept.
- `docs/sys/SafetyComponent - SSRD.md`: system and software requirements.

## Installation
1. Create and activate a Python 3.10+ virtual environment.
2. Install backend dependencies:
   ```bash
   python -m pip install -r backend/requirements.txt
   ```
3. Deploy the AppDaemon app by pointing AppDaemon `apps_dir` to `backend/` or by copying `backend/SafetyFunctions.py` and `backend/components/` into your AppDaemon apps directory.

## Usage
1. Copy or merge `backend/app_cfg.yaml` into your AppDaemon `apps.yaml` (or set it as your AppDaemon config file).
2. Update entity IDs and room configuration under `user_config`.
3. Start AppDaemon and verify the health entity `sensor.safety_app_health` transitions to `running`.

## Configuration
Configuration is split into:
- `app_config`: instance-independent policy (fault catalog, strict validation, entity validation flags).
- `user_config`: house-specific entities, component enablement, and calibration.

See `backend/app_cfg.yaml` for a fully annotated example. The `config_version` value must match the supported version in code.

## Code Organization
Backend code is organized under `backend/components` by responsibility:
- `app_config_validator`: AppDaemon configuration schema + validation.
- `core`: Shared types/utilities (entities, enums, validation helpers).
- `faults_manager`: Fault catalog parsing and fault state management.
- `notification_manager`: Notification config + delivery logic.
- `recovery_manager`: Recovery execution flow.
- `safetycomponents`: Base safety component framework + concrete components.
  - `core`: `SafetyComponent`, `SafetyMechanism`, `DerivativeMonitor`.
  - `temperature`: `TemperatureComponent` + schema.

## Frontend
The `frontend/` directory contains a React + Vite UI (work in progress). It can be developed and built independently from the backend.
- Local dev: follow `frontend/README.md` for Node.js/NVM requirements and `npm run dev`.
- Build: `npm run build` from `frontend/`.
- Deployment: optional SSH deploy script described in `frontend/README.md`.

## Testing
Automated tests are maintained under `backend/tests` and rely on the in-repo AppDaemon Hass stub for isolation. To run the full test suite:

1. Create and activate a Python 3.10+ virtual environment.
2. Install test dependencies (pytest and any project requirements) in that environment.
3. From the repository root, execute:

   ```bash
   pytest backend/tests
   ```

Recent validation: the suite was exercised locally via `pytest backend/tests`.

## Contributing
We appreciate your contributions! Please feel free to submit pull requests, create issues, and contribute to discussions.

## Fork the Project
Create your Feature Branch (git checkout -b feature/AmazingFeature)
Commit your Changes (git commit -m 'Add some AmazingFeature')
Push to the Branch (git push origin feature/AmazingFeature)
Open a Pull Request

## License
Distributed under the MIT License. See LICENSE for more information.

## Contact
Open a GitHub issue for questions or support.



## Acknowledgments
We would like to express our gratitude to the community for their continuous support and valuable feedback. This project wouldn't be where it is today without your help.
