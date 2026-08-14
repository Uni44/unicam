import logging
import os
import shutil
import struct
import subprocess
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def _project_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _default_fallback_candidates() -> list[str]:
    root = _project_root()
    return [
        os.path.join(root, "img", "hdmi_fallback.png"),
        os.path.join(root, "img", "test.jpg"),
        os.path.join(root, "img", "loading.png"),
        os.path.join(root, "overlay.png"),
    ]


def get_framebuffer_device(candidate_paths=None) -> Optional[str]:
    paths = candidate_paths or ["/dev/fb0", "/dev/fb1", "/dev/fb2"]
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def _write_image_to_framebuffer(image_path: str) -> bool:
    fb_path = get_framebuffer_device()
    if not fb_path:
        raise FileNotFoundError("No se encontró un framebuffer disponible en /dev/fb0")

    with Image.open(image_path) as img:
        fb_width = None
        fb_height = None
        sysfs_path = fb_path.replace("/dev/", "/sys/class/graphics/")
        size_path = os.path.join(sysfs_path, "virtual_size")
        if os.path.exists(size_path):
            with open(size_path, "r", encoding="utf-8") as handle:
                size_value = handle.read().strip()
            parts = [int(part) for part in size_value.split(",") if part.strip()]
            if len(parts) >= 2:
                fb_width, fb_height = parts[0], parts[1]

        bpp_path = os.path.join(sysfs_path, "bits_per_pixel")
        bpp = 32
        if os.path.exists(bpp_path):
            with open(bpp_path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
            try:
                bpp = int(value)
            except ValueError:
                bpp = 32

        if fb_width is None or fb_height is None:
            fb_width, fb_height = img.size

        img = img.convert("RGBA")
        img = img.resize((fb_width, fb_height), Image.LANCZOS)
        rgba = img.tobytes("raw", "RGBA")
        bytes_per_pixel = max(1, bpp // 8)

        with open(fb_path, "r+b") as framebuffer:
            for y in range(fb_height):
                row_start = y * fb_width * 4
                row_end = row_start + fb_width * 4
                row_pixels = rgba[row_start:row_end]
                if bytes_per_pixel == 4:
                    framebuffer.seek(y * fb_width * 4)
                    framebuffer.write(row_pixels)
                elif bytes_per_pixel == 2:
                    pixel_bytes = bytearray()
                    for i in range(0, len(row_pixels), 4):
                        r, g, b, a = row_pixels[i:i + 4]
                        if a < 128:
                            pixel_bytes.extend(struct.pack('<H', 0))
                        else:
                            r5 = int(r / 255 * 31)
                            g6 = int(g / 255 * 63)
                            b5 = int(b / 255 * 31)
                            pixel_bytes.extend(struct.pack('<H', (r5 << 11) | (g6 << 5) | b5))
                    framebuffer.seek(y * fb_width * 2)
                    framebuffer.write(pixel_bytes)
                else:
                    framebuffer.seek(y * fb_width * 3)
                    framebuffer.write(row_pixels[:, :3] if False else b"")

    return True


def resolve_fallback_image_path(cfg=None) -> Optional[str]:
    if cfg is None:
        try:
            from camera_config import load_config
            cfg = load_config()
        except Exception:
            cfg = {}

    image_path = str(cfg.get("hdmi_fallback_image") or "").strip()
    if image_path and os.path.exists(image_path):
        return image_path

    for candidate in _default_fallback_candidates():
        if os.path.exists(candidate):
            return candidate
    return None


def should_show_fallback_image(cfg=None) -> bool:
    if cfg is None:
        try:
            from camera_config import load_config
            cfg = load_config()
        except Exception:
            cfg = {}

    if not bool(cfg.get("hdmi_fallback_enabled", True)):
        return False

    hdmi_value = str(cfg.get("hdmi") or "").strip().lower()
    return hdmi_value in {"off", "none", "no", "disabled", "desactivado", "desconectado"}


def show_fallback_image(cfg=None, force=False) -> bool:
    if not force and not should_show_fallback_image(cfg):
        return False

    image_path = resolve_fallback_image_path(cfg)
    if not image_path:
        logger.warning("No se encontró una imagen de fallback para HDMI")
        return False

    try:
        if _write_image_to_framebuffer(image_path):
            logger.info("Imagen de fallback mostrada directamente en el framebuffer: %s", image_path)
            return True
    except Exception as exc:
        logger.debug("No se pudo escribir directamente al framebuffer: %s", exc)

    try:
        if shutil.which("fbi"):
            subprocess.Popen(
                ["fbi", "-d", "/dev/fb0", "-T", "1", "-a", "-noverbose", image_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Imagen de fallback mostrada con fbi: %s", image_path)
            return True
    except Exception as exc:
        logger.debug("No se pudo usar fbi para la imagen de fallback: %s", exc)

    try:
        if shutil.which("fbv"):
            subprocess.Popen(
                ["fbv", "-f", image_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Imagen de fallback mostrada con fbv: %s", image_path)
            return True
    except Exception as exc:
        logger.debug("No se pudo usar fbv para la imagen de fallback: %s", exc)

    logger.info("No hay un visor de framebuffer disponible; se dejó preparada la imagen de fallback: %s", image_path)
    return True
