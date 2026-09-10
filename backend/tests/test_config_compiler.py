"""Tests for separated system and installation configuration sources."""

from pathlib import Path

import yaml

from build_app_config import compile_config

BACKEND_DIR = Path(__file__).parents[1]


def test_generated_app_config_matches_both_sources() -> None:
    generated = yaml.safe_load(
        (BACKEND_DIR / "app_cfg.yaml").read_text(encoding="utf-8")
    )

    assert generated == compile_config()


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
