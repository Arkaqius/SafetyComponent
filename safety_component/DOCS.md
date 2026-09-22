# SafetyComponent Home Assistant App

SafetyComponent runs the SafetyFunctions backend and Safety Home frontend in a
single Home Assistant App. AppDaemon is an internal runtime detail; no separate
AppDaemon App is required after migration.

The App connects to Home Assistant through the Supervisor-provided token,
serves Safety Home only through authenticated Ingress, and keeps installation
configuration and lifecycle state in its App-specific configuration directory.
Because the same Ingress includes the private installation editor, the sidebar
panel is restricted to Home Assistant administrators.

## Installation

Add this Git repository to the Home Assistant App store, install
**SafetyComponent**, and start it. On a fresh installation, the Safety Home
panel and its configuration API start while SafetyFunctions waits. Open
**Safety Home → Konfiguracja** as a Home Assistant administrator. Replace the
example bindings in the draft with your installation values, or click
**Wczytaj user_config YAML** to load an existing version 2 `.yml`/`.yaml`
file. Import validates the file and fills the form; it does not save it yet.
Review the result and click **Utwórz user_config.yml**. The private file is then
written to `/addon_configs/<repository>_safety_component/user_config.yml`.

Restart the App after saving. The backend compiles the file with its packaged
system policy before AppDaemon starts; SafetyFunctions then performs Home
Assistant entity validation during initialization. If source compilation
fails, Safety Home stays available so the configuration can be corrected.

The App configuration tab owns the runtime log level. The Safety Home editor
owns user and installation settings stored in `user_config.yml`, including
entity, area, room, detector, and opening mappings. The packaged
`system_config.yml` is not editable from the UI.

The editor validates the complete model and checks it with the packaged system
configuration before an atomic save. Saving does not change the running safety
logic. Restart the App to compile and apply the new source. If another session
changed the file after it was opened, reload the page and reconcile the newer
revision instead of overwriting it.

AppDaemon's required latitude, longitude, elevation, and time zone are generated
from Home Assistant Core configuration on every start. The same current latitude
and longitude are used for the safety providers. Do not duplicate coordinates
in the App options or `user_config.installation.site`; its timezone, country,
and TERYT codes remain installation-owned.

## Configuration ownership

- `user_config.yml` contains a normalized registry of installation-owned rooms,
  openings, detectors, monitored entities, Home Assistant bindings,
  notification destinations, location, language, and enabled components.
- The packaged `system_config.yml` contains software policy, calibration,
  fault definitions, provider lifecycle, stable runtime contracts, and
  installation-independent defaults.
- `apps.yaml` is generated inside the container on every start and must not be
  edited.
- `appdaemon/*.json` contains notification, recovery, and component persistence
  owned by the running App.

The public SafetyComponent repository contains only
`backend/config/user_config.example.yml`. Keep the real `user_config.yml` in a
separate private repository or another access-controlled backup. It can be
restored through the editor's YAML import or copied into the App-specific
configuration directory while the App is stopped.

Configuration model version 2 applies values in the order system default,
installation default, then asset override. Declare a physical opening once and
attach its `external_hazard` or `safety_door` roles; a room references that
opening by its stable key. `user_config.model_version: 2` is mandatory; missing,
older, and unknown versions stop before AppDaemon starts.

Changing stable fault keys, Safety Mechanism IDs, MQTT topics, entity IDs, raw
state codes, or recovery behavior requires a coordinated code, requirements,
test, and deployment change.

## Migration from the separate AppDaemon App

Use a controlled cutover so two SafetyFunctions instances never run at once:

1. Back up the old AppDaemon App configuration.
2. Start SafetyComponent. SafetyFunctions waits while the configuration panel
   is available.
3. Open **Safety Home → Konfiguracja**, import the reviewed version 2
   `user_config.yml`, inspect it, and save. Alternatively copy the file into
   the App-specific configuration directory while the App is stopped.
4. If lifecycle continuity is required, copy the old
   `appdaemon/notification_state.json`, `appdaemon/recovery_state.json`, and
   `appdaemon/internal_environment_state.json` files into the new App's
   `appdaemon/` directory. Missing files are created by the backend as needed.
5. Stop the separate AppDaemon App, or remove its `SafetyFunctions` entry.
6. Restart SafetyComponent and inspect the App log for configuration or entity
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
