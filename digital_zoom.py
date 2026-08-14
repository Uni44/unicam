from __future__ import annotations

import math
from typing import Sequence, Tuple


def normalize_zoom_factor(zoom_factor, max_zoom: float = 6.0) -> float:
    """Normaliza el factor de zoom para evitar valores inválidos."""
    try:
        value = float(zoom_factor)
    except (TypeError, ValueError):
        return 1.0

    if not math.isfinite(value):
        return 1.0
    if value <= 1.0:
        return 1.0
    return max(1.0, min(max_zoom, value))


def calculate_effective_digital_zoom_factor(
    total_zoom,
    optical_zoom_max: float = 3.5,
    digital_zoom_max: float = 2.5,
    total_zoom_max: float = 6.0,
) -> float:
    """Calcula el factor digital real a aplicar según el zoom físico y los límites configurados."""
    try:
        total_zoom = float(total_zoom)
    except (TypeError, ValueError):
        return 1.0

    if not math.isfinite(total_zoom):
        return 1.0

    total_zoom = max(1.0, min(total_zoom_max, total_zoom))
    if total_zoom <= optical_zoom_max:
        return 1.0

    return max(1.0, min(digital_zoom_max, total_zoom / optical_zoom_max))


def build_scaler_crop(full_res: Sequence[int] | Tuple[int, int], zoom_factor, center_x: float = 0.5, center_y: float = 0.5):
    """Devuelve un tuple (x, y, crop_w, crop_h) compatible con picamera2 ScalerCrop."""
    if full_res is None:
        raise ValueError("full_res no puede ser None")

    fw, fh = int(full_res[0]), int(full_res[1])
    if fw <= 0 or fh <= 0:
        raise ValueError("full_res debe contener tamaños positivos")

    zoom_factor = normalize_zoom_factor(zoom_factor)
    if zoom_factor <= 1.0:
        return (0, 0, fw, fh)

    crop_w = max(1, int(fw / zoom_factor))
    crop_h = max(1, int(fh / zoom_factor))
    x = int(round(fw * center_x - crop_w / 2.0))
    y = int(round(fh * center_y - crop_h / 2.0))
    x = max(0, min(x, fw - crop_w))
    y = max(0, min(y, fh - crop_h))
    return (x, y, crop_w, crop_h)