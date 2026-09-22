"""Structural checks for the standalone Home Assistant App package."""

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).parents[2]
APP_ROOT = REPOSITORY_ROOT / "safety_component"


def test_app_exposes_only_authenticated_ingress() -> None:
    config = yaml.safe_load((APP_ROOT / "config.yaml").read_text(encoding="utf-8"))

    assert config["slug"] == "safety_component"
    assert config["homeassistant_api"] is True
    assert config["ingress"] is True
    assert config["ingress_port"] == 8099
    assert config["panel_icon"] == "mdi:alarm-light"
    assert config["panel_title"] == "Safety Home"
    assert config["panel_admin"] is True
    assert config["ports"]["8099/tcp"] is None


def test_app_runs_backend_and_frontend_under_s6() -> None:
    service_root = APP_ROOT / "rootfs" / "etc" / "s6-overlay"
    contents = service_root / "s6-rc.d" / "user" / "contents.d"

    for service in (
        "init-safety-component",
        "safety-backend",
        "safety-config-api",
        "safety-frontend",
    ):
        assert (contents / service).is_file()

    legacy_contents = service_root / "user-bundles.d" / "user" / "contents.d"
    assert all(
        not (legacy_contents / service).is_file()
        for service in (
            "init-safety-component",
            "safety-backend",
            "safety-config-api",
            "safety-frontend",
        )
    )

    scripts = list((service_root / "s6-rc.d").rglob("run"))
    scripts.extend((service_root / "s6-rc.d").rglob("finish"))
    scripts.append(service_root / "scripts" / "init-safety-component")
    assert scripts
    assert all(b"\r\n" not in script.read_bytes() for script in scripts)


def test_ingress_proxies_only_the_user_configuration_api() -> None:
    nginx = (
        APP_ROOT / "rootfs" / "etc" / "nginx" / "http.d" / "safety-component.conf"
    ).read_text(encoding="utf-8")
    api_run = (
        APP_ROOT
        / "rootfs"
        / "etc"
        / "s6-overlay"
        / "s6-rc.d"
        / "safety-config-api"
        / "run"
    ).read_text(encoding="utf-8")

    assert "location /api/config" in nginx
    assert "proxy_pass http://127.0.0.1:8100" in nginx
    assert "--user /config/user_config.yml" in api_run
    assert "--system /opt/safety-component/backend/config/system_config.yml" in api_run


def test_first_start_keeps_frontend_available_until_config_is_saved() -> None:
    service_root = APP_ROOT / "rootfs" / "etc" / "s6-overlay"
    init_service = service_root / "s6-rc.d" / "init-safety-component"
    assert (init_service / "type").read_text(encoding="utf-8").strip() == "oneshot"
    assert (init_service / "up").read_text(encoding="utf-8").strip() == (
        "/etc/s6-overlay/scripts/init-safety-component"
    )
    assert not (init_service / "run").exists()

    init_script = (service_root / "scripts" / "init-safety-component").read_text(
        encoding="utf-8"
    )

    assert "bashio::exit.nok" not in init_script
    assert "user_config.example.yml" not in init_script
    assert "backend/SafetyFunctions.py" in init_script
    assert "backend/components" in init_script
    assert "backend/." not in init_script
    assert "build_appdaemon_config.py" not in init_script

    backend_run = (service_root / "s6-rc.d" / "safety-backend" / "run").read_text(
        encoding="utf-8"
    )
    assert '[[ ! -f "${user_config}" ]]' in backend_run
    assert "build_app_config.py" in backend_run
    assert "--system" in backend_run
    assert "--user" in backend_run
    assert "--log-level" in backend_run
    assert "--output" in backend_run
    assert "build_appdaemon_config.py" in backend_run


def test_appdaemon_template_gets_required_location_from_home_assistant() -> None:
    template = (
        APP_ROOT / "rootfs" / "etc" / "safety-component" / "appdaemon.yaml"
    ).read_text(encoding="utf-8")

    assert "latitude: __HOME_ASSISTANT_LATITUDE__" in template
    assert "longitude: __HOME_ASSISTANT_LONGITUDE__" in template
    assert "elevation: __HOME_ASSISTANT_ELEVATION__" in template
    assert "time_zone: __HOME_ASSISTANT_TIME_ZONE__" in template
    assert "token: !env_var SUPERVISOR_TOKEN" in template
