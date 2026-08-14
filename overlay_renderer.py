import time
import threading
import os
import math
import shutil
import socket
import subprocess
import ipaddress
from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont

try:
    import psutil
except Exception:  # pragma: no cover - entorno sin psutil
    psutil = None

try:
    from camera_config import CONFIG, load_config, resolve_storage_dir, get_storage_base_path
except Exception:  # pragma: no cover - entorno sin cámara disponible
    CONFIG = {}
    load_config = None
    resolve_storage_dir = None
    get_storage_base_path = None

try:
    import gpio_control as gpio_control_module
except Exception:  # pragma: no cover - entorno sin gpio_control
    gpio_control_module = None

try:
    from wifi_manager import get_wifi_device_status
except Exception:  # pragma: no cover - entorno sin wifi_manager
    get_wifi_device_status = None

try:
    from ups_driver import INA219
except Exception:  # pragma: no cover - entorno sin ups_driver
    INA219 = None

try:
    from network_monitor import NetworkMonitor
except Exception:  # pragma: no cover - entorno sin network_monitor
    NetworkMonitor = None

sensor_ups = None

# Instancia cacheada de INA219 para el fallback local (fix #4): evita crear
# un sensor I2C nuevo en cada render si no hay sensor_ups global disponible.
_local_ina219 = None
_local_ina219_failed = False


# ---------------------------------------------------------------------------
# Helpers de dibujo
# ---------------------------------------------------------------------------

def draw_text_outline(draw, position, text, font, fill="white", outline="black", stroke_width=1):
    """Dibuja texto con contorno usando el soporte nativo de PIL/FreeType
    (stroke_width/stroke_fill) en vez de 9 llamadas manuales a draw.text con
    offsets. Es la misma idea visual (texto + contorno) pero resuelta en una
    sola pasada de rasterizado en vez de 9, que era el mayor consumidor de
    CPU del overlay (ver profiling: draw_text_outline / ImageDraw.text)."""
    draw.text(position, text, font=font, fill=fill,
              stroke_width=stroke_width, stroke_fill=outline)


