# Backend

## Coding Standards

Follow these conventions when working on the backend codebase:

- **Type hints**: Use type hints for function signatures, class attributes, and complex variables whenever practical.
- **PEP 8 naming**: Use `snake_case` for functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- **Docstrings**: Add docstrings to all public modules, classes, and functions to describe purpose, inputs, and outputs.
- **Imports**: Group standard library, third-party, and local imports separately, and keep imports ordered within each group.
- **Clarity over cleverness**: Prefer explicit, readable logic and meaningful names over terse constructs.

If you are unsure about an existing pattern, check nearby modules in `backend/` and follow the established style.

Install `backend/requirements-dev.txt` for local checks. From the repository
root, run `python -m ruff check backend` for selected PEP 8 and correctness
rules, and `python -m mypy` for the configuration compiler and source schemas
currently listed in `mypy.ini`. The checks run in CI alongside backend tests;
newly typed modules can be added to the mypy scope incrementally.

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

## Runtime state storage

The runtime stores notification, recovery, fault evidence, internal detector,
periodic-test, detector-test, and battery-fault retirement state in a shared
SQLite database outside the deployed image. The default is
`/config/appdaemon/safety_state.sqlite3`.
Existing JSON state paths remain one-time import inputs; they are not
dual-written after import. Store transactions and health contributors remain
independent. See [Runtime State Storage](<../docs/features/Runtime State Storage - Architecture.md>)
for schema ownership, migration, failure handling, and stopped-App copying.

## MQTT retained-message migration

### Diagnostic fault and monitor timing migration

Component input diagnostics use one `InputMonitoringUnavailable` fault. It
replaces `TemperatureMonitoringUnavailable`, `SafetyDoorMonitoringUnavailable`,
`ExternalOpeningMonitoringUnavailable`, and `CommonInputUnavailable`.
`ExternalDataUnavailable` replaces per-provider `ExternalProviderUnavailable...`
faults and `ExternalHazardDataUnavailable`. Per-source contributors, consumer
coverage bindings and raw entity/provider health diagnostics remain separate.
Recovery, indoor-detector, runtime and maintenance faults retain their names.
One physical entity may participate in distinct input and recovery fault
families. Those logical records keep separate evidence and fault ownership;
the shared reader acquires the entity at their shortest required cadence.

Dashboards and automations using retired fault entities must use the new IDs.
Startup retires obsolete MQTT discovery and retained fault topics; it does not
interpret removal of an old entity as positive recovery evidence. Current
contributors determine the new fault state.

New entity-monitor calibration uses `report_timeout_seconds` for the maximum
age of a trusted source report and `failure_debounce_seconds` for failure
confirmation. Freshness still requires a declared trustworthy timestamp source.
The monitor derives cadence within its safety allocations; HA response deadlines
remain internal reader policy. Legacy nested `checks.freshness.max_silence_seconds`
is accepted as the report-age timeout alias; both forms must agree when present.
Existing startup, evaluation, recovery and detection-budget fields remain accepted
and validated for migration without weakening tighter dependency requirements.
See [Entity Health Monitoring](../docs/features/Entity%20Health%20Monitoring%20-%20Architecture.md#14-configuration-contract).

### Retained state and attribute audit

Ordinary startup preserves active entity topics. Both `MqttSettings` and the
packaged system configuration default `clear_retained_state_on_start` to
`false`. Keep `retain_state: false`, `heartbeat_seconds: 60`, and
`expire_after: 180`. Discovery includes an attribute template that preserves
the last attributes when an empty or whitespace-only payload arrives; valid
JSON replaces them. Nonempty malformed JSON remains an error. Historical
attributes do not establish current availability or clear an active fault.
See [Home Assistant's MQTT sensor contract](https://www.home-assistant.io/integrations/sensor.mqtt/).

The existing `clear_retained_state_on_start: true` setting remains accepted
for compatibility. An explicit override still clears active entity topics on
each application start and must be disabled after a migration. Configured
retired entities and legacy discovery topics are still removed at startup.
The [software requirement](../docs/sys/SafetyComponent%20-%20SSRD.md#47-mqtt-lifecycle-and-diagnostics)
separates this retirement from active-topic migration.

The [migration tool](migrate_mqtt_retained.py) audits only retained messages on
`<base_topic>/state/+` and `<base_topic>/attributes/+`. It never changes discovery,
availability, commands, other applications, or broker sessions belonging to
other clients. It uses a unique, authenticated MQTT 3.1.1 client with
`clean_session=True`, no automatic reconnection, bounded scan/acknowledgement
windows, and disconnects on success or failure. MQTT 5 diagnostics outside this
tool must use `clean_start=True` with a zero session expiry interval. See
[Paho's session settings](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).

Run the following only against an explicitly authorized broker. These steps
require a maintenance window because retained deletion reaches active
subscribers too:

1. Audit before switching an existing installation to the new defaults. Install
   the [tool dependencies](requirements-mqtt-tools.txt), set `MQTT_USERNAME`
   and `MQTT_PASSWORD` in the process environment using your secret store,
   and use the installation's actual base topic. Never put credentials on the
   command line. `--tls` enables certificate-verified TLS; select the broker's
   TLS port explicitly when needed.

   ```powershell
   python -m pip install -r backend/requirements-mqtt-tools.txt
   python backend/migrate_mqtt_retained.py --host <broker> --base-topic safety_component
   ```

2. Prepare the release with startup cleanup disabled and the empty-attribute
   guard. With deployment separately authorized, load its updated discovery
   and confirm the guard on active sensors before deleting retained messages.
   Then stop the SafetyComponent publisher and confirm availability is
   `offline`. Do not run an older publisher concurrently. Review the audit's
   topic list and ensure the broker account has read/write access to both
   scoped topic families.

3. If retained topics were observed, execute the explicit, one-time migration
   while the publisher is stopped:

   ```powershell
   python backend/migrate_mqtt_retained.py --host <broker> --base-topic safety_component --apply
   ```

   Only observed retained state/attribute topics receive zero-length retained
   messages. The tool waits for each QoS 1 acknowledgement and resubscribes to
   check for remaining retained messages. An empty audit is a no-op.

4. Restart the authorized installation with startup cleanup disabled. Confirm
   fresh state/attributes, availability, and heartbeat beyond 180 seconds.
   Repeat the read-only audit to detect any publisher recreating retained state.
   A failed migration must be resolved before accepting the release; do not
   interpret missing state or old attributes as healthy monitoring.

Exit codes are `0` when no retained topics were observed (including verified
cleanup), `2` when an audit finds retained topics, and `1` for a failed operation.
The scan defaults to five seconds after SUBACK; increase `--scan-seconds` up to
60 for a slow broker. MQTT 3.1.1 supplies no end-of-retained-snapshot marker, so
absence means none observed within the scan window and the account's ACL scope.
The tool prints topic names and counts, never payloads or credentials.

This migration addresses SafetyComponent empty attribute messages. Investigate
unrelated `value_json` failures by identifying their topic and publisher before
changing Zigbee2MQTT or other application templates. Persistent scanner sessions
and Mosquitto ACL cleanup are separate broker administration work.
