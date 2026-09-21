"""Tests for separated system and installation configuration sources."""

import sys
from pathlib import Path

import yaml

from build_app_config import compile_config, main

BACKEND_DIR = Path(__file__).parents[1]


def test_example_installation_config_compiles() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )

    assert compiled["SafetyFunctions"]["module"] == "SafetyFunctions"
    assert compiled["SafetyFunctions"]["user_config"]["site"]["country_code"] == "PL"


def test_cli_accepts_explicit_app_paths(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "apps.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_app_config.py",
            "--system",
            str(BACKEND_DIR / "config" / "system_config.yml"),
            "--user",
            str(BACKEND_DIR / "config" / "user_config.example.yml"),
            "--output",
            str(output_path),
        ],
    )

    main()

    assert yaml.safe_load(output_path.read_text(encoding="utf-8")) == compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )


def test_user_example_does_not_inherit_production_entity_collections() -> None:
    compiled = compile_config(
        user_path=BACKEND_DIR / "config" / "user_config.example.yml"
    )["SafetyFunctions"]["user_config"]["safety_components"]

    assert set(compiled["TemperatureComponent"]["rooms"]) == {"LivingRoom"}
    assert set(compiled["SafetyDoorsComponent"]["doors"]) == {"EntranceDoor"}
    assert set(compiled["ExternalHazardComponent"]["openings"]) == {
        "LivingRoomWindow"
    }
    assert compiled["TemperatureComponent"]["defaults"][
        "CAL_HIGH_TEMP_THRESHOLD"
    ] == 28.0
