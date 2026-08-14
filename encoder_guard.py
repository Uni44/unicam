from __future__ import annotations

from typing import Any, Dict


_PRESET_RANK = {
    "ultrafast": 0,
    "superfast": 1,
    "veryfast": 2,
    "faster": 3,
    "fast": 4,
    "medium": 5,
    "slow": 6,
    "slower": 7,
    "placebo": 8,
}


def _parse_resolution(value: Any):
    if not value:
        return None
    try:
        text = str(value).strip().lower()
        if "x" not in text:
            return None
        width, height = text.split("x", 1)
        return int(width), int(height)
    except Exception:
        return None


def _parse_fps(value: Any, default: int = 24):
    try:
        fps = int(float(str(value).strip()))
    except Exception:
        return default
    return max(5, min(90, fps))


def _get_warning_limits(mode: str) -> Dict[str, Any]:
    defaults = {
        "Grabar": {"resolution": (2560, 1440), "fps": 24, "preset": "superfast"},
        "Stream": {"resolution": (1920, 1080), "fps": 60, "preset": "ultrafast"},
        "Foto": {"resolution": (1920, 1080), "fps": 60, "preset": "ultrafast"},
    }
    return defaults.get(mode, defaults["Stream"])


def evaluate_encoder_warning(config: Dict[str, Any]) -> Dict[str, Any]:
    """Evalúa si la configuración actual supera un umbral de seguridad del encoder."""
    if not config:
        return {"active": False, "level": "info", "message": ""}

    enabled = bool(config.get("encoder_warning_enabled", True))
    if not enabled:
        return {"active": False, "level": "info", "message": ""}

    mode = str(config.get("modo") or "Stream").strip()
    current_resolution = _parse_resolution(config.get("resolution")) or (1920, 1080)
    current_fps = _parse_fps(config.get("fps"), default=30)
    current_preset = str(config.get("preset") or "superfast").strip().lower()

    warning_limit = _get_warning_limits(mode)
    warning_resolution = warning_limit["resolution"]
    warning_fps = warning_limit["fps"]
    warning_preset = warning_limit["preset"]

    current_pixels = current_resolution[0] * current_resolution[1]
    warning_pixels = warning_resolution[0] * warning_resolution[1]

    exceeds_resolution = current_pixels > warning_pixels
    exceeds_fps = current_fps > warning_fps

    if not (exceeds_resolution or exceeds_fps):
        return {"active": False, "level": "info", "message": ""}

    mode_label = "grabación" if mode == "Grabar" else "stream"
    level = "warning"
    message = (
        f"⚠️ Cuidado: la configuración actual de {mode_label} supera el límite recomendado. "
        f"Actual: {current_resolution[0]}x{current_resolution[1]} @ {current_fps} fps con preset {current_preset}. "
        f"Límite: {warning_resolution[0]}x{warning_resolution[1]} @ {warning_fps} fps con preset {warning_preset}. "
        "Puede fallar la codificación o provocar inestabilidad."
    )
    return {"active": True, "level": level, "message": message}
