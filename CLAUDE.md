# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Deployment

See [DEPLOY.md](DEPLOY.md) for deploy steps, remote environment details, and service definitions.

## Project Overview

Local control service for Ledvance Sun@Home lamps using TinyTuya. Provides a REST API that Matterbridge webhooks call for Google Home voice control. All lamp commands travel locally on WiFi using Tuya Protocol 3.5.

## Tooling

- **Python**: 3.12+
- **Package manager**: uv (hatchling build backend)
- **Linter/formatter**: ruff (line-length 99, pyflakes + pycodestyle + isort + bugbear)
- **Type checker**: ty
- **Testing**: pytest with pytest-asyncio
- **Pre-commit**: ruff + ty hooks

## Commands

```bash
# Install dependencies (from lamp-service directory)
uv sync --group dev

# Run the service
LAMPS_CONFIG="../config/lamps.yaml" uv run uvicorn src.main:app --host 0.0.0.0 --port 8000

# Run tests
uv run pytest
uv run pytest tests/test_models.py -v              # single file
uv run pytest tests/test_models.py::test_lamp_config_defaults -v  # single test

# Lint & format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ty check src/

# Auto-fix lint issues
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

## Architecture

### Core Components

- **main.py**: FastAPI app with two endpoint groups:
  - `/lamps/{id}/*` - JSON REST API (POST, returns CommandResponse with state)
  - `/webhook/{id}/*` - GET endpoints for Matterbridge webhooks (simple success/fail)

- **lamp_controller.py**: TinyTuya wrapper
  - `LampController` - controls single lamp, handles Tuya protocol (DPS 20-24)
  - `LampManager` - registry of controllers, loaded from config at startup
  - Commands use fresh socket per attempt with retry logic
  - Error 914 detection with backoff (stuck devices need physical power cycle)

- **solar.py**: Sun position to lamp values mapping
  - Uses `astral` library for Stockholm (59.33N, 18.07E) sun elevation
  - Maps elevation to brightness (10-100%) and color temp (2200-4500K)
  - Used by on-endpoints for instant solar values and by background sync task

- **Background solar sync**: asyncio task in FastAPI lifespan, updates on-lamps every 60s

### Tuya Protocol Details

Lamp state is controlled via Data Points (DPS):
- DPS 20: Power (bool)
- DPS 21: Mode ("white" or "colour")
- DPS 22: Brightness (10-1000, maps to 0-100%)
- DPS 23: Color temp (0-1000, 0=warmest/2200K, 1000=coolest/5000K)
- DPS 24: HSV color as 12-char hex (HHHHSSSSВВВВ)

### Configuration

Config loaded from `LAMPS_CONFIG` env var or standard paths. Each lamp needs:
- `device_id`, `ip`, `local_key` (from Ledvance account extraction)
- `version` defaults to "3.5"
- Color temp range defaults to 2200-5000K

### Environment Variables

- `LAMPS_CONFIG` - path to lamps.yaml (falls back to `config/lamps.yaml` in cwd, repo root, or `~/.config/local-lamps/`)

## Code Style

- Use `X | None` instead of `Optional[X]` (no `from typing import` needed)
- Prefer `%s` format strings in logger calls, f-strings elsewhere
- Line length limit: 99 characters