class OverlayRenderer:
    # Configuración de widgets por defecto: todos visibles.
    DEFAULT_OVERLAY_CONFIG = {
        "show_rec": True,
        "show_timer": True,
        "show_video": True,
        "show_focus": True,
        "show_white_balance": True,
        "show_zoom": True,
        "show_storage": True,
        "show_battery": True,
        "show_network": True,
        "show_audio": True,
        "show_camera": True,
        "show_thirds": True,
    }

    def __init__(self, width=1920, height=1080, out_path=None, overlay=None, overlay_scale=1.8):
        self.width = width
        self.height = height
        self.out_path = out_path or os.path.join(os.path.dirname(__file__), "overlay.png")

        # Configuración de qué widgets se dibujan.
        self.overlay = dict(self.DEFAULT_OVERLAY_CONFIG)
        if overlay:
            self.overlay.update(overlay)

        # `overlay_scale` es un multiplicador manual encima del escalado por
        # resolución: 1.0 = tamaño de referencia, 1.5 = HUD 50% más grande,
        # útil si el texto se ve chico independientemente de la resolución.
        self.overlay_scale = max(overlay_scale, 0.1)

        # Todas las medidas escalan respecto a un diseño de referencia 1920px
        # de ancho, así el HUD se ve consistente en cualquier resolución, y
        # además se multiplican por `overlay_scale`.
        self.scale = max(self.width / 1920.0, 0.3) * self.overlay_scale

        self._load_fonts()

        # Geometría base reutilizada por los distintos widgets.
        self.margin = int(24 * self.scale)
        self.line_h = int(28 * self.scale)
        self.icon_s = int(16 * self.scale)

        # Tamaños de icono e interlineado de grupo, reutilizados por el HUD.
        self.icon_sm = max(int(18 * self.scale), 10)
        self.icon_md = max(int(24 * self.scale), 12)
        self.stroke_w = max(int(2 * self.scale), 1)
        # Separación extra entre el grupo WB/AF y el grupo de storage, para
        # que se lean como dos bloques de información distintos.
        self.group_gap = int(self.line_h * 0.55)

        # Estado interno para el contador de grabación/streaming.
        self._timer_active = False
        self._timer_started_at = None

        # Monitor de red en background para no bloquear la renderización.
        self._network_monitor = None
        self._init_network_monitor()

        # --- Caches (fixes #3 y #5) ---------------------------------------
        # Config runtime: se releía del disco hasta 5 veces por render
        # (build_live_state + _get_focus_mode + _get_zoom_value +
        # _get_storage_info llamaban cada una a _runtime_config). Con TTL de
        # 1s seguimos teniendo datos frescos en cada vuelta del overlay
        # (que ya corre a 1s) pero sin repetir I/O + json.loads 5 veces.
        self._cfg_cache = None
        self._cfg_cache_at = 0.0
        self._cfg_cache_ttl = 1.0

        # Storage: shutil.disk_usage es una syscall (statvfs) que no hace
        # falta repetir cada segundo, el espacio libre no cambia tan rápido.
        self._storage_cache = None
        self._storage_cache_at = 0.0
        self._storage_cache_ttl = 5.0

        # Capa de "regla de tercios" (fix #6): las 4 líneas son siempre
        # iguales para un width/height dado, así que se renderizan una sola
        # vez y se componen por encima en cada frame en vez de recalcularlas.
        self._thirds_layer = None

    def _load_fonts(self):
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        sizes = {
            "small": max(int(16 * self.scale), 10),
            "med": max(int(20 * self.scale), 12),
            "big": max(int(26 * self.scale), 14),
        }
        try:
            self.font_small = ImageFont.truetype(font_path, sizes["small"])
            self.font_med = ImageFont.truetype(font_path, sizes["med"])
            self.font_big = ImageFont.truetype(font_path, sizes["big"])
        except Exception:
            self.font_small = ImageFont.load_default()
            self.font_med = ImageFont.load_default()
            self.font_big = ImageFont.load_default()

    def _init_network_monitor(self):
        if NetworkMonitor is None:
            return
        try:
            self._network_monitor = NetworkMonitor(
                get_config=self._runtime_config,
                extract_host=self._extract_host,
                classify_kind=self._classify_network_kind,
                wifi_status_fn=get_wifi_device_status,
                interval=4.0,
                ping_count=3,
                smoothing=2,
            )
            self._network_monitor.start()
        except Exception:
            self._network_monitor = None

    # -- utilidades de medición / alineación ---------------------------------

    @staticmethod
    def _text_size(draw, text, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _draw_text_right(self, draw, right_x, y, text, font, **kw):
        tw, _ = self._text_size(draw, text, font)
        draw_text_outline(draw, (right_x - tw, y), text, font, **kw)

    def _draw_text_center(self, draw, center_x, y, text, font, **kw):
        tw, _ = self._text_size(draw, text, font)
        draw_text_outline(draw, (center_x - tw // 2, y), text, font, **kw)

    # -- composición icono + texto -------------------------------------------
    # Estos tres helpers dibujan un ícono vectorial pegado a un texto,
    # anclados a izquierda / derecha / centro respectivamente. `icon_fn`
    # siempre tiene la firma `icon_fn(draw, x, y, size)`.

    def _icon_gap(self):
        return int(6 * self.scale)

    def _draw_icon_text_left(self, draw, x, y, icon_fn, icon_size, text, font, **kw):
        gap = self._icon_gap()
        icon_y = y + (font.size - icon_size) // 2
        icon_fn(draw, x, icon_y, icon_size)
        text_x = x + icon_size + gap
        draw_text_outline(draw, (text_x, y), text, font, **kw)
        tw, _ = self._text_size(draw, text, font)
        return text_x + tw

    def _draw_icon_text_right(self, draw, right_x, y, icon_fn, icon_size, text, font, **kw):
        gap = self._icon_gap()
        tw, _ = self._text_size(draw, text, font)
        text_x = right_x - tw
        icon_x = text_x - gap - icon_size
        icon_y = y + (font.size - icon_size) // 2
        icon_fn(draw, icon_x, icon_y, icon_size)
        draw_text_outline(draw, (text_x, y), text, font, **kw)
        return icon_x

    def _draw_icon_text_center(self, draw, center_x, y, icon_fn, icon_size, text, font, **kw):
        gap = self._icon_gap()
        tw, _ = self._text_size(draw, text, font)
        total_w = icon_size + gap + tw
        start_x = center_x - total_w // 2
        icon_y = y + (font.size - icon_size) // 2
        icon_fn(draw, start_x, icon_y, icon_size)
        draw_text_outline(draw, (start_x + icon_size + gap, y), text, font, **kw)
        return start_x

    # -------------------------------------------------------------------
    # Íconos vectoriales — todos autocontenidos (sin assets externos),
    # dibujados dentro de un "chip" circular/redondeado semitransparente
    # para que se lean bien sobre cualquier fondo de video.
    # -------------------------------------------------------------------

    def _icon_badge(self, draw, x, y, w, h, shape="circle", bg=(0, 0, 0, 130)):
        if shape == "circle":
            draw.ellipse((x, y, x + w, y + h), fill=bg)
        else:
            radius = max(int(3 * self.scale), 2)
            draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=bg)
        pad = max(int(2 * self.scale), 1)
        return (x + pad, y + pad, x + w - pad, y + h - pad)

    def _icon_clock(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = (x1 - x0) / 2
        draw.ellipse((x0, y0, x1, y1), outline=color, width=self.stroke_w)
        draw.line((cx, cy, cx, cy - r * 0.55), fill=color, width=self.stroke_w)
        draw.line((cx, cy, cx + r * 0.4, cy + r * 0.15), fill=color, width=self.stroke_w)

    def _icon_camera(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, shape="rounded")
        w, h = x1 - x0, y1 - y0
        body_top = y0 + h * 0.30
        draw.rounded_rectangle((x0, body_top, x1, y1), radius=max(int(2 * self.scale), 1),
                                outline=color, width=self.stroke_w)
        vf_w = w * 0.34
        draw.rectangle((x0 + w * 0.18, y0, x0 + w * 0.18 + vf_w, body_top), outline=color, width=self.stroke_w)
        lr = h * 0.20
        draw.ellipse((x0 + w / 2 - lr, body_top + (y1 - body_top) / 2 - lr,
                       x0 + w / 2 + lr, body_top + (y1 - body_top) / 2 + lr),
                      outline=color, width=self.stroke_w)

    def _icon_sun(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = (x1 - x0) * 0.24
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=self.stroke_w)
        ray_r0 = r * 1.5
        ray_r1 = r * 2.15
        for i in range(8):
            ang = math.radians(i * 45)
            lx0 = cx + ray_r0 * math.cos(ang)
            ly0 = cy + ray_r0 * math.sin(ang)
            lx1 = cx + ray_r1 * math.cos(ang)
            ly1 = cy + ray_r1 * math.sin(ang)
            draw.line((lx0, ly0, lx1, ly1), fill=color, width=self.stroke_w)

    def _icon_thermo(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s)
        w, h = x1 - x0, y1 - y0
        cx = (x0 + x1) / 2
        bulb_r = w * 0.16
        bulb_cy = y1 - bulb_r - h * 0.08
        stem_top = y0 + h * 0.12
        draw.ellipse((cx - bulb_r, bulb_cy - bulb_r, cx + bulb_r, bulb_cy + bulb_r), fill=color)
        draw.rounded_rectangle((cx - w * 0.08, stem_top, cx + w * 0.08, bulb_cy),
                                radius=max(int(2 * self.scale), 1), outline=color, width=self.stroke_w)

    def _icon_focus(self, draw, x, y, s, color=(255, 255, 255, 255), filled=True):
        """Corchetes de encuadre AF; punto lleno = autofoco, guion = manual."""
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, shape="rounded")
        w, h = x1 - x0, y1 - y0
        cl = w * 0.28
        pad = w * 0.12
        corners = [
            (x0 + pad, y0 + pad, 1, 1),
            (x1 - pad, y0 + pad, -1, 1),
            (x0 + pad, y1 - pad, 1, -1),
            (x1 - pad, y1 - pad, -1, -1),
        ]
        for cx, cy, sx, sy in corners:
            draw.line((cx, cy, cx + sx * cl, cy), fill=color, width=self.stroke_w)
            draw.line((cx, cy, cx, cy + sy * cl), fill=color, width=self.stroke_w)
        ccx, ccy = (x0 + x1) / 2, (y0 + y1) / 2
        if filled:
            dr = max(w * 0.07, 2)
            draw.ellipse((ccx - dr, ccy - dr, ccx + dr, ccy + dr), fill=color)
        else:
            draw.line((ccx - w * 0.12, ccy, ccx + w * 0.12, ccy), fill=color, width=self.stroke_w)

    def _icon_zoom(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s)
        w, h = x1 - x0, y1 - y0
        r = w * 0.28
        cx, cy = x0 + w * 0.40, y0 + h * 0.40
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=self.stroke_w)
        draw.line((cx + r * 0.7, cy + r * 0.7, x1 - w * 0.12, y1 - h * 0.12), fill=color, width=self.stroke_w + 1)
        draw.line((cx - r * 0.5, cy, cx + r * 0.5, cy), fill=color, width=max(self.stroke_w - 1, 1))
        draw.line((cx, cy - r * 0.5, cx, cy + r * 0.5), fill=color, width=max(self.stroke_w - 1, 1))

    def _icon_digital_zoom(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, shape="rounded")
        w, h = x1 - x0, y1 - y0
        r = w * 0.25
        cx, cy = x0 + w * 0.40, y0 + h * 0.40
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=self.stroke_w)
        draw.line((cx + r * 0.72, cy + r * 0.72, x1 - w * 0.12, y1 - h * 0.12), fill=color, width=self.stroke_w + 1)
        draw.line((x0 + w * 0.22, y1 - h * 0.24, x1 - w * 0.22, y1 - h * 0.24), fill=color, width=max(self.stroke_w - 1, 1))
        draw.ellipse((cx + w * 0.12, cy - h * 0.12, cx + w * 0.20, cy - h * 0.04), fill=color)

    def _icon_drive(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, shape="rounded")
        w, h = x1 - x0, y1 - y0
        body_y0 = y0 + h * 0.20
        body_y1 = y1 - h * 0.12
        draw.rounded_rectangle((x0 + w * 0.08, body_y0, x1 - w * 0.08, body_y1),
                                radius=max(int(2 * self.scale), 1), outline=color, width=self.stroke_w)
        led_y = body_y1 - (body_y1 - body_y0) * 0.28
        for dx in (0.28, 0.52):
            lr = max(w * 0.035, 1)
            lcx = x0 + w * dx
            draw.ellipse((lcx - lr, led_y - lr, lcx + lr, led_y + lr), fill=color)

    def _icon_mic(self, draw, x, y, s, color=(255, 255, 255, 255), muted=False):
        badge_color = (120, 0, 0, 150) if muted else (0, 0, 0, 130)
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, bg=badge_color)
        w, h = x1 - x0, y1 - y0
        c = (255, 90, 90, 255) if muted else color
        cx = (x0 + x1) / 2
        cap_w = w * 0.26
        cap_top = y0 + h * 0.14
        cap_bot = y0 + h * 0.55
        draw.rounded_rectangle((cx - cap_w / 2, cap_top, cx + cap_w / 2, cap_bot),
                                radius=cap_w / 2, outline=c, width=self.stroke_w)
        stand_r = w * 0.22
        stand_cy = cap_bot - (cap_bot - cap_top) * 0.15
        draw.arc((cx - stand_r, stand_cy - stand_r, cx + stand_r, stand_cy + stand_r), 20, 160,
                  fill=c, width=self.stroke_w)
        base_y = min(y1 - h * 0.10, stand_cy + stand_r * 0.9)
        draw.line((cx, stand_cy + stand_r * 0.75, cx, base_y), fill=c, width=self.stroke_w)
        draw.line((cx - w * 0.16, base_y, cx + w * 0.16, base_y), fill=c, width=self.stroke_w)
        if muted:
            draw.line((x0 + w * 0.12, y0 + h * 0.12, x1 - w * 0.12, y1 - h * 0.12), fill=c, width=self.stroke_w + 1)

    def _icon_wifi(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s)
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, y1 - h * 0.20
        dr = max(w * 0.06, 1.5)
        draw.ellipse((cx - dr, cy - dr, cx + dr, cy + dr), fill=color)
        for r in (w * 0.22, w * 0.36):
            bbox = (cx - r, cy - r, cx + r, cy + r)
            draw.arc(bbox, 210, 330, fill=color, width=self.stroke_w)

    def _icon_lan(self, draw, x, y, s, color=(255, 255, 255, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, shape="rounded")
        w, h = x1 - x0, y1 - y0
        body = (x0 + w * 0.22, y0 + h * 0.28, x1 - w * 0.22, y1 - h * 0.30)
        draw.rectangle(body, outline=color, width=self.stroke_w)
        for dx in (0.34, 0.5, 0.66):
            px = x0 + w * dx
            draw.line((px, body[3], px, body[3] + h * 0.16), fill=color, width=self.stroke_w)

    def _icon_offline(self, draw, x, y, s, color=(255, 90, 90, 255)):
        x0, y0, x1, y1 = self._icon_badge(draw, x, y, s, s, bg=(90, 0, 0, 130))
        pad_w = (x1 - x0) * 0.24
        pad_h = (y1 - y0) * 0.24
        draw.line((x0 + pad_w, y0 + pad_h, x1 - pad_w, y1 - pad_h), fill=color, width=self.stroke_w + 1)
        draw.line((x0 + pad_w, y1 - pad_h, x1 - pad_w, y0 + pad_h), fill=color, width=self.stroke_w + 1)

    # -------------------------------------------------------------------
    # Guía de composición
    # -------------------------------------------------------------------

    def draw_rule_of_thirds(self, draw, state=None):
        """Grilla de regla de tercios: 2 líneas verticales + 2 horizontales,
        finas y semitransparentes, típicas de los HUD de cámara para ayudar
        a encuadrar. No lleva texto ni afecta al resto de los widgets."""
        line_color = (255, 255, 255, 90)
        line_w = max(int(2 * self.scale), 2)

        x1 = self.width // 3
        x2 = (self.width * 2) // 3
        y1 = self.height // 3
        y2 = (self.height * 2) // 3

        draw.line([(x1, 0), (x1, self.height)], fill=line_color, width=line_w)
        draw.line([(x2, 0), (x2, self.height)], fill=line_color, width=line_w)
        draw.line([(0, y1), (self.width, y1)], fill=line_color, width=line_w)
        draw.line([(0, y2), (self.width, y2)], fill=line_color, width=line_w)

    def _get_thirds_layer(self):
        """Fix #6: la grilla de tercios es siempre igual para un
        width/height dado (no depende de `state`), así que se renderiza una
        sola vez y se cachea, en vez de recalcular 4 líneas por frame."""
        if self._thirds_layer is None:
            layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            self.draw_rule_of_thirds(ImageDraw.Draw(layer))
            self._thirds_layer = layer
        return self._thirds_layer

    # -------------------------------------------------------------------
    # Widgets individuales — cada uno dibuja SOLO su propio elemento.
    # -------------------------------------------------------------------

    def draw_rec(self, draw, state, frame_count=0):
        """● REC (parpadeante) arriba a la izquierda, o LIVE si transmite."""
        recording = bool(state.get("recording", False))
        streaming = bool(state.get("streaming", False))
        x, y = self.margin, self.margin
        dot_r = int(6 * self.scale)

        if recording:
            blink_on = (frame_count // 15) % 2 == 0
            dot_color = (255, 40, 40, 255) if blink_on else (120, 0, 0, 255)
            label = "REC"
        elif streaming:
            blink_on = (frame_count // 15) % 2 == 0
            dot_color = (80, 200, 80, 255) if blink_on else (120, 0, 0, 255)
            label = "LIVE"
        else:
            dot_color = (150, 150, 150, 255)
            label = "STBY"

        cy = y + self.font_med.size // 2
        draw.ellipse((x, cy - dot_r, x + dot_r * 2, cy + dot_r), fill=dot_color, outline="black")
        draw_text_outline(draw, (x + dot_r * 2 + int(8 * self.scale), y), label, self.font_med)

    def draw_timer(self, draw, state):
        """Reloj + timer de grabación arriba a la derecha."""
        timer_text = state.get("timer", "00:00:00")
        self._draw_icon_text_right(draw, self.width - self.margin, self.margin,
                                    self._icon_clock, self.icon_sm, timer_text, self.font_med)

    @staticmethod
    def _resolve_video_format(width, height):
        """Convierte una resolución en una etiqueta legible para el HUD."""
        width = max(int(width or 0), 0)
        height = max(int(height or 0), 0)
        max_dim = max(width, height)

        if max_dim >= 7680:
            return "8K"
        if max_dim >= 3840:
            return "4K"
        if max_dim >= 2560:
            return "2K"
        if max_dim >= 2048:
            return "QHD"
        if max_dim >= 1280:
            return "HD"
        return "FHD"

    def draw_video(self, draw, state):
        """Cámara + formato/fps (ej. 'FHD  30p') arriba centrado."""
        video = state.get("video", {}) or {}
        fmt = video.get("format", "FHD")
        fps = video.get("fps", 30)
        text = f"{fmt}   {fps}p"
        self._draw_icon_text_center(draw, self.width // 2, self.margin,
                                     self._icon_camera, self.icon_sm, text, self.font_med)

    def _row_y(self, row_from_bottom):
        """Y del borde superior de una fila del stack derecho (cámara / red /
        batería), contando filas desde abajo (0 = la más pegada al borde
        inferior). Todas las filas miden `line_h`."""
        return self.height - self.margin - (row_from_bottom + 1) * self.line_h

    def _storage_row_y(self, row_from_bottom):
        """Y de una fila del bloque de STORAGE (bottom-left, 2 filas)."""
        return self.height - self.margin - (row_from_bottom + 1) * self.line_h

    def _wbaf_row_y(self, row_from_group_bottom):
        """Y de una fila del grupo WB/AF, ubicado arriba del bloque de
        storage con un `group_gap` de separación visual, para que se lean
        como dos bloques de información independientes. row 0 = AF (pegado
        al gap), row 1 = WB (arriba de AF)."""
        storage_top = self._storage_row_y(1)
        base = storage_top - self.group_gap - self.line_h
        return base - row_from_group_bottom * self.line_h

    def draw_white_balance(self, draw, state):
        """AWB (sol) o temperatura en Kelvin (termómetro). Grupo WB/AF,
        fila superior."""
        wb = state.get("white_balance", {}) or {}
        auto = wb.get("auto", True)
        text = "AWB" if auto else f"{wb.get('kelvin', 5600)}K"
        icon_fn = self._icon_sun if auto else self._icon_thermo
        self._draw_icon_text_left(draw, self.margin, self._wbaf_row_y(1),
                                   icon_fn, self.icon_sm, text, self.font_small)

    def draw_focus(self, draw, state):
        """Modo de foco (AF-C / AF-S / MF) con corchetes de encuadre. Grupo
        WB/AF, fila inferior (pegada al gap con storage)."""
        focus = state.get("focus", {}) or {}
        mode = focus.get("mode", "AF-C")
        filled = mode not in ("MF", "manual")

        def icon_fn(d, ix, iy, s):
            self._icon_focus(d, ix, iy, s, filled=filled)

        self._draw_icon_text_left(draw, self.margin, self._wbaf_row_y(0),
                                   icon_fn, self.icon_sm, mode, self.font_small)

    def _get_zoom_speed_mode(self):
        if gpio_control_module is None:
            return "slow"
        return getattr(gpio_control_module, "ZOOM_SPEED_MODE", "slow")

    def draw_zoom(self, draw, state):
        """Nivel de zoom con indicador visual cuando el zoom digital está activo."""
        zoom = state.get("zoom", 1)
        speed = state.get("zoom_speed_mode")
        digital_active = bool(state.get("digital_zoom_active", False))
        text = f"x{float(zoom):.1f}"
        if speed:
            text += f" {speed.upper()}"
        if digital_active:
            text += " DIG"
        y = self._storage_row_y(0)
        icon_fn = self._icon_digital_zoom if digital_active else self._icon_zoom
        self._draw_icon_text_center(draw, self.width // 2, y,
                                     icon_fn, self.icon_md, text, self.font_med)

    def draw_storage(self, draw, state):
        """Disco + dispositivo/espacio libre (fila 1) y tiempo restante
        debajo, indentado bajo el ícono (fila 0). Bottom-left, bloque propio
        separado del grupo WB/AF por `group_gap`."""
        storage = state.get("storage", {}) or {}
        device = storage.get("device", "USB")
        free_gb = storage.get("free_gb", 0)
        remaining = storage.get("remaining", "--")

        line1 = f"{device} {free_gb}GB"
        line2 = remaining

        self._draw_icon_text_left(draw, self.margin, self._storage_row_y(1),
                                   self._icon_drive, self.icon_sm, line1, self.font_small)
        indent = self.icon_sm + self._icon_gap()
        draw_text_outline(draw, (self.margin + indent, self._storage_row_y(0)), line2, self.font_small)

    def draw_battery(self, draw, state):
        """Icono de batería + porcentaje, con patrones claros para carga,
        descarga, idle y error del sensor."""
        battery = state.get("battery", {}) or {}
        percent = max(0, min(100, battery.get("percent", 100)))
        status = str(battery.get("status") or battery.get("power_state") or "").lower()
        charging = status in ("charging", "cargando")
        discharging = status == "discharging"
        idle = status in ("idle", "online")
        error = status in ("error", "sensor_error", "unknown")

        body_w = int(30 * self.scale)
        body_h = int(14 * self.scale)
        nub_w = max(int(3 * self.scale), 2)

        y = self._row_y(2)
        right_x = self.width - self.margin
        body_x0 = right_x - body_w - nub_w

        fill_color = (255, 60, 60, 255) if percent <= 15 else (255, 255, 255, 255)

        draw.rounded_rectangle(
            [body_x0, y, body_x0 + body_w, y + body_h],
            radius=2, outline="white", width=2
        )
        nub_h = body_h // 2
        draw.rectangle(
            [body_x0 + body_w, y + (body_h - nub_h) // 2, body_x0 + body_w + nub_w, y + (body_h - nub_h) // 2 + nub_h],
            fill="white"
        )
        inner_pad = 2
        fill_w = int((body_w - inner_pad * 2) * (percent / 100.0))
        if fill_w > 0:
            draw.rectangle(
                [body_x0 + inner_pad, y + inner_pad, body_x0 + inner_pad + fill_w, y + body_h - inner_pad],
                fill=fill_color
            )

        if charging:
            cx = body_x0 + body_w / 2
            cy = y + body_h / 2
            bolt = [
                (cx - body_w * 0.08, y - 1), (cx + body_w * 0.06, cy - 1),
                (cx - body_w * 0.02, cy - 1), (cx + body_w * 0.08, y + body_h + 1),
                (cx - body_w * 0.06, cy + 1), (cx + body_w * 0.02, cy + 1),
            ]
            draw.polygon(bolt, fill=(255, 220, 60, 255), outline=(0, 0, 0, 255))
        elif discharging:
            label_x = body_x0 + body_w / 2
            label_y = y + body_h / 2
            draw.text((label_x - 3 * self.scale, label_y - 6 * self.scale), "-", fill="white", font=self.font_small, stroke_width=1, stroke_fill="black")
        elif error:
            draw.text((body_x0 + 7 * self.scale, y - 1), "!", fill=(255, 120, 120, 255), font=self.font_small, stroke_width=1, stroke_fill="black")

        if charging:
            suffix = "CHG"
        elif discharging:
            suffix = "DIS"
        elif idle:
            suffix = "IDLE"
        elif error:
            suffix = "ERR"
        else:
            suffix = ""

        label = f"{percent}%{suffix}"
        self._draw_text_right(draw, body_x0 - int(6 * self.scale), y - int(2 * self.scale), label, self.font_small)

    def draw_network(self, draw, state):
        """Ícono de tipo de red (wifi / lan / offline) + barras de señal +
        texto de estado. Abajo a la derecha."""
        network = state.get("network", {}) or {}
        quality = max(0, min(5, network.get("quality", 0)))
        kind = str(network.get("kind", "OFFLINE") or "OFFLINE").upper()

        n_bars = 5
        bar_w = max(int(4 * self.scale), 3)
        gap = max(int(2 * self.scale), 2)
        max_h = int(16 * self.scale)
        min_h = int(5 * self.scale)

        y = self._row_y(1)
        total_w = n_bars * bar_w + (n_bars - 1) * gap
        x0 = self.width - self.margin - total_w
        base_y = y + max_h

        for i in range(n_bars):
            bar_h = min_h + int((max_h - min_h) * (i + 1) / n_bars)
            filled = i < quality
            color = (255, 255, 255, 255) if filled else (110, 110, 110, 180)
            bx = x0 + i * (bar_w + gap)
            draw.rectangle([bx, base_y - bar_h, bx + bar_w, base_y], fill=color)

        label = kind if kind in {"LAN", "WAN", "WIFI", "OFFLINE"} else kind
        label_y = y + int(2 * self.scale)
        self._draw_text_right(draw, x0 - int(8 * self.scale), label_y, label, self.font_small)

        if kind == "WIFI":
            icon_fn = self._icon_wifi
        elif kind in ("LAN", "WAN"):
            icon_fn = self._icon_lan
        else:
            icon_fn = self._icon_offline
        tw, _ = self._text_size(draw, label, self.font_small)
        icon_right_edge = x0 - int(8 * self.scale) - tw - self._icon_gap()
        icon_y = label_y + (self.font_small.size - self.icon_sm) // 2
        icon_fn(draw, icon_right_edge - self.icon_sm, icon_y, self.icon_sm)

    def draw_camera_number(self, draw, state):
        """Cámara + etiqueta 'CAM1' / 'CAM2'. Abajo a la derecha."""
        camera = state.get("camera", {}) or {}
        number = camera.get("number", 1)
        text = f"CAM {number}"
        y = self._row_y(0)
        self._draw_icon_text_right(draw, self.width - self.margin, y,
                                    self._icon_camera, self.icon_sm, text, self.font_small)

    def draw_audio_meter(self, draw, state):
        """Mic + dB, barra y modo tachado (X) si no hay entrada de audio."""
        audio = state.get("audio", {}) or {}
        configured = bool(audio.get("configured", False))
        valid = bool(audio.get("valid", False)) or configured
        db = float(audio.get("db", -80.0))
        level = int(max(0, min(100, audio.get("level", 0))))

        bar_w = int(320 * self.scale)
        bar_h = max(int(18 * self.scale), 12)
        x = self.width - self.margin - bar_w
        y = self._row_y(5)
        label_y = y
        bar_y = y + self.font_med.size + int(6 * self.scale)
        right_x = self.width - self.margin

        def icon_fn(d, ix, iy, s):
            self._icon_mic(d, ix, iy, s, muted=not valid)

        if not valid:
            label = "MIC X"
            self._draw_icon_text_right(draw, right_x, label_y, icon_fn, self.icon_md, label,
                                        self.font_med, fill=(255, 80, 80, 255), outline="black")
            return

        label = f"MIC {db:+.1f} dB"
        self._draw_icon_text_right(draw, right_x, label_y, icon_fn, self.icon_md, label, self.font_med)

        bar_x0 = x
        bar_x1 = x + bar_w
        bar_color = (120, 220, 120, 255)
        if level >= 95:
            bar_color = (255, 40, 40, 255)
        elif level >= 80:
            bar_color = (255, 170, 0, 255)

        fill_w = int((level / 100.0) * bar_w)
        draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], fill=(50, 50, 50, 200), outline=(220, 220, 220, 200), width=1)
        if fill_w > 0:
            draw.rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + bar_h], fill=bar_color)

        red_zone_start = bar_x0 + int(bar_w * 0.90)
        draw.line([red_zone_start, bar_y, red_zone_start, bar_y + bar_h], fill=(255, 0, 0, 220), width=max(int(2 * self.scale), 1))
        self._draw_text_right(draw, right_x, bar_y - int(2 * self.scale), f"{level}%", self.font_small)

    # -------------------------------------------------------------------
    # Composición final
    # -------------------------------------------------------------------

    def _runtime_config(self):
        """Fix #5: cachea la config con TTL de 1s. Antes se releía y
        reparseaba el JSON de disco hasta ~5 veces por render (una vez desde
        build_live_state y una vez más desde cada uno de _get_focus_mode,
        _get_zoom_value, _get_storage_info, _get_network_state)."""
        now = time.time()
        if self._cfg_cache is not None and (now - self._cfg_cache_at) < self._cfg_cache_ttl:
            return self._cfg_cache

        if callable(load_config):
            try:
                self._cfg_cache = load_config()
            except Exception:
                self._cfg_cache = CONFIG or {}
        else:
            self._cfg_cache = CONFIG or {}
        self._cfg_cache_at = now
        return self._cfg_cache

    @staticmethod
    def _format_timer(seconds):
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _update_timer_state(self, resolved):
        recording = bool(resolved.get("recording", False))
        streaming = bool(resolved.get("streaming", False))
        active = recording or streaming

        if active:
            if self._timer_started_at is None:
                self._timer_started_at = time.time()
            elapsed = int(time.time() - self._timer_started_at)
            resolved["timer"] = self._format_timer(elapsed)
            self._timer_active = True
            return

        self._timer_active = False
        self._timer_started_at = None
        if "timer" not in resolved:
            resolved["timer"] = "00:00:00"

    def _get_optics_state(self):
        if gpio_control_module is None:
            return {}
        try:
            if hasattr(gpio_control_module, "get_optics_state"):
                return gpio_control_module.get_optics_state() or {}
        except Exception:
            pass
        return {}

    def _get_focus_mode(self):
        optics = self._get_optics_state()
        mode = None
        if optics:
            mode = optics.get("focus_mode") or optics.get("focus")
        if not mode and gpio_control_module is not None:
            mode = getattr(gpio_control_module, "FOCUS_MODE", None)
        if not mode:
            cfg = self._runtime_config()
            mode = cfg.get("AfMode") or cfg.get("focus_mode")
        if isinstance(mode, str):
            mode = mode.strip()
        if mode in {"manual", "MF", "mf"}:
            return "MF"
        if mode in {"autofocus", "AF-C", "AF-S", "af-c", "af-s", "AF", "af"}:
            return "AF-C"
        if isinstance(mode, int):
            return "AF-C" if mode in {1, 2} else "MF"
        return "AF-C"

    def _get_zoom_value(self):
        optics = self._get_optics_state()
        if optics:
            try:
                return float(optics.get("zoom", optics.get("optical_zoom", 1.0)))
            except Exception:
                pass
        cfg = self._runtime_config()
        zoom = cfg.get("LensPosition", 1.0)
        try:
            return float(zoom)
        except Exception:
            return 1.0

    def _get_storage_info(self):
        """Fix #3: cachea el resultado de shutil.disk_usage (syscall
        statvfs) con TTL de 5s. El espacio libre no cambia lo suficiente
        segundo a segundo como para justificar una syscall por frame."""
        now = time.time()
        if self._storage_cache is not None and (now - self._storage_cache_at) < self._storage_cache_ttl:
            return self._storage_cache

        cfg = self._runtime_config()
        if callable(resolve_storage_dir):
            try:
                target_dir = resolve_storage_dir("videos", cfg)
            except Exception:
                target_dir = None
        else:
            target_dir = None
        if not target_dir and callable(get_storage_base_path):
            try:
                target_dir = get_storage_base_path(cfg)
            except Exception:
                target_dir = None
        target_dir = target_dir or os.getcwd()
        try:
            usage = shutil.disk_usage(target_dir)
            free_gb = max(0, usage.free // (1024 ** 3))
            device = "USB" if any(token in target_dir.lower() for token in ("usb", "media", "mnt")) else "SSD"
            result = {
                "device": device,
                "free_gb": free_gb,
                "remaining": f"{free_gb}GB FREE" if free_gb else "FULL",
            }
        except Exception:
            result = {"device": "SSD", "free_gb": 0, "remaining": "--"}

        self._storage_cache = result
        self._storage_cache_at = now
        return result

    def _resolve_sensor_ups(self):
        global sensor_ups
        if sensor_ups is not None:
            return sensor_ups
        try:
            import importlib
            main_module = importlib.import_module("main")
            sensor_ups = getattr(main_module, "sensor_ups", None)
        except Exception:
            sensor_ups = None
        return sensor_ups

    def _get_battery_state(self):
        """Fix #4: la instancia local de INA219 (fallback cuando no hay
        sensor_ups global) se cachea a nivel de módulo en vez de crearse de
        nuevo en cada render — instanciar el driver implica init de I2C, que
        no es gratis a 1 llamada/segundo. Si falla una vez, no se reintenta
        infinitamente (se marca _local_ina219_failed) para no repetir el
        costo de un init fallido en cada vuelta."""
        global _local_ina219, _local_ina219_failed

        sensor = self._resolve_sensor_ups()
        try:
            if sensor is not None:
                stats = sensor.get_stats()
                if stats.get("battery_percent") is not None:
                    power_state = stats.get("power_state") or stats.get("status") or "offline"
                    return {
                        "percent": int(stats["battery_percent"]),
                        "voltage_v": stats.get("voltage_v"),
                        "current_a": stats.get("current_a"),
                        "power_w": stats.get("power_w"),
                        "status": power_state,
                        "power_state": power_state,
                    }
        except Exception:
            pass
        try:
            if psutil is not None:
                battery = psutil.sensors_battery()
                if battery is not None and battery.percent is not None:
                    status = "charging" if getattr(battery, "power_plugged", False) else "online"
                    return {"percent": int(battery.percent), "status": status}
        except Exception:
            pass
        try:
            if INA219 is not None and not _local_ina219_failed:
                if _local_ina219 is None:
                    _local_ina219 = INA219()
                stats = _local_ina219.get_stats()
                if stats.get("battery_percent") is not None:
                    power_state = stats.get("power_state") or stats.get("status") or "offline"
                    return {
                        "percent": int(stats["battery_percent"]),
                        "voltage_v": stats.get("voltage_v"),
                        "current_a": stats.get("current_a"),
                        "power_w": stats.get("power_w"),
                        "status": power_state,
                        "power_state": power_state,
                    }
        except Exception:
            _local_ina219_failed = True
            _local_ina219 = None
        return {"percent": 100, "status": "offline"}

    def _extract_host(self, value):
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        if "://" in text:
            try:
                return urlparse(text).hostname
            except Exception:
                return None
        if "/" in text:
            text = text.split("/", 1)[0]
        if ":" in text:
            text = text.split(":", 1)[0]
        return text or None

    def _classify_network_kind(self, host):
        try:
            resolved = socket.gethostbyname(host)
            ip = ipaddress.ip_address(resolved)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return "LAN"
            return "WAN"
        except Exception:
            return "WAN"

    def _get_network_state(self):
        cfg = self._runtime_config()
        host = self._extract_host(cfg.get("IPDestinoSRT") or cfg.get("IPDestino") or "")

        if callable(get_wifi_device_status):
            try:
                state, connection = get_wifi_device_status()
                if state == "connected":
                    return {"quality": 5, "connected": True, "connection": connection or "WiFi", "kind": "WIFI"}
                if state:
                    return {"quality": 2, "connected": False, "connection": connection or "WiFi", "kind": "WIFI"}
            except Exception:
                pass

        if not host:
            return {"quality": 0, "connected": False, "connection": "--", "kind": "OFFLINE"}

        ping_cmd = ["ping", "-n", "1", "-w", "1000", host] if os.name == "nt" else ["ping", "-c", "1", "-W", "1", host]
        try:
            completed = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            if completed.returncode == 0:
                kind = self._classify_network_kind(host)
                return {"quality": 5, "connected": True, "connection": host, "kind": kind}
        except Exception:
            pass

        return {"quality": 0, "connected": False, "connection": host, "kind": "OFFLINE"}

    def build_live_state(self, state=None):
        """Combina el estado del overlay con datos del sistema si están disponibles."""
        resolved = dict(state or {})
        cfg = self._runtime_config()
        resolution = str(cfg.get("resolution", "1920x1080") or "1920x1080")
        try:
            width, height = [int(part) for part in resolution.lower().split("x")]
        except Exception:
            width, height = 1920, 1080

        video = dict(resolved.get("video") or {})
        video.setdefault("format", self._resolve_video_format(width, height))
        video.setdefault("fps", int(cfg.get("fps", 30) or 30))
        resolved["video"] = video

        focus = dict(resolved.get("focus") or {})
        focus.setdefault("mode", self._get_focus_mode())
        resolved["focus"] = focus

        white_balance = dict(resolved.get("white_balance") or {})
        auto_wb = cfg.get("AwbEnable", True)
        white_balance.setdefault("auto", bool(auto_wb))
        white_balance.setdefault("kelvin", int(cfg.get("ColourTemperature", 5600) or 5600))
        resolved["white_balance"] = white_balance

        optics = self._get_optics_state()
        if optics:
            zoom_value = self._get_zoom_value()
            physical_zoom_max = getattr(gpio_control_module, "PHYSICAL_ZOOM_MAX", 3.5)
            resolved["zoom"] = zoom_value
            resolved["digital_zoom_active"] = zoom_value > physical_zoom_max or str(optics.get("zoom_mode", "")).lower() == "digital"
            focus = dict(resolved.get("focus") or {})
            focus.setdefault("mode", self._get_focus_mode())
            focus.setdefault("position", optics.get("focus_position", 0.0))
            resolved["focus"] = focus
        else:
            zoom = resolved.get("zoom", None)
            if zoom is None:
                zoom = cfg.get("LensPosition", 1.0)
            try:
                resolved["zoom"] = float(zoom)
            except Exception:
                resolved["zoom"] = 1.0
            resolved["digital_zoom_active"] = False

            focus = dict(resolved.get("focus") or {})
            focus.setdefault("mode", self._get_focus_mode())
            resolved["focus"] = focus

        storage = dict(resolved.get("storage") or {})
        storage.update(self._get_storage_info())
        resolved["storage"] = storage

        resolved.setdefault("zoom_speed_mode", getattr(gpio_control_module, "ZOOM_SPEED_MODE", "slow"))

        battery = dict(resolved.get("battery") or {})
        battery.update(self._get_battery_state())
        resolved["battery"] = battery

        network = dict(resolved.get("network") or {})
        if self._network_monitor is not None:
            try:
                network.update(self._network_monitor.get_state())
            except Exception:
                network.update(self._get_network_state())
        else:
            network.update(self._get_network_state())
        resolved["network"] = network

        camera = dict(resolved.get("camera") or {})
        camera.setdefault("number", int(cfg.get("camera_number", 1) or 1))
        resolved["camera"] = camera

        try:
            import video_rec as video_rec_module
            resolved.setdefault("recording", bool(getattr(video_rec_module, "recTake", False)))
        except Exception:
            resolved.setdefault("recording", bool(resolved.get("recording", False)))

        try:
            import video_stream as video_stream_module
            resolved.setdefault("streaming", bool(getattr(video_stream_module, "video_thread_running", None) and getattr(video_stream_module.video_thread_running, "is_set", lambda: False)()))
        except Exception:
            resolved.setdefault("streaming", bool(resolved.get("streaming", False)))

        resolved.setdefault("mode", "REC" if resolved.get("recording") else "LIVE")
        self._update_timer_state(resolved)
        return resolved

    def render_overlay(self, state=None):
        """Compone el HUD completo respetando la configuración `self.overlay`."""
        state = self.build_live_state(state)
        base = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)
        frame_count = state.get("frame_count", 0)
        cfg = self.overlay

        if cfg.get("show_thirds", True):
            # Fix #6: compone la capa cacheada en vez de recalcular las
            # líneas en cada frame.
            base.alpha_composite(self._get_thirds_layer())
        if cfg.get("show_rec", True):
            self.draw_rec(draw, state, frame_count)
        if cfg.get("show_timer", True):
            self.draw_timer(draw, state)
        if cfg.get("show_video", True):
            self.draw_video(draw, state)
        if cfg.get("show_white_balance", True):
            self.draw_white_balance(draw, state)
        if cfg.get("show_focus", True):
            self.draw_focus(draw, state)
        if cfg.get("show_zoom", True):
            self.draw_zoom(draw, state)
        if cfg.get("show_storage", True):
            self.draw_storage(draw, state)
        if cfg.get("show_battery", True):
            self.draw_battery(draw, state)
        if cfg.get("show_network", True):
            self.draw_network(draw, state)
        if cfg.get("show_audio", True):
            self.draw_audio_meter(draw, state)
        if cfg.get("show_camera", True):
            self.draw_camera_number(draw, state)

        return base

    def save_overlay(self, img):
        """Guarda el PNG de forma atómica (tmp + replace) para evitar lecturas
        a medio escribir por parte de quien componga el overlay sobre video.

        Fix #2: compress_level=1 en vez del default (6). Este archivo se
        sobreescribe cada segundo y se lee una sola vez por quien compone el
        overlay — no tiene sentido gastar CPU comprimiendo bien un PNG
        temporal; priorizamos velocidad de escritura sobre tamaño en disco.
        """
        tmp_path = f"{self.out_path}.tmp"
        img.convert("RGBA").save(tmp_path, format="PNG", compress_level=1)
        os.replace(tmp_path, self.out_path)

    def run_periodic(self, interval=1.0, state_provider=None, stop_event=None):
        stop_event = stop_event or threading.Event()
        frame_count = 0
        start = time.time()
        while not stop_event.is_set():
            now = time.time()
            elapsed = int(now - start)
            state = state_provider() if state_provider else {}
            state.setdefault("frame_count", frame_count)
            state.setdefault("elapsed_seconds", elapsed)
            img = self.render_overlay(state)
            try:
                self.save_overlay(img)
            except Exception:
                pass
            frame_count += 1
            stop_event.wait(interval)


if __name__ == "__main__":
    renderer = OverlayRenderer()

    def sample_state():
        return {
            "recording": True,
            "streaming": True,
            "mode": "REC",
            "timer": "00:13:42",
            "video": {
                "format": "FHD",
                "resolution": "1920x1080",
                "fps": 30,
            },
            "focus": {
                "mode": "AF-C",
            },
            "white_balance": {
                "auto": True,
                "kelvin": 5600,
            },
            "zoom": 3.5,
            "storage": {
                "device": "USB",
                "free_gb": 124,
                "remaining": "02h35m",
            },
            "battery": {
                "percent": 82,
                "status": "charging",
            },
            "network": {
                "quality": 5,
                "kind": "WIFI",
            },
            "camera": {
                "number": 1,
            },
            "audio": {
                "configured": True,
                "valid": True,
                "db": -44,
                "level": 44
            },
        }

    stop = threading.Event()
    try:
        renderer.run_periodic(interval=1.0, state_provider=sample_state, stop_event=stop)
    except KeyboardInterrupt:
        stop.set()