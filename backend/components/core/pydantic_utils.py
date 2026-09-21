"""Helpers for consistent, context-aware Pydantic validation."""

from __future__ import annotations

from typing import Any, Callable, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator


class StrictBaseModel(BaseModel):
    """Base model that enforces unknown-key checks when strict_validation is enabled."""

    model_config = ConfigDict(extra="allow")
    allow_unknown_keys: ClassVar[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _enforce_strict_keys(cls, data: Any, info: Any) -> Any:
        if not isinstance(data, dict):
            return data

        strict = True
        if info.context and "strict_validation" in info.context:
            strict = bool(info.context["strict_validation"])

        if getattr(cls, "allow_unknown_keys", False):
            return data

        if not strict:
            return data

        allowed: set[str] = set()
        for name, field in cls.model_fields.items():
            allowed.add(name)
            alias = getattr(field, "validation_alias", None)
            if isinstance(alias, str):
                allowed.add(alias)
            alias = getattr(field, "alias", None)
            if isinstance(alias, str):
                allowed.add(alias)

        extras = sorted(key for key in data.keys() if key not in allowed)
        if extras:
            raise ValueError(f"Unknown keys for {cls.__name__}: {', '.join(extras)}")

        return data


def log_extra_keys(
    model: BaseModel, log: Callable[..., None] | None, path: str
) -> None:
    """Log unknown keys captured by a model when strict validation is disabled."""
    if not log:
        return

    extras = getattr(model, "model_extra", None) or {}
    if not extras:
        return

    message = f"Unknown keys in {path}: {', '.join(sorted(extras.keys()))}"
    try:
        log(message, level="WARNING")
    except TypeError:
        log(message)
