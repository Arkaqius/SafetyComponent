from typing import List

from pydantic import ConfigDict, Field

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys


def test_strict_model_accepts_aliases():
    class AliasModel(StrictBaseModel):
        model_config = ConfigDict(extra="allow", populate_by_name=True)

        value_a: int = Field(validation_alias="input_a")
        value_b: int = Field(alias="input_b")

    model = AliasModel.model_validate(
        {"input_a": 1, "input_b": 2},
        context={"strict_validation": True},
    )
    assert model.value_a == 1
    assert model.value_b == 2


def test_log_extra_keys_with_level_and_without_level():
    class ExtraModel(StrictBaseModel):
        model_config = ConfigDict(extra="allow")
        name: str

    model = ExtraModel.model_validate(
        {"name": "ok", "extra": "val"},
        context={"strict_validation": False},
    )

    calls_with_level: List[tuple[str, str]] = []
    calls_without_level: List[str] = []

    def log_with_level(message: str, level: str = "") -> None:
        calls_with_level.append((message, level))

    def log_no_level(message: str) -> None:
        calls_without_level.append(message)

    log_extra_keys(model, log_with_level, "path")
    log_extra_keys(model, log_no_level, "path")

    assert calls_with_level
    assert calls_without_level
