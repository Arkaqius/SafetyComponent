# Changelog

## 0.2.0

- Start the public repository with a clean history that contains no production
  installation configuration.
- Keep `user_config.yml` and generated `app_cfg.yaml` outside version control;
  ship only a safe example configuration.
- Move the published App image to `ghcr.io/arkaqius/safetyfunctions`.

## 0.1.3

- Generate AppDaemon's required latitude, longitude, elevation, and time zone
  from Home Assistant Core configuration before starting the runtime.
- Keep Home Assistant runtime location settings out of the App options and
  installation-owned safety configuration.

## 0.1.2

- Execute the App configuration initializer from the S6 oneshot service's
  `up` command before starting the backend and frontend dependencies.
- Ensure the generated AppDaemon configuration exists before its runtime
  starts.

## 0.1.1

- Register the initialization, backend, and frontend services in the Home
  Assistant base image's S6 `user` bundle so they start with the container.
- Restore first-start creation of the App-specific `user_config.yml`.

## 0.1.0

- Package AppDaemon, SafetyFunctions, and the built Safety Home frontend in one
  Home Assistant App image.
- Add authenticated Ingress and a `mdi:alarm-light` sidebar entry.
- Persist installation configuration and runtime state in the App-specific
  configuration directory.
