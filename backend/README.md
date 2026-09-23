# Backend

## Coding Standards

Follow these conventions when working on the backend codebase:

- **Type hints**: Use type hints for function signatures, class attributes, and complex variables whenever practical.
- **PEP 8 naming**: Use `snake_case` for functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- **Docstrings**: Add docstrings to all public modules, classes, and functions to describe purpose, inputs, and outputs.
- **Imports**: Group standard library, third-party, and local imports separately, and keep imports ordered within each group.
- **Clarity over cleverness**: Prefer explicit, readable logic and meaningful names over terse constructs.

If you are unsure about an existing pattern, check nearby modules in `backend/` and follow the established style.

## Home Assistant App runtime

The standalone Home Assistant App compiles the packaged `system_config.yml`
with `/config/user_config.yml` on every start. Its startup service invokes:

```powershell
python backend/build_app_config.py --system <system.yml> --user <user.yml> --home-assistant-config <ha-location.json> --output <apps.yaml>
```

The App generates the location JSON from the current Home Assistant Core
configuration on every start; it contains latitude and longitude only. For
local compilation, provide a test fixture with those two numeric fields.
The default source paths remain available for local development after copying
`config/user_config.example.yml` to the ignored `config/user_config.yml`.
The generated `app_cfg.yaml` is also ignored. Explicit path arguments are for
the container boundary and do not change the generated `SafetyFunctions`
configuration contract.

Source configuration model version 2 builds a normalized installation registry
before generating component bindings. Packaged defaults are applied first,
`installation.component_settings` may override them for the whole installation, and one
room or opening may override its applicable values last. The compiler accepts
only explicit `user_config.model_version: 2`; missing, older, or unknown
versions fail before AppDaemon starts. Print the machine-readable contract with
`python backend/build_app_config.py --print-user-schema`. See
[`Configuration Model - Architecture.md`](<../docs/features/Configuration Model - Architecture.md>).
