"""TinyTuya wrapper for controlling Ledvance Sun@Home lamps."""

import colorsys
import logging
import time

import tinytuya

from .models import LampConfig, LampState

logger = logging.getLogger(__name__)

DPS_POWER = "20"
DPS_MODE = "21"
DPS_BRIGHTNESS = "22"
DPS_COLOR_TEMP = "23"
DPS_HSV_COLOR = "24"

TUYA_BRIGHTNESS_MIN = 10
TUYA_BRIGHTNESS_MAX = 1000
TUYA_COLOR_TEMP_MIN = 0
TUYA_COLOR_TEMP_MAX = 1000

# Error 914 tracking: after this many consecutive failures, the device is
# considered "stuck" and likely needs a physical power cycle.
ERR914_STUCK_THRESHOLD = 5
# Once stuck, only retry every this many seconds instead of every request.
ERR914_BACKOFF_SECONDS = 600  # 10 minutes


class LampController:
    """Controller for a single Ledvance Sun@Home lamp."""

    def __init__(self, config: LampConfig):
        self.config = config
        self._device: tinytuya.BulbDevice | None = None
        # Error 914 tracking
        self._err914_count: int = 0
        self._err914_first: float | None = None
        self._err914_last_attempt: float | None = None
        self._err914_stuck_logged: bool = False
        # Last scene values sent, to skip redundant commands
        self._last_scene: tuple[int, int] | None = None  # (tuya_brightness, tuya_temp)

    def _get_device(self, fresh: bool = False) -> tinytuya.BulbDevice:
        """Get or create device connection. Use fresh=True for max reliability."""
        if fresh:
            self._reset_connection()
        if self._device is None:
            self._device = tinytuya.BulbDevice(
                dev_id=self.config.device_id,
                address=self.config.ip,
                local_key=self.config.local_key,
                version=float(self.config.version),
            )
            # Prefer reliability: avoid stale persistent sockets.
            self._device.set_socketPersistent(False)
            self._device.set_socketTimeout(3)
            self._device.set_socketRetryLimit(2)
        return self._device

    def _reset_connection(self):
        """Reset the device connection."""
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    @staticmethod
    def _is_err914(result) -> bool:
        """Check if result is a Tuya error 914 (key/version mismatch)."""
        return isinstance(result, dict) and result.get("Err") == "914"

    @property
    def is_stuck_err914(self) -> bool:
        """True if device is in a persistent error 914 state."""
        return self._err914_count >= ERR914_STUCK_THRESHOLD

    @property
    def err914_duration(self) -> float | None:
        """How long (seconds) the device has been in error 914 state, or None."""
        if self._err914_first is None:
            return None
        return time.time() - self._err914_first

    def _record_err914(self):
        """Record an error 914 occurrence and detect stuck state."""
        now = time.time()
        if self._err914_first is None:
            self._err914_first = now
        self._err914_count += 1
        self._err914_last_attempt = now

        if self.is_stuck_err914 and not self._err914_stuck_logged:
            duration_min = (self.err914_duration or 0) / 60
            logger.error(
                "STUCK DEVICE: %s (%s) has returned error 914 %d consecutive "
                "times over %.0f minutes. The local key is likely correct but "
                "the device encryption is in a bad state. A physical power "
                "cycle (unplug and replug) is usually required to fix this. "
                "Backing off to one attempt every %ds.",
                self.config.id,
                self.config.ip,
                self._err914_count,
                duration_min,
                ERR914_BACKOFF_SECONDS,
            )
            self._err914_stuck_logged = True

    def _clear_err914(self):
        """Clear error 914 tracking after a successful operation."""
        if self._err914_count > 0:
            logger.info(
                "%s recovered from error 914 state after %d failures (%.0f minutes)",
                self.config.id,
                self._err914_count,
                (self.err914_duration or 0) / 60,
            )
        self._err914_count = 0
        self._err914_first = None
        self._err914_last_attempt = None
        self._err914_stuck_logged = False

    def should_skip_for_backoff(self) -> bool:
        """Return True if this device should be skipped due to 914 backoff."""
        if not self.is_stuck_err914:
            return False
        if self._err914_last_attempt is None:
            return False
        elapsed = time.time() - self._err914_last_attempt
        return elapsed < ERR914_BACKOFF_SECONDS

    @staticmethod
    def _is_success(result) -> bool:
        if result is None or result is False:
            return False
        if isinstance(result, dict) and result.get("Error"):
            return False
        if isinstance(result, str) and "Error" in result:
            return False
        return True

    @staticmethod
    def _normalize_send_result(result):
        """Normalize fire-and-forget send() responses into a success sentinel."""
        if result is None:
            return {"dps": "ok"}
        return result

    def _send_command(self, action: str, func, *args, **kwargs) -> bool:
        """Send command with retry on failure."""
        total_start = time.perf_counter()
        saw_914 = False
        for attempt in range(2):
            attempt_start = time.perf_counter()
            try:
                device = self._get_device(fresh=True)
                result = func(device, *args, **kwargs)
                attempt_ms = (time.perf_counter() - attempt_start) * 1000
                if not self._is_success(result):
                    if self._is_err914(result):
                        saw_914 = True
                    logger.warning(
                        "%s (%s:6668) %s attempt %d failed in %.1fms: %s",
                        self.config.id,
                        self.config.ip,
                        action,
                        attempt + 1,
                        attempt_ms,
                        result,
                    )
                    self._reset_connection()
                    continue
                logger.info(
                    "%s %s attempt %d ok in %.1fms",
                    self.config.id,
                    action,
                    attempt + 1,
                    attempt_ms,
                )
                self._clear_err914()
                return True
            except Exception as e:
                attempt_ms = (time.perf_counter() - attempt_start) * 1000
                logger.warning(
                    "%s (%s:6668) %s attempt %d exception in %.1fms: %s",
                    self.config.id,
                    self.config.ip,
                    action,
                    attempt + 1,
                    attempt_ms,
                    e,
                )
                self._reset_connection()
            finally:
                # Always close to avoid reusing stale sockets.
                self._reset_connection()
        total_ms = (time.perf_counter() - total_start) * 1000
        logger.warning(
            "%s (%s:6668) %s failed after %.1fms",
            self.config.id,
            self.config.ip,
            action,
            total_ms,
        )
        if saw_914:
            self._record_err914()
        return False

    def _percent_to_tuya_brightness(self, percent: int) -> int:
        if percent <= 0:
            return TUYA_BRIGHTNESS_MIN
        if percent >= 100:
            return TUYA_BRIGHTNESS_MAX
        span = TUYA_BRIGHTNESS_MAX - TUYA_BRIGHTNESS_MIN
        return int(TUYA_BRIGHTNESS_MIN + (percent / 100) * span)

    def _tuya_brightness_to_percent(self, tuya_val: int) -> int:
        if tuya_val <= TUYA_BRIGHTNESS_MIN:
            return 0
        if tuya_val >= TUYA_BRIGHTNESS_MAX:
            return 100
        span = TUYA_BRIGHTNESS_MAX - TUYA_BRIGHTNESS_MIN
        return int((tuya_val - TUYA_BRIGHTNESS_MIN) / span * 100)

    def _kelvin_to_tuya_temp(self, kelvin: int) -> int:
        min_k = self.config.min_color_temp
        max_k = self.config.max_color_temp
        kelvin = max(min_k, min(max_k, kelvin))
        return int((kelvin - min_k) / (max_k - min_k) * TUYA_COLOR_TEMP_MAX)

    def _tuya_temp_to_kelvin(self, tuya_val: int) -> int:
        min_k = self.config.min_color_temp
        max_k = self.config.max_color_temp
        return int(min_k + (tuya_val / TUYA_COLOR_TEMP_MAX) * (max_k - min_k))

    def _rgb_to_hsv_hex(self, r: int, g: int, b: int, brightness: int | None = None) -> str:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        hue = int(h * 360)
        sat = int(s * 1000)
        if brightness is not None:
            val = self._percent_to_tuya_brightness(brightness)
        else:
            val = int(v * 1000)
        return f"{hue:04x}{sat:04x}{val:04x}"

    def _hsv_hex_to_components(self, hsv_hex: str) -> tuple[int, int, int]:
        if len(hsv_hex) != 12:
            return 0, 0, 100
        try:
            hue = int(hsv_hex[0:4], 16)
            sat = int(hsv_hex[4:8], 16)
            val = int(hsv_hex[8:12], 16)
            return hue, int(sat / 10), self._tuya_brightness_to_percent(val)
        except ValueError:
            return 0, 0, 100

    def get_status(self) -> LampState:
        try:
            device = self._get_device(fresh=True)
            status = device.status()
            if "Error" in status:
                if self._is_err914(status):
                    self._record_err914()
                logger.error(
                    "Error getting status for %s (%s:6668): %s",
                    self.config.id,
                    self.config.ip,
                    status,
                )
                self._reset_connection()
                return LampState(id=self.config.id, name=self.config.name, online=False)

            self._clear_err914()
            dps = status.get("dps", {})
            power = dps.get(DPS_POWER, False)
            mode = dps.get(DPS_MODE, "white")
            brightness_raw = dps.get(DPS_BRIGHTNESS, 1000)
            color_temp_raw = dps.get(DPS_COLOR_TEMP, 500)
            brightness = self._tuya_brightness_to_percent(brightness_raw)
            color_temp = self._tuya_temp_to_kelvin(color_temp_raw)

            hue, saturation = None, None
            if mode == "colour" and DPS_HSV_COLOR in dps:
                hue, saturation, _ = self._hsv_hex_to_components(dps[DPS_HSV_COLOR])

            return LampState(
                id=self.config.id,
                name=self.config.name,
                online=True,
                power=power,
                brightness=brightness,
                color_temp=color_temp,
                mode=mode,
                hue=hue,
                saturation=saturation,
            )
        except Exception as e:
            logger.exception(
                "Exception getting status for %s (%s:6668): %s",
                self.config.id,
                self.config.ip,
                e,
            )
            self._reset_connection()
            return LampState(id=self.config.id, name=self.config.name, online=False)

    def turn_on_with_scene(self, brightness: int, color_temp: int, force: bool = False) -> bool:
        """Turn on lamp with specific brightness and color temperature.

        Skips sending if the values haven't changed since last successful send
        (unless force=True), to avoid hammering the device with redundant
        commands that can cause error 914 lockups.
        """
        tuya_brightness = self._percent_to_tuya_brightness(brightness)
        tuya_temp = self._kelvin_to_tuya_temp(color_temp)

        scene = (tuya_brightness, tuya_temp)
        if not force and self._last_scene == scene:
            return True

        def cmd(device):
            # Single payload = 1 TCP connection instead of 4 separate set_value
            # calls. Returns None on success (device sends no ack), so we
            # verify by reading status back.
            payload = device.generate_payload(
                tinytuya.CONTROL,
                {
                    DPS_POWER: True,
                    DPS_MODE: "white",
                    DPS_BRIGHTNESS: tuya_brightness,
                    DPS_COLOR_TEMP: tuya_temp,
                },
            )
            return self._normalize_send_result(device.send(payload))

        success = self._send_command("turn_on_with_scene", cmd)
        logger.info(
            f"Turn on with scene {self.config.id} brightness={brightness}% temp={color_temp}K "
            f"(tuya br={tuya_brightness} temp={tuya_temp}): {'OK' if success else 'FAILED'}"
        )
        if success:
            self._last_scene = scene
        return success

    def turn_off(self) -> bool:
        def cmd(device):
            return device.set_status(False, switch=DPS_POWER)

        success = self._send_command("turn_off", cmd)
        logger.info(f"Turn off {self.config.id}: {'OK' if success else 'FAILED'}")
        if success:
            self._last_scene = None  # force scene send on next turn_on
        return success

    def set_brightness(self, brightness: int) -> bool:
        def cmd(device):
            tuya_brightness = self._percent_to_tuya_brightness(brightness)
            payload = device.generate_payload(
                tinytuya.CONTROL, {DPS_POWER: True, DPS_BRIGHTNESS: tuya_brightness}
            )
            return self._normalize_send_result(device.send(payload))

        success = self._send_command("set_brightness", cmd)
        result = "OK" if success else "FAILED"
        logger.info(f"Set brightness {self.config.id} to {brightness}%: {result}")
        if success:
            # Manual changes should not block the next solar scene re-assertion.
            self._last_scene = None
        return success

    def set_color_temp(self, kelvin: int) -> bool:
        def cmd(device):
            tuya_temp = self._kelvin_to_tuya_temp(kelvin)
            payload = device.generate_payload(
                tinytuya.CONTROL, {DPS_POWER: True, DPS_MODE: "white", DPS_COLOR_TEMP: tuya_temp}
            )
            return self._normalize_send_result(device.send(payload))

        success = self._send_command("set_color_temp", cmd)
        result = "OK" if success else "FAILED"
        logger.info(f"Set color temp {self.config.id} to {kelvin}K: {result}")
        if success:
            # Manual changes should not block the next solar scene re-assertion.
            self._last_scene = None
        return success

    def set_color(self, red: int, green: int, blue: int, brightness: int | None = None) -> bool:
        def cmd(device):
            hsv_hex = self._rgb_to_hsv_hex(red, green, blue, brightness)
            payload = device.generate_payload(
                tinytuya.CONTROL, {DPS_POWER: True, DPS_MODE: "colour", DPS_HSV_COLOR: hsv_hex}
            )
            return self._normalize_send_result(device.send(payload))

        success = self._send_command("set_color", cmd)
        logger.info(f"Set color {self.config.id}: {'OK' if success else 'FAILED'}")
        if success:
            # Manual changes should not block the next solar scene re-assertion.
            self._last_scene = None
        return success

    def close(self):
        self._reset_connection()


class LampManager:
    def __init__(self):
        self._controllers: dict[str, LampController] = {}

    def add_lamp(self, config: LampConfig):
        self._controllers[config.id] = LampController(config)
        logger.info(f"Added lamp: {config.id} ({config.name}) at {config.ip}")

    def get_controller(self, lamp_id: str) -> LampController | None:
        return self._controllers.get(lamp_id)

    def get_all_controllers(self) -> list[LampController]:
        return list(self._controllers.values())

    def get_all_status(self) -> list[LampState]:
        return [ctrl.get_status() for ctrl in self._controllers.values()]

    def close_all(self):
        for controller in self._controllers.values():
            controller.close()
        self._controllers.clear()
