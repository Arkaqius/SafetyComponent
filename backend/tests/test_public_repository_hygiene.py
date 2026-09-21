"""Regression checks for the public repository configuration boundary."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]


def test_installation_configuration_is_not_committed() -> None:
    assert not (REPOSITORY_ROOT / "backend" / "config" / "user_config.yml").exists()
    assert not (REPOSITORY_ROOT / "backend" / "app_cfg.yaml").exists()


def test_installation_configuration_is_ignored() -> None:
    ignored_paths = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".gitignore").read_text(
            encoding="utf-8"
        ).splitlines()
    }

    assert "backend/config/user_config.yml" in ignored_paths
    assert "backend/app_cfg.yaml" in ignored_paths


def test_runtime_has_no_embedded_remote_debugger() -> None:
    backend = REPOSITORY_ROOT / "backend"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in backend.rglob("*.py")
        if "tests" not in path.parts
    )

    assert "RemotePdb" not in source
    assert "remote_pdb" not in source
