"""Configuration loader for the lamp service."""

import os
from pathlib import Path

import yaml

from .models import AppConfig, LampConfig, ServiceConfig


def find_config_file() -> Path:
    """Find the configuration file in standard locations."""
    # Check environment variable first
    if env_path := os.environ.get("LAMPS_CONFIG"):
        path = Path(env_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Config file not found at LAMPS_CONFIG path: {env_path}")

    # Check standard locations
    search_paths = [
        Path.cwd() / "config" / "lamps.yaml",
        Path.cwd() / "lamps.yaml",
        Path(__file__).resolve().parents[2] / "config" / "lamps.yaml",
        Path.home() / ".config" / "local-lamps" / "lamps.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return path

    raise FileNotFoundError(
        f"Configuration file not found. Searched: {[str(p) for p in search_paths]}. "
        "Copy config/lamps.example.yaml to config/lamps.yaml and configure your lamps."
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = find_config_file()

    with open(config_path) as f:
        raw_config = yaml.safe_load(f)

    # Parse service config
    service_data = raw_config.get("service", {})
    service_config = ServiceConfig(**service_data)

    # Parse lamp configs
    lamps_data = raw_config.get("lamps", [])
    lamp_configs = [LampConfig(**lamp) for lamp in lamps_data]

    return AppConfig(service=service_config, lamps=lamp_configs)
