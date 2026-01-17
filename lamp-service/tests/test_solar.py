"""Tests for solar position to lamp values mapping."""

import datetime
import zoneinfo

from src.solar import elevation_to_lamp_values, get_solar_lamp_values

STOCKHOLM_TZ = zoneinfo.ZoneInfo("Europe/Stockholm")


class TestElevationToLampValues:
    """Test the pure elevation-to-values mapping function."""

    def test_deep_night(self):
        """Well below horizon: warmest and dimmest."""
        brightness, color_temp = elevation_to_lamp_values(-20.0)
        assert brightness == 10
        assert color_temp == 2200

    def test_night_boundary(self):
        """At -6 degrees: still at night floor values."""
        brightness, color_temp = elevation_to_lamp_values(-6.0)
        assert brightness == 10
        assert color_temp == 2200

    def test_twilight_midpoint(self):
        """Midpoint of twilight band (-3 degrees)."""
        brightness, color_temp = elevation_to_lamp_values(-3.0)
        assert brightness == 20  # midpoint of 10-30
        assert color_temp == 2450  # midpoint of 2200-2700

    def test_horizon(self):
        """At 0 degrees (horizon): top of twilight band."""
        brightness, color_temp = elevation_to_lamp_values(0.0)
        assert brightness == 30
        assert color_temp == 2700

    def test_low_sun_midpoint(self):
        """Midpoint of low sun band (5 degrees)."""
        brightness, color_temp = elevation_to_lamp_values(5.0)
        assert brightness == 50  # midpoint of 30-70
        assert color_temp == 3100  # midpoint of 2700-3500

    def test_low_sun_top(self):
        """Top of low sun band (10 degrees)."""
        brightness, color_temp = elevation_to_lamp_values(10.0)
        assert brightness == 70
        assert color_temp == 3500

    def test_mid_sun_midpoint(self):
        """Midpoint of mid sun band (20 degrees)."""
        brightness, color_temp = elevation_to_lamp_values(20.0)
        assert brightness == 85  # midpoint of 70-100
        assert color_temp == 4000  # midpoint of 3500-4500

    def test_high_sun(self):
        """Above 30 degrees: max values."""
        brightness, color_temp = elevation_to_lamp_values(30.0)
        assert brightness == 100
        assert color_temp == 4500

    def test_very_high_sun(self):
        """Well above 30 degrees: still capped at max."""
        brightness, color_temp = elevation_to_lamp_values(54.0)
        assert brightness == 100
        assert color_temp == 4500


class TestGetSolarLampValues:
    """Test the time-based function that uses astral."""

    def test_returns_tuple(self):
        """Should return (brightness, color_temp) tuple."""
        result = get_solar_lamp_values()
        assert isinstance(result, tuple)
        assert len(result) == 2
        brightness, color_temp = result
        assert 10 <= brightness <= 100
        assert 2200 <= color_temp <= 4500

    def test_with_explicit_time(self):
        """Should accept an explicit datetime."""
        # Stockholm noon on summer solstice - sun is very high
        summer_noon = datetime.datetime(2026, 6, 21, 12, 0, 0, tzinfo=STOCKHOLM_TZ)
        brightness, color_temp = get_solar_lamp_values(now=summer_noon)
        assert brightness == 100
        assert color_temp == 4500

    def test_winter_midnight(self):
        """Stockholm winter midnight - sun well below horizon."""
        winter_midnight = datetime.datetime(2026, 12, 21, 0, 0, 0, tzinfo=STOCKHOLM_TZ)
        brightness, color_temp = get_solar_lamp_values(now=winter_midnight)
        assert brightness == 10
        assert color_temp == 2200
