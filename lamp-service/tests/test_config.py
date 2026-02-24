"""Tests for configuration file discovery."""

from pathlib import Path

import pytest

from src import config


def test_find_config_file_falls_back_to_repo_root_config(monkeypatch, tmp_path):
    monkeypatch.delenv("LAMPS_CONFIG", raising=False)

    empty_cwd = tmp_path / "cwd"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(config.Path, "home", lambda: fake_home)

    expected = Path(config.__file__).resolve().parents[2] / "config" / "lamps.yaml"

    assert config.find_config_file().resolve() == expected.resolve()


def test_load_config_empty_yaml_uses_defaults(tmp_path):
    config_file = tmp_path / "lamps.yaml"
    config_file.write_text("", encoding="utf-8")

    loaded = config.load_config(config_file)

    assert loaded.service.host == "0.0.0.0"
    assert loaded.service.port == 8000
    assert loaded.lamps == []


def test_load_config_rejects_non_mapping_yaml(tmp_path):
    config_file = tmp_path / "lamps.yaml"
    config_file.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a YAML mapping"):
        config.load_config(config_file)
