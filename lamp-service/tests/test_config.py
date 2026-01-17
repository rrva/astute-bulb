"""Tests for configuration file discovery."""

from pathlib import Path

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
