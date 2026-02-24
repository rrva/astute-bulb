"""Tests for Pydantic models."""

import pytest

from src.models import (
    BrightnessRequest,
    ColorRequest,
    ColorTempRequest,
    LampConfig,
    LampState,
)


def test_lamp_config_defaults():
    """Test LampConfig with minimal required fields."""
    config = LampConfig(
        id="test",
        name="Test Lamp",
        device_id="abc123",
        ip="192.168.1.100",
        local_key="0123456789abcdef",
    )
    assert config.version == "3.5"
    assert config.supports_color is True
    assert config.supports_color_temp is True
    assert config.min_color_temp == 2200
    assert config.max_color_temp == 5000


def test_lamp_config_rejects_invalid_color_temp_range():
    """max_color_temp must be greater than min_color_temp."""
    with pytest.raises(ValueError, match="max_color_temp must be greater than min_color_temp"):
        LampConfig(
            id="test",
            name="Test Lamp",
            device_id="abc123",
            ip="192.168.1.100",
            local_key="0123456789abcdef",
            min_color_temp=5000,
            max_color_temp=5000,
        )


def test_lamp_state_offline():
    """Test offline lamp state."""
    state = LampState(id="test", name="Test Lamp", online=False)
    assert state.online is False
    assert state.power is False
    assert state.brightness == 100


def test_brightness_request_validation():
    """Test brightness request validation."""
    # Valid requests
    assert BrightnessRequest(brightness=0).brightness == 0
    assert BrightnessRequest(brightness=100).brightness == 100
    assert BrightnessRequest(brightness=50).brightness == 50

    # Invalid requests
    with pytest.raises(ValueError):
        BrightnessRequest(brightness=-1)
    with pytest.raises(ValueError):
        BrightnessRequest(brightness=101)


def test_color_temp_request_validation():
    """Test color temperature request validation."""
    # Valid requests
    assert ColorTempRequest(temperature=2700).temperature == 2700
    assert ColorTempRequest(temperature=5000).temperature == 5000

    # Invalid requests
    with pytest.raises(ValueError):
        ColorTempRequest(temperature=1000)  # Too low
    with pytest.raises(ValueError):
        ColorTempRequest(temperature=8000)  # Too high


def test_color_request_validation():
    """Test color request validation."""
    # Valid requests
    color = ColorRequest(red=255, green=128, blue=0)
    assert color.red == 255
    assert color.green == 128
    assert color.blue == 0

    # With optional brightness
    color_with_brightness = ColorRequest(red=255, green=0, blue=0, brightness=50)
    assert color_with_brightness.brightness == 50

    # Invalid requests
    with pytest.raises(ValueError):
        ColorRequest(red=256, green=0, blue=0)
    with pytest.raises(ValueError):
        ColorRequest(red=0, green=-1, blue=0)
