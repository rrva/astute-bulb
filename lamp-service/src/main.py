"""FastAPI application for local lamp control."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from .config import load_config
from .lamp_controller import LampManager
from .models import (
    AppConfig,
    BrightnessRequest,
    ColorRequest,
    ColorTempRequest,
    CommandResponse,
    LampListResponse,
    LampState,
    SceneConfig,
    SceneRequest,
)
from .solar import get_solar_lamp_values

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
)
logger = logging.getLogger(__name__)


def configure_uvicorn_logging():
    formatter = logging.Formatter(LOG_FORMAT)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        for handler in uvicorn_logger.handlers:
            handler.setFormatter(formatter)


# Global state
lamp_manager: LampManager | None = None
app_config: AppConfig | None = None
scene_map: dict[str, SceneConfig] = {}


SOLAR_SYNC_INTERVAL = 60  # seconds


async def solar_sync_loop():
    """Background task: update already-on lamps to match solar values every 60 seconds."""
    while True:
        await asyncio.sleep(SOLAR_SYNC_INTERVAL)
        if lamp_manager is None:
            continue
        try:
            brightness, color_temp = get_solar_lamp_values(
                app_config.service.location if app_config else None
            )
            for controller in lamp_manager.get_all_controllers():
                try:
                    if controller.should_skip_for_backoff():
                        continue
                    status = controller.get_status()
                    if status.online and status.power:
                        controller.turn_on_with_scene(brightness, color_temp, source="solar")
                except Exception as e:
                    logger.warning(f"Solar sync failed for {controller.config.id}: {e}")
            logger.info(f"Solar sync: {brightness}% {color_temp}K")
        except Exception as e:
            logger.exception(f"Solar sync error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global lamp_manager, app_config, scene_map

    # Startup
    logger.info("Starting Local Lamps Service...")
    configure_uvicorn_logging()
    try:
        app_config = load_config()
        hold_timeout_seconds = app_config.service.hold_timeout_minutes * 60
        lamp_manager = LampManager(default_hold_timeout=hold_timeout_seconds)

        for lamp_config in app_config.lamps:
            lamp_manager.add_lamp(lamp_config)

        scene_map = {s.name: s for s in app_config.scenes}
        logger.info(f"Loaded {len(app_config.lamps)} lamp(s), {len(scene_map)} scene(s)")
        sync_task = asyncio.create_task(solar_sync_loop())
        logger.info("Solar sync background task started (60s interval)")
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.exception(f"Startup error: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Local Lamps Service...")
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    if lamp_manager:
        lamp_manager.close_all()


app = FastAPI(
    title="Local Lamps Service",
    description="Local control API for Ledvance Sun@Home lamps",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Matterbridge webhooks
app.add_middleware(
    CORSMiddleware,  # type: ignore[invalid-argument-type]  # Starlette ParamSpec
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Request %s %s failed after %.1fms from %s: %s",
            request.method,
            request.url.path,
            duration_ms,
            request.client.host if request.client else "unknown",
            exc,
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Request %s %s -> %s in %.1fms from %s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request.client.host if request.client else "unknown",
    )
    return response


def get_lamp_or_404(lamp_id: str):
    """Get lamp controller or raise 404."""
    if lamp_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    controller = lamp_manager.get_controller(lamp_id)
    if controller is None:
        raise HTTPException(status_code=404, detail=f"Lamp '{lamp_id}' not found")
    return controller


def raise_on_command_failure(success: bool, lamp_id: str, action: str):
    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"{action} failed for lamp '{lamp_id}'",
        )


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    lamps_health = {}
    if lamp_manager:
        for ctrl in lamp_manager.get_all_controllers():
            if ctrl.is_stuck_err914:
                duration = ctrl.err914_duration
                lamps_health[ctrl.config.id] = {
                    "status": "stuck_err914",
                    "err914_count": ctrl._err914_count,
                    "stuck_minutes": round(duration / 60, 1) if duration else 0,
                    "message": "Device needs physical power cycle",
                }
            else:
                lamp_info: dict = {"status": "ok"}
                if ctrl.is_held:
                    lamp_info["hold"] = ctrl.hold_status
                lamps_health[ctrl.config.id] = lamp_info
    return {
        "status": "degraded" if any(v["status"] != "ok" for v in lamps_health.values()) else "ok",
        "lamps": lamps_health,
    }


# List all lamps
@app.get("/lamps", response_model=LampListResponse)
async def list_lamps():
    """List all configured lamps with their current status."""
    if lamp_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    states = lamp_manager.get_all_status()
    return LampListResponse(lamps=states)


# Get lamp status
@app.get("/lamps/{lamp_id}/status", response_model=LampState)
async def get_lamp_status(lamp_id: str):
    """Get the current status of a specific lamp."""
    controller = get_lamp_or_404(lamp_id)
    return controller.get_status()


# Turn lamp on
@app.post("/lamps/{lamp_id}/on", response_model=CommandResponse)
async def turn_on(lamp_id: str):
    """Turn a lamp on with solar-matched brightness and color temperature."""
    controller = get_lamp_or_404(lamp_id)
    brightness, color_temp = get_solar_lamp_values(
        app_config.service.location if app_config else None
    )
    success = controller.turn_on_with_scene(brightness, color_temp)

    return CommandResponse(
        success=success,
        message=f"Lamp on at {brightness}% {color_temp}K" if success else "Failed to turn on lamp",
        lamp_id=lamp_id,
        state=controller.get_status() if success else None,
    )


# Turn lamp off
@app.post("/lamps/{lamp_id}/off", response_model=CommandResponse)
async def turn_off(lamp_id: str):
    """Turn a lamp off."""
    controller = get_lamp_or_404(lamp_id)
    success = controller.turn_off()

    return CommandResponse(
        success=success,
        message="Lamp turned off" if success else "Failed to turn off lamp",
        lamp_id=lamp_id,
        state=controller.get_status() if success else None,
    )


# Set brightness
@app.post("/lamps/{lamp_id}/brightness", response_model=CommandResponse)
async def set_brightness(lamp_id: str, request: BrightnessRequest):
    """Set lamp brightness (0-100%)."""
    controller = get_lamp_or_404(lamp_id)
    success = controller.set_brightness(request.brightness)

    return CommandResponse(
        success=success,
        message=(
            f"Brightness set to {request.brightness}%" if success else "Failed to set brightness"
        ),
        lamp_id=lamp_id,
        state=controller.get_status() if success else None,
    )


# Set color temperature
@app.post("/lamps/{lamp_id}/temperature", response_model=CommandResponse)
async def set_color_temperature(lamp_id: str, request: ColorTempRequest):
    """Set lamp color temperature in Kelvin."""
    controller = get_lamp_or_404(lamp_id)
    success = controller.set_color_temp(request.temperature)

    return CommandResponse(
        success=success,
        message=(
            f"Color temperature set to {request.temperature}K"
            if success
            else "Failed to set color temperature"
        ),
        lamp_id=lamp_id,
        state=controller.get_status() if success else None,
    )


# Set RGB color
@app.post("/lamps/{lamp_id}/color", response_model=CommandResponse)
async def set_color(lamp_id: str, request: ColorRequest):
    """Set lamp RGB color."""
    controller = get_lamp_or_404(lamp_id)
    success = controller.set_color(request.red, request.green, request.blue, request.brightness)

    return CommandResponse(
        success=success,
        message=f"Color set to RGB({request.red},{request.green},{request.blue})"
        if success
        else "Failed to set color",
        lamp_id=lamp_id,
        state=controller.get_status() if success else None,
    )


# Apply named scene
@app.post("/lamps/{lamp_id}/scene", response_model=CommandResponse)
async def apply_scene(lamp_id: str, request: SceneRequest):
    """Apply a named scene (engages solar sync hold)."""
    controller = get_lamp_or_404(lamp_id)
    scene = scene_map.get(request.name)
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scene '{request.name}' not found. Available: {list(scene_map.keys())}",
        )
    timeout = scene.hold_minutes * 60 if scene.hold_minutes is not None else None
    success = controller.set_scene(scene.brightness, scene.color_temp, scene.name, timeout=timeout)

    return CommandResponse(
        success=success,
        message=f"Scene '{scene.name}' applied"
        if success
        else f"Failed to apply scene '{scene.name}'",
        lamp_id=lamp_id,
        state=controller.get_status() if success else None,
    )


# Resume solar sync
@app.post("/lamps/{lamp_id}/resume", response_model=CommandResponse)
async def resume_solar(lamp_id: str):
    """Release solar sync hold and resume circadian auto-adjust."""
    controller = get_lamp_or_404(lamp_id)
    controller.release_hold()

    return CommandResponse(
        success=True,
        message="Solar sync resumed",
        lamp_id=lamp_id,
        state=controller.get_status(),
    )


# ============================================================================
# Matterbridge Webhook Endpoints
# These endpoints are designed to be called by matterbridge-webhooks plugin
# They use GET requests with query parameters for easy webhook configuration
# ============================================================================


# "all" routes must be registered before {lamp_id} to avoid path capture.
@app.get("/webhook/all/scene")
async def webhook_all_scene(
    name: str = Query(..., description="Scene name from config"),
):
    """Apply a named scene to all lamps (for Matterbridge)."""
    if lamp_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    scene = scene_map.get(name)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Scene '{name}' not found")
    timeout = scene.hold_minutes * 60 if scene.hold_minutes is not None else None
    failed = []
    for controller in lamp_manager.get_all_controllers():
        if not controller.set_scene(
            scene.brightness, scene.color_temp, scene.name, timeout=timeout
        ):
            failed.append(controller.config.id)
    if failed:
        raise HTTPException(status_code=502, detail=f"Scene failed for: {failed}")
    return {"success": True}


@app.get("/webhook/all/resume")
async def webhook_all_resume():
    """Release solar sync hold on all lamps (for Matterbridge)."""
    if lamp_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    for controller in lamp_manager.get_all_controllers():
        controller.release_hold()
    return {"success": True}


@app.get("/webhook/{lamp_id}/on")
async def webhook_on(lamp_id: str):
    """Webhook endpoint to turn lamp on with solar values (for Matterbridge)."""
    controller = get_lamp_or_404(lamp_id)
    brightness, color_temp = get_solar_lamp_values(
        app_config.service.location if app_config else None
    )
    success = controller.turn_on_with_scene(brightness, color_temp)
    raise_on_command_failure(success, lamp_id, "turn on")
    return {"success": True}


@app.get("/webhook/{lamp_id}/off")
async def webhook_off(lamp_id: str):
    """Webhook endpoint to turn lamp off (for Matterbridge)."""
    controller = get_lamp_or_404(lamp_id)
    success = controller.turn_off()
    raise_on_command_failure(success, lamp_id, "turn off")
    return {"success": True}


@app.get("/webhook/{lamp_id}/brightness")
async def webhook_brightness(
    lamp_id: str,
    level: int = Query(..., ge=0, le=100, description="Brightness level 0-100"),
):
    """Webhook endpoint to set brightness (for Matterbridge).

    Matterbridge sends ${LEVEL} which is 0-100.
    """
    controller = get_lamp_or_404(lamp_id)
    success = controller.set_brightness(level)
    raise_on_command_failure(success, lamp_id, "set brightness")
    return {"success": True}


@app.get("/webhook/{lamp_id}/temperature")
async def webhook_temperature(
    lamp_id: str,
    kelvin: int = Query(default=None, description="Color temperature in Kelvin"),
    mired: int = Query(default=None, description="Color temperature in Mired"),
):
    """Webhook endpoint to set color temperature (for Matterbridge).

    Matterbridge can send ${KELVIN} or ${MIRED}.
    Mired = 1,000,000 / Kelvin
    """
    controller = get_lamp_or_404(lamp_id)

    if kelvin is not None:
        temp = kelvin
    elif mired is not None:
        temp = int(1_000_000 / mired) if mired > 0 else 4000
    else:
        raise HTTPException(status_code=400, detail="Either kelvin or mired required")

    # Clamp to valid range
    temp = max(controller.config.min_color_temp, min(controller.config.max_color_temp, temp))
    success = controller.set_color_temp(temp)
    raise_on_command_failure(success, lamp_id, "set color temperature")
    return {"success": True}


@app.get("/webhook/{lamp_id}/color")
async def webhook_color(
    lamp_id: str,
    red: int = Query(default=None, ge=0, le=255),
    green: int = Query(default=None, ge=0, le=255),
    blue: int = Query(default=None, ge=0, le=255),
    hue: int = Query(default=None, ge=0, le=360, description="Hue in degrees"),
    saturation: int = Query(default=None, ge=0, le=100, description="Saturation 0-100"),
    level: int = Query(default=None, ge=0, le=100, description="Brightness level"),
):
    """Webhook endpoint to set color (for Matterbridge).

    Accepts either RGB (red, green, blue) or HSV (hue, saturation, level).
    Matterbridge can send ${HUE}, ${SATURATION}, or ${red}, ${green}, ${blue}.
    """
    import colorsys

    controller = get_lamp_or_404(lamp_id)

    # If RGB provided, use directly
    if red is not None and green is not None and blue is not None:
        success = controller.set_color(red, green, blue, level)
        raise_on_command_failure(success, lamp_id, "set color")
        return {"success": True}

    # If HSV provided, convert to RGB
    if hue is not None and saturation is not None:
        # Convert HSV to RGB
        h = hue / 360
        s = saturation / 100
        v = (level if level is not None else 100) / 100
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        red, green, blue = int(r * 255), int(g * 255), int(b * 255)
        success = controller.set_color(red, green, blue, level)
        raise_on_command_failure(success, lamp_id, "set color")
        return {"success": True}

    raise HTTPException(status_code=400, detail="Either RGB or HSV values required")


@app.get("/webhook/{lamp_id}/scene")
async def webhook_scene(
    lamp_id: str,
    name: str = Query(..., description="Scene name from config"),
):
    """Webhook endpoint to apply a named scene (for Matterbridge)."""
    controller = get_lamp_or_404(lamp_id)
    scene = scene_map.get(name)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Scene '{name}' not found")
    timeout = scene.hold_minutes * 60 if scene.hold_minutes is not None else None
    success = controller.set_scene(scene.brightness, scene.color_temp, scene.name, timeout=timeout)
    raise_on_command_failure(success, lamp_id, f"apply scene '{name}'")
    return {"success": True}


@app.get("/webhook/{lamp_id}/resume")
async def webhook_resume(lamp_id: str):
    """Webhook endpoint to release solar sync hold (for Matterbridge)."""
    controller = get_lamp_or_404(lamp_id)
    controller.release_hold()
    return {"success": True}


def main():
    """Run the application."""
    import uvicorn

    config = load_config()
    uvicorn.run(
        "src.main:app",
        host=config.service.host,
        port=config.service.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
