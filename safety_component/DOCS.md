# SafetyComponent Home Assistant App

SafetyComponent runs the SafetyFunctions backend and Safety Home frontend in a
single Home Assistant App. AppDaemon is an internal runtime detail; no separate
AppDaemon App is required after migration.

The App connects to Home Assistant through the Supervisor-provided token,
serves Safety Home only through authenticated Ingress, and keeps installation
configuration and lifecycle state in its App-specific configuration directory.

## Installation

This first package is experimental. Add this Git repository to the Home
Assistant App store, install **SafetyComponent**, and start it once. The first
start creates `/addon_configs/<repository>_safety_component/user_config.yml`
and then stops intentionally so an unreviewed example configuration cannot
begin monitoring a real installation.

Edit `user_config.yml`, replace every example entity and area binding, then
start the App again. The startup service parses and compiles that file with its
packaged system policy before AppDaemon starts; SafetyFunctions then performs
the full schema and Home Assistant entity validation during initialization.

The App configuration tab currently owns the runtime log level. Complex entity,
area, room, detector, and opening mappings remain in `user_config.yml`; the
Home Assistant App schema supports only shallow nested structures and cannot
provide the entity selectors required by this safety configuration.

AppDaemon's required latitude, longitude, elevation, and time zone are generated
from Home Assistant Core configuration on every start. Do not duplicate these
runtime settings in the App options. The safety provider coordinates under
`user_config.site` remain installation-owned inputs and may intentionally differ
from the Home Assistant installation location.

## Configuration ownership

- `user_config.yml` contains installation-owned Home Assistant bindings,
  notification destinations, location, language, and enabled components.
- The packaged `system_config.yml` contains software policy, calibration,
  fault definitions, provider lifecycle, and stable runtime contracts.
- `apps.yaml` is generated inside the container on every start and must not be
  edited.
- `appdaemon/*.json` contains notification, recovery, and component persistence
  owned by the running App.

The public SafetyComponent repository contains only
`backend/config/user_config.example.yml`. Keep the real `user_config.yml` in a
separate private repository or another access-controlled backup, and copy it to
the App-specific configuration directory during installation or recovery.

Changing stable fault keys, Safety Mechanism IDs, MQTT topics, entity IDs, raw
state codes, or recovery behavior requires a coordinated code, requirements,
test, and deployment change.

## Migration from the separate AppDaemon App

Use a controlled cutover so two SafetyFunctions instances never run at once:

1. Back up the old AppDaemon App configuration.
2. Start SafetyComponent once to create its App-specific `user_config.yml`,
   then leave SafetyComponent stopped.
3. Copy the reviewed contents of the old SafetyFunctions
   `config/user_config.yml` into the new `user_config.yml`.
4. If lifecycle continuity is required, copy the old
   `appdaemon/notification_state.json`, `appdaemon/recovery_state.json`, and
   `appdaemon/internal_environment_state.json` files into the new App's
   `appdaemon/` directory. Missing files are created by the backend as needed.
5. Stop the separate AppDaemon App, or remove its `SafetyFunctions` entry.
6. Start SafetyComponent and inspect the App log for configuration or entity
   validation errors.

Do not run the old and new backends together. They would register duplicate
listeners, publish the same stable MQTT entities, and could duplicate
notifications or recovery handling.

## Verification

After the configured startup grace period:

1. Open **Safety Home** from the Home Assistant sidebar.
2. Verify `sensor.safety_app_health` reports `running`.
3. Verify `sensor.safetysystem_state` and Entity Health Monitoring reflect the
   expected installation state.
4. Review fresh App logs for validation, connection, MQTT, notification, or
   provider errors.

Do not trigger household routines, actuators, or synthetic safety alerts merely
to verify the installation. Home Assistant acceptance of a notification request
does not prove physical phone delivery.

## Backup and recovery

The App uses cold backups so its persisted JSON state is not changing while the
Supervisor captures it. Restore both `user_config.yml` and the `appdaemon/`
state directory before starting a recovered instance.
