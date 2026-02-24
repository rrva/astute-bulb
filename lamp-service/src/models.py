"""Pydantic models for lamp configuration and API responses."""

from pydantic import BaseModel, Field, model_validator


class LampConfig(BaseModel):
    """Configuration for a single lamp."""

    id: str = Field(..., description="Unique identifier for the lamp")
    name: str = Field(..., description="Human-readable name")
    device_id: str = Field(..., description="Tuya device ID")
    ip: str = Field(..., description="Local IP address")
    local_key: str = Field(..., description="Tuya local encryption key")
    version: str = Field(default="3.5", description="Tuya protocol version")
    supports_color: bool = Field(default=True, description="Supports RGB color")
    supports_color_temp: bool = Field(default=True, description="Supports color temperature")
    min_color_temp: int = Field(default=2200, description="Minimum color temperature in Kelvin")
    max_color_temp: int = Field(default=5000, description="Maximum color temperature in Kelvin")

    @model_validator(mode="after")
    def validate_color_temp_range(self):
        if self.max_color_temp <= self.min_color_temp:
            raise ValueError("max_color_temp must be greater than min_color_temp")
        return self


class LocationConfig(BaseModel):
    """Configuration for sun position calculations."""

    latitude: float = Field(..., description="Latitude in degrees")
    longitude: float = Field(..., description="Longitude in degrees")
    timezone: str = Field(default="UTC", description="Timezone name (e.g., Europe/Stockholm)")
    elevation: float = Field(default=0, description="Elevation in meters")


class ServiceConfig(BaseModel):
    """Service configuration."""

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    location: LocationConfig | None = Field(default=None)


class AppConfig(BaseModel):
    """Full application configuration."""

    service: ServiceConfig = Field(default_factory=ServiceConfig)
    lamps: list[LampConfig] = Field(default_factory=list)


class LampState(BaseModel):
    """Current state of a lamp."""

    id: str
    name: str
    online: bool = False
    power: bool = False
    brightness: int = Field(default=100, ge=0, le=100, description="Brightness percentage")
    color_temp: int | None = Field(default=None, description="Color temperature in Kelvin")
    mode: str = Field(default="white", description="Current mode: 'white' or 'colour'")
    hue: int | None = Field(default=None, ge=0, le=360, description="Hue in degrees")
    saturation: int | None = Field(
        default=None, ge=0, le=100, description="Saturation percentage"
    )


class LampListResponse(BaseModel):
    """Response for listing all lamps."""

    lamps: list[LampState]


class BrightnessRequest(BaseModel):
    """Request to set brightness."""

    brightness: int = Field(..., ge=0, le=100, description="Brightness percentage (0-100)")


class ColorTempRequest(BaseModel):
    """Request to set color temperature."""

    temperature: int = Field(..., ge=2000, le=7000, description="Color temperature in Kelvin")


class ColorRequest(BaseModel):
    """Request to set RGB color."""

    red: int = Field(..., ge=0, le=255)
    green: int = Field(..., ge=0, le=255)
    blue: int = Field(..., ge=0, le=255)
    brightness: int | None = Field(
        default=None, ge=0, le=100, description="Optional brightness override"
    )


class CommandResponse(BaseModel):
    """Response for lamp control commands."""

    success: bool
    message: str
    lamp_id: str
    state: LampState | None = None
