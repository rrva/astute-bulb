"""Solar position to lamp values mapping for Stockholm, Sweden."""

import datetime
import logging
import zoneinfo

from astral import Observer
from astral.sun import elevation

from .models import LocationConfig

logger = logging.getLogger(__name__)

# Elevation bands: (min_elev, max_elev, min_bright, max_bright, min_temp, max_temp)
_BANDS = [
    (-6.0, 0.0, 10, 30, 2200, 2700),  # twilight
    (0.0, 10.0, 30, 70, 2700, 3500),  # low sun
    (10.0, 30.0, 70, 100, 3500, 4500),  # mid sun
]

_NIGHT_BRIGHTNESS = 10
_NIGHT_TEMP = 2200
_MAX_BRIGHTNESS = 100
_MAX_TEMP = 4500


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def elevation_to_lamp_values(elev: float) -> tuple[int, int]:
    """Map sun elevation (degrees) to (brightness_percent, color_temp_kelvin)."""
    if elev < _BANDS[0][0]:
        return _NIGHT_BRIGHTNESS, _NIGHT_TEMP

    for min_elev, max_elev, min_br, max_br, min_t, max_t in _BANDS:
        if elev < max_elev:
            t = (elev - min_elev) / (max_elev - min_elev)
            return int(round(_lerp(min_br, max_br, t))), int(round(_lerp(min_t, max_t, t)))

    return _MAX_BRIGHTNESS, _MAX_TEMP


def get_solar_lamp_values(
    location: LocationConfig | None = None,
    now: datetime.datetime | None = None,
) -> tuple[int, int]:
    """Get current lamp values based on sun position at a given location.

    Returns (brightness_percent, color_temp_kelvin).
    """
    if location is None:
        # Fallback to Stockholm if no location provided
        observer = Observer(latitude=59.33, longitude=18.07, elevation=0)
        tz = zoneinfo.ZoneInfo("Europe/Stockholm")
    else:
        observer = Observer(
            latitude=location.latitude,
            longitude=location.longitude,
            elevation=location.elevation,
        )
        tz = zoneinfo.ZoneInfo(location.timezone)

    if now is None:
        now = datetime.datetime.now(tz)
    sun_elevation = elevation(observer, now)
    brightness, color_temp = elevation_to_lamp_values(sun_elevation)
    logger.info(f"Solar: elevation={sun_elevation:.1f}° -> {brightness}% {color_temp}K")
    return brightness, color_temp
