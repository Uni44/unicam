"""Helpers para cargar y aplicar overlay PNG sobre `Picamera2` preview.

Provee `start_overlay_updater(picam2, interval)` que devuelve (thread, stop_event).
"""
import json
import os
import threading
import time
import math
from PIL import Image
import numpy as np
import logging

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import camera_config
except Exception:
    camera_config = None

from overlay_renderer import OverlayRenderer

logger = logging.getLogger(__name__)

# Path por defecto relativo al proyecto
DEFAULT_OVERLAY = os.path.join(os.path.dirname(__file__), "overlay.png")


class AudioMeter:
    """Mide el nivel del micrófono en background para el overlay.

    Usa SoundDevice en modo callback para no bloquear ni hacer grabaciones
    completas. Guarda RMS/dB y devuelve un estado listo para el renderer.
    """

    def __init__(self, device=None, sample_rate=48000, channels=1, block_size=4096):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = max(int(block_size), 2048)
        self._state = {
            "active": False,
            "db": -80.0,
            "level": 0,
            "valid": False,
            "configured": False,
        }
        self._lock = threading.Lock()
        self._stream = None
        # Para no inundar el log si hay overflow/underrun constante.
        self._status_warn_count = 0
        self._callback_count = 0
        self._last_error = None
        self._start_stream()

    def _load_runtime_config(self):
        if camera_config is not None:
            cfg = getattr(camera_config, 'CONFIG', None)
            if isinstance(cfg, dict):
                return cfg
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'camera_config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as handle:
                    data = json.load(handle)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {}

    def _resolve_device(self):
        if self.device is not None:
            return self.device
        cfg = self._load_runtime_config()
        mic = str(cfg.get('mic') or '').strip()
        if not mic or mic.startswith('!'):
            return None
        # PortAudio (sounddevice) espera un índice numérico o un substring del
        # nombre que PortAudio le puso al dispositivo — NO un nombre de PCM de
        # ALSA como "dsnoop_mic" definido en ~/.asoundrc. Si en la config
        # guardamos un índice como string ("2"), hay que castearlo a int o
        # sounddevice lo va a tratar como texto y no va a matchear nada.
        if mic.isdigit():
            try:
                return int(mic)
            except Exception:
                return mic
        return mic

    def debug_devices(self):
        """Devuelve la lista de dispositivos que ve PortAudio, para diagnóstico.
        Útil para confirmar si tu mic (ej. dsnoop_mic / hw:2,0) aparece acá con
        otro nombre o índice distinto al que tenés en camera_config."""
        if sd is None:
            return {"error": "sounddevice no está disponible en este entorno"}
        try:
            devices = sd.query_devices()
            return {
                "resolved_device": self._resolve_device(),
                "default_input": sd.default.device,
                "devices": [
                    {
                        "index": i,
                        "name": d.get("name"),
                        "max_input_channels": d.get("max_input_channels"),
                        "default_samplerate": d.get("default_samplerate"),
                    }
                    for i, d in enumerate(devices)
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    def _start_stream(self):
        if sd is None:
            logger.warning("AudioMeter: sounddevice no disponible, medidor de audio deshabilitado")
            return
        device = self._resolve_device()
        configured = device is not None
        with self._lock:
            self._state["configured"] = configured
            self._state["valid"] = configured
            self._state["active"] = False
        if device is None:
            logger.info("AudioMeter: sin mic configurado (camera_config['mic'] vacío o deshabilitado con '!')")
            return
        try:
            self._stream = sd.InputStream(
                device=device,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=self._audio_callback,
            )
            self._stream.start()
            with self._lock:
                self._state["active"] = True
                self._state["valid"] = True
            logger.info(f"AudioMeter: stream abierto correctamente en device={device!r}")
        except Exception as e:
            self._stream = None
            self._last_error = str(e)
            with self._lock:
                self._state["active"] = False
                # OJO: antes esto quedaba en True, lo que ocultaba el fallo
                # real (el HUD mostraba "mic válido" pero congelado en -80dB).
                self._state["valid"] = False
                self._state["configured"] = True
            logger.error(
                f"AudioMeter: no se pudo abrir InputStream en device={device!r}: {e}. "
                f"Dispositivos disponibles: {self.debug_devices()}"
            )

    def _audio_callback(self, indata, frames, time_info, status):
        self._callback_count += 1
        if status:
            # Overflow/underrun son avisos, no errores fatales. Con buffers más
            # grandes se reduce la incidencia, y si llegan de forma continua
            # solo se registra cada cierto número de veces para no saturar el log.
            self._status_warn_count += 1
            if self._status_warn_count <= 3 or self._status_warn_count % 200 == 0:
                logger.warning(
                    "AudioMeter: status del stream (%s veces): %s",
                    self._status_warn_count,
                    status,
                )
        try:
            samples = np.asarray(indata, dtype=np.float32)
            if samples.size == 0:
                return
            rms = math.sqrt(float(np.mean(samples ** 2)))
            db = 20.0 * math.log10(max(rms, 1e-8))
            db = max(db, -80.0)
            level = int(max(0, min(100, round((db + 60.0) * (100.0 / 60.0)))))
            with self._lock:
                self._state["db"] = db
                self._state["level"] = level
                self._state["active"] = True
                self._state["valid"] = True
        except Exception as e:
            if self._callback_count <= 3:
                logger.error(f"AudioMeter: error calculando nivel de audio: {e}")

    def get_state(self):
        with self._lock:
            return dict(self._state)

    def close(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def load_overlay_png(path=DEFAULT_OVERLAY, size=(1920, 1080)):
    try:
        img = Image.open(path).convert("RGBA")
        if img.size != size:
            img = img.resize(size)
        return np.asarray(img)
    except Exception as e:
        logger.debug(f"No se pudo cargar overlay PNG '{path}': {e}")
        return None


def clear_overlay(picam2, size=(1920, 1080)):
    if picam2 is None:
        return False
    try:
        if not hasattr(picam2, 'set_overlay'):
            return False
        height, width = size[1], size[0]
        overlay = np.zeros((height, width, 4), dtype=np.uint8)
        picam2.set_overlay(overlay)
        return True
    except Exception as e:
        logger.debug(f"No se pudo limpiar overlay: {e}")
        return False


def overlay_updater_thread(picam2, path=DEFAULT_OVERLAY, size=(1920, 1080), interval=1.0, stop_event=None, state_provider=None):
    stop_event = stop_event or threading.Event()
    renderer = OverlayRenderer(width=size[0], height=size[1], out_path=path, overlay_scale=1.8)
    audio_meter = AudioMeter()
    try:
        while not stop_event.is_set():
            try:
                state = state_provider() if state_provider else {}
                if isinstance(state, dict):
                    state["audio"] = audio_meter.get_state()
                img = renderer.render_overlay(state)
                renderer.save_overlay(img)
                overlay = np.asarray(img.convert("RGBA"))
                if overlay is not None and hasattr(picam2, 'set_overlay'):
                    try:
                        picam2.set_overlay(overlay)
                        logger.debug("Overlay aplicado con picam2.set_overlay()")
                    except Exception as e:
                        logger.debug(f"Error aplicando overlay desde memoria: {e}")
                        try:
                            overlay_from_disk = load_overlay_png(path, size=size)
                            if overlay_from_disk is not None:
                                picam2.set_overlay(overlay_from_disk)
                                logger.debug("Overlay aplicado desde PNG de respaldo")
                        except Exception as e2:
                            logger.debug(f"Error aplicando overlay desde PNG de respaldo: {e2}")
                else:
                    if not hasattr(picam2, 'set_overlay'):
                        logger.debug("picam2.set_overlay no disponible; omitiendo overlay")
            except Exception as e:
                logger.debug(f"Error generando/guardando overlay: {e}")
            stop_event.wait(interval)
    finally:
        try:
            clear_overlay(picam2, size=size)
        except Exception:
            pass
        audio_meter.close()


def start_overlay_updater(picam2, interval=1.0, path=None, size=(1920, 1080)):
    path = path or DEFAULT_OVERLAY
    stop_event = threading.Event()
    t = threading.Thread(target=overlay_updater_thread, args=(picam2, path, size, interval, stop_event), daemon=True)
    t.start()
    return t, stop_event