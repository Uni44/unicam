import threading
import time
import subprocess
import logging
from datetime import datetime
from picamera2 import Picamera2
from picamera2.previews import DrmPreview
from camera_config import aplicar_camara_config, CONFIG, picam2, changeRunningCamera, load_config, resolve_storage_dir
from overlay_utils import start_overlay_updater
import os
from hdmi_fallback import show_fallback_image

logger = logging.getLogger(__name__)


def ensure_xdg_runtime_dir():
    xr = os.environ.get("XDG_RUNTIME_DIR")
    if xr and os.path.isdir(xr):
        return
    try:
        uid = os.getuid()
    except Exception:
        uid = None
    if uid:
        candidate = f"/run/user/{uid}"
        if os.path.isdir(candidate):
            os.environ["XDG_RUNTIME_DIR"] = candidate
            return
    fallback = f"/tmp/xdg-runtime-{os.getpid()}"
    try:
        os.makedirs(fallback, exist_ok=True)
        os.chmod(fallback, 0o700)
        os.environ["XDG_RUNTIME_DIR"] = fallback
    except Exception:
        os.environ["XDG_RUNTIME_DIR"] = "/tmp"


def start_drm_preview(picam2):
    if picam2 is None:
        return False
    opcion_hdmi = CONFIG.get("hdmi")
    if opcion_hdmi == "Off":
        return False
    try:
        if hasattr(picam2, 'stop_preview'):
            try:
                picam2.stop_preview()
            except Exception:
                pass
        time.sleep(0.2)
        picam2.start_preview(DrmPreview(x=0, y=0, width=2560, height=1440)) #LA SALIDA POR HDMI ESTA FIJADO A 2k
        logger.info("✅ DrmPreview iniciado para HDMI")
        return True
    except Exception as e:
        logger.error(f"⚠️ No se pudo iniciar DrmPreview: {e}")
        return False


def request_hdmi_restart():
    if picam2 is None:
        logger.warning("No hay cámara activa para reiniciar HDMI")
        return False
    logger.info("🔁 Reiniciando HDMI/DrmPreview")
    return start_drm_preview(picam2)

video_thread = None

video_thread_running = threading.Event()

# Overlay control
overlay_thread = None
overlay_stop = None

fotoTake = False

# Crear carpeta si no existe
carpeta = resolve_storage_dir("fotos", CONFIG)
os.makedirs(carpeta, exist_ok=True)

def video_stream_thread():
    global overlay_thread, overlay_stop
    video_thread_running.set()
    logger.info("📡 Hilo de captura de foto iniciado.")
    
    global picam2, fotoTake
    from gpio_control import start_blink, stop_blink

    WIDTH2, HEIGHT2 = 4608, 2592

    import camera_config
    picam2 = Picamera2()
    camera_config.picam2 = picam2
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH2, HEIGHT2)},
        buffer_count=2
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.2)
    drm_started = start_drm_preview(picam2)
    if not drm_started:
        try:
            show_fallback_image(CONFIG, force=True)
        except Exception as exc:
            logger.warning("No se pudo mostrar la imagen de fallback: %s", exc)
    # start overlay thread if enabled
    try:
        cfg = load_config()
        if cfg.get("hdmi_overlay", True):
            overlay_thread, overlay_stop = start_overlay_updater(picam2, interval=1.0)
        else:
            logger.info("Overlay HDMI desactivado por configuración (hdmi_overlay=False)")
    except Exception:
        logger.debug("No se pudo iniciar overlay updater thread (foto)")
    aplicar_camara_config(picam2, True)

    changeRunningCamera(True)

    start_time = time.time()
    frame_count = 0
    stop_error = False
    
    try:
        while video_thread_running.is_set() and not stop_error:
            try:
                frame = picam2.capture_array("main")
                # DrmPreview maneja la salida HDMI automaticamente
                if fotoTake:
                    start_blink()
                    carpeta = resolve_storage_dir("fotos", load_config())
                    os.makedirs(carpeta, exist_ok=True)
                    for i in range(10):  # cantidad de fotos
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        nombre_archivo = f"foto_{timestamp}.jpg"
                        ruta_completa = os.path.join(carpeta, nombre_archivo)
                        print("✅ Foto guardada en", ruta_completa)
                        picam2.capture_file(ruta_completa)
                        time.sleep(0.2)
                    stop_blink()
                    fotoTake = False
                latest_frame = memoryview(frame)
            except Exception as e:
                stop_error = True
                logger.error("❌ Error capturando frame: %s", e)
                stop_blink()
                changeRunningCamera(False)
    except Exception as e:
        stop_error = True
        logger.error("❌ Error en hilo video: %s", e)
        stop_blink()
        changeRunningCamera(False)
    finally:
        video_thread_running.clear()
        picam2.close()
        # DrmPreview se cierra automaticamente con picam2
        print("🔴 Hilo de captura de foto parado.")
        stop_blink()
        # stop overlay thread if running
        try:
            if overlay_stop:
                overlay_stop.set()
            if overlay_thread and overlay_thread.is_alive():
                overlay_thread.join(timeout=1)
            overlay_stop = None
            overlay_thread = None
        except Exception:
            pass
        changeRunningCamera(False)

last_restart_time = 0
debounce_delay = 1.0  # segundos
def restart_foto_thread():
    global video_thread, picam2, last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        print("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now

    if video_thread and video_thread.is_alive():
        print("🔁 Deteniendo hilo de captura...")
    video_thread_running.clear()
    if video_thread and video_thread.is_alive():
        video_thread.join()
    time.sleep(1)

    print("▶️ Iniciando nuevos hilos de fotos...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()



def capture_foto():
    global fotoTake, last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        print("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now
    fotoTake = True

def apply_config_to_active_camera_foto(todo=False):
    global picam2, CONFIG
    if picam2 is not None:
        aplicar_camara_config(picam2, todo)
        CONFIG = load_config()