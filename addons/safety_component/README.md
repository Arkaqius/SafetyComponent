# Safety Component Add-on

This add-on bundles AppDaemon with the SafetyFunctions backend.

## Default behavior
- AppDaemon config is written to `/data/appdaemon.yaml` on first start.
- App config is copied from `/app/app_cfg.yaml` to `/data/apps.yaml` if not present.

## Configuration
Set options in the add-on UI:
- `ha_url`: Home Assistant URL (default `http://supervisor/core`).
- `token`: Long-lived access token (optional if Supervisor token is available).
- `log_level`: AppDaemon log level.
- `time_zone`, `latitude`, `longitude`, `elevation`: Optional location metadata.

To override the SafetyFunctions app config, edit `/data/apps.yaml`.
