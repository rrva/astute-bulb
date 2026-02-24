"""Tests for LampController.turn_on_with_scene."""

from unittest.mock import MagicMock, patch

import pytest
import tinytuya

from src.lamp_controller import (
    DPS_BRIGHTNESS,
    DPS_COLOR_TEMP,
    DPS_HSV_COLOR,
    DPS_MODE,
    DPS_POWER,
    ERR914_STUCK_THRESHOLD,
    LampController,
)
from src.models import LampConfig


@pytest.fixture
def lamp_config():
    return LampConfig(
        id="test",
        name="Test Lamp",
        device_id="fake_id",
        ip="192.168.1.1",
        local_key="fake_key_16char!",
        version="3.3",
    )


class TestTurnOnWithScene:
    def test_sends_single_payload(self, lamp_config):
        """turn_on_with_scene sends all DPS in a single generate_payload+send."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command") as mock_send:
            mock_send.return_value = True
            result = controller.turn_on_with_scene(brightness=70, color_temp=3500)

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == "turn_on_with_scene"

        # Execute the command function to inspect device calls
        cmd_func = call_args[0][1]
        mock_device = MagicMock()
        mock_device.send.return_value = None  # device returns None on success
        cmd_func(mock_device)

        # Should use generate_payload with all DPS in one call
        mock_device.generate_payload.assert_called_once()
        payload_args = mock_device.generate_payload.call_args
        assert payload_args[0][0] == tinytuya.CONTROL
        dps = payload_args[0][1]
        assert dps[DPS_POWER] is True
        assert dps[DPS_MODE] == "white"
        assert DPS_BRIGHTNESS in dps
        assert DPS_COLOR_TEMP in dps

    def test_skips_when_values_unchanged(self, lamp_config):
        """turn_on_with_scene skips sending if values haven't changed."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command", return_value=True) as mock_send:
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            assert mock_send.call_count == 1

            # Same values again — should skip
            result = controller.turn_on_with_scene(brightness=50, color_temp=3000)
            assert result is True
            assert mock_send.call_count == 1  # not called again

    def test_resends_after_value_change(self, lamp_config):
        """turn_on_with_scene resends when values change."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command", return_value=True) as mock_send:
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            controller.turn_on_with_scene(brightness=60, color_temp=3000)
            assert mock_send.call_count == 2

    def test_force_bypasses_cache(self, lamp_config):
        """force=True sends even when values haven't changed."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command", return_value=True) as mock_send:
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            controller.turn_on_with_scene(brightness=50, color_temp=3000, force=True)
            assert mock_send.call_count == 2

    def test_clamps_brightness(self, lamp_config):
        """Brightness is clamped to 0-100 range."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command", return_value=True):
            controller.turn_on_with_scene(brightness=0, color_temp=2700)
            controller.turn_on_with_scene(brightness=100, color_temp=2700)

    def test_clamps_color_temp(self, lamp_config):
        """Color temp is clamped to lamp's min/max range."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command") as mock_send:
            mock_send.return_value = True
            controller.turn_on_with_scene(brightness=50, color_temp=2200)

            cmd_func = mock_send.call_args[0][1]
            mock_device = MagicMock()
            mock_device.send.return_value = None
            cmd_func(mock_device)

            dps = mock_device.generate_payload.call_args[0][1]
            # 2200K on a 2200-5000 range -> tuya value 0 (min tuya = warmest)
            assert dps[DPS_COLOR_TEMP] == 0

    def test_turn_off_clears_scene_cache(self, lamp_config):
        """turn_off clears the cached scene so next turn_on resends."""
        controller = LampController(lamp_config)

        with patch.object(controller, "_send_command", return_value=True) as mock_send:
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            assert mock_send.call_count == 1

            controller.turn_off()

            # Same values after off should resend
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            # 3 calls: scene, off, scene again
            assert mock_send.call_count == 3

    @pytest.mark.parametrize(
        ("method_name", "method_args"),
        [
            ("set_brightness", (42,)),
            ("set_color_temp", (3200,)),
            ("set_color", (128, 64, 32, 50)),
        ],
    )
    def test_manual_setters_clear_scene_cache(self, lamp_config, method_name, method_args):
        """Manual changes should force the next solar scene write even if values match."""
        controller = LampController(lamp_config)
        method = getattr(controller, method_name)

        with patch.object(controller, "_send_command", return_value=True) as mock_send:
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            assert mock_send.call_count == 1

            assert method(*method_args) is True
            assert mock_send.call_count == 2

            # Must resend after manual override even if same scene is requested.
            controller.turn_on_with_scene(brightness=50, color_temp=3000)
            assert mock_send.call_count == 3


class TestErr914Detection:
    def test_not_stuck_initially(self, lamp_config):
        controller = LampController(lamp_config)
        assert not controller.is_stuck_err914
        assert not controller.should_skip_for_backoff()

    def test_becomes_stuck_after_threshold(self, lamp_config):
        controller = LampController(lamp_config)
        for _ in range(ERR914_STUCK_THRESHOLD):
            controller._record_err914()
        assert controller.is_stuck_err914

    def test_clears_on_success(self, lamp_config):
        controller = LampController(lamp_config)
        for _ in range(ERR914_STUCK_THRESHOLD):
            controller._record_err914()
        assert controller.is_stuck_err914
        controller._clear_err914()
        assert not controller.is_stuck_err914

    def test_is_err914_detection(self, lamp_config):
        err914 = {"Error": "Check device key or version", "Err": "914", "Payload": None}
        assert LampController._is_err914(err914)
        err905 = {"Error": "Network Error", "Err": "905", "Payload": None}
        assert not LampController._is_err914(err905)
        assert not LampController._is_err914({"dps": {"20": True}})
        assert not LampController._is_err914(None)


class TestWriteCommands:
    @pytest.mark.parametrize(
        ("method_name", "method_args", "required_pairs", "required_keys"),
        [
            ("set_brightness", (42,), {DPS_POWER: True}, (DPS_BRIGHTNESS,)),
            (
                "set_color_temp",
                (3200,),
                {DPS_POWER: True, DPS_MODE: "white"},
                (DPS_COLOR_TEMP,),
            ),
            (
                "set_color",
                (128, 64, 32, 50),
                {DPS_POWER: True, DPS_MODE: "colour"},
                (DPS_HSV_COLOR,),
            ),
        ],
    )
    def test_send_none_is_normalized_to_success(
        self, lamp_config, method_name, method_args, required_pairs, required_keys
    ):
        controller = LampController(lamp_config)
        method = getattr(controller, method_name)

        with patch.object(controller, "_send_command", return_value=True) as mock_send:
            assert method(*method_args) is True

        cmd_func = mock_send.call_args[0][1]
        mock_device = MagicMock()
        mock_device.send.return_value = None

        result = cmd_func(mock_device)

        assert result == {"dps": "ok"}
        dps = mock_device.generate_payload.call_args[0][1]
        for key, value in required_pairs.items():
            assert dps[key] == value
        for key in required_keys:
            assert key in dps
