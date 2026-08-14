import threading
import time
import subprocess
import logging
from picamera2 import Picamera2
from picamera2.previews import DrmPreview
from overlay_utils import start_overlay_updater
from camera_config import aplicar_camara_config, generar_sdp, CONFIG, picam2, load_config, changeRunningCamera, build_audio_monitor_plan, resolve_audio_monitor_plan
from talkback import ensure_fifo, start_talkback_feeder, FIFO_PATH
from camera_utils import release_camera_resources
import os
from hdmi_fallback import show_fallback_image

# Configurar logging para capturar mensajes de este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.propagate = True

AUDIO_BITRATE = "192k"


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
    # Fallback: create a tmp runtime dir with safe perms
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
# Overlay control (thread + stop event)
overlay_thread = None
overlay_stop = None

video_thread_running = threading.Event()

stream_proc = None
watchdog_thread = None
watchdog_running = threading.Event()
restart_lock = threading.Lock()

def _safe_start_blink():
    try:
        from gpio_control import start_blink
        start_blink()
    except Exception:
        pass


def _safe_stop_blink():
    try:
        from gpio_control import stop_blink
        stop_blink()
    except Exception:
        pass

def video_stream_thread():
    global overlay_thread, overlay_stop
    ensure_fifo()
    start_talkback_feeder()
    video_thread_running.set()
    logger.info("📡 Hilo de video stream iniciado.")
    global picam2, CONFIG, stream_proc
    
    CONFIG = load_config()
    mic_path = CONFIG.get("mic")
    is_mic_enabled = mic_path and not mic_path.startswith('!')
    if is_mic_enabled:
        logger.info(f"Micrófono detectado y activo: {mic_path}")
    else:
        CONFIG["mic"] = ""
        logger.info("Micrófono desactivado o comentado con '!'. Solo de video.")
    audio_plan = resolve_audio_monitor_plan(CONFIG)
    if audio_plan["enabled"]:
        logger.info("🎧 Monitor de audio activado: %s -> %s", audio_plan["monitor_source"], audio_plan["monitor_output"])
    else:
        logger.warning("⚠️ Monitor de audio desactivado: dispositivo ALSA no válido o no configurado")
    WIDTH, HEIGHT = map(int, CONFIG["resolution"].lower().split("x"))
    TARGET_FPS = CONFIG["fps"]

    import camera_config
    picam2 = Picamera2()
    camera_config.picam2 = picam2
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH, HEIGHT)},
        controls={"FrameRate": int(TARGET_FPS)}
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
    # arrancar hilo que aplica overlay.png sobre la preview (si la API lo permite)
    try:
        if CONFIG.get("hdmi_overlay", True):
            overlay_thread, overlay_stop = start_overlay_updater(picam2, interval=1.0)
        else:
            logger.info("Overlay HDMI desactivado por configuración (hdmi_overlay=False)")
    except Exception:
        logger.debug("No se pudo iniciar overlay updater thread")
    aplicar_camara_config(picam2, True)
    
    generar_sdp(ip=CONFIG.get("IPSDP"))

    cmd = [
        'ffmpeg',
        '-y',
        '-hide_banner', '-loglevel', 'warning', '-nostats',
        '-fflags', 'nobuffer+genpts',
        '-flags', 'low_delay',
        # VIDEO INPUT
        '-use_wallclock_as_timestamps', '1',
        '-thread_queue_size', '4096',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-framerate', str(TARGET_FPS),
        '-i', '-',
    ]

    # VIDEO encode options
    cmd.extend([
        '-g', '60',
        '-c:v', 'libx264',
        '-threads', '3',
        '-preset', CONFIG.get('preset'),
        '-b:v', CONFIG.get('bitrate'),
        '-maxrate', CONFIG.get('bitrate'),
        '-bufsize', CONFIG.get('bitrate'),
        '-tune', 'zerolatency',
        '-x264opts', 'keyint=30:scenecut=0:repeat-headers=1',
    ])

    # Add audio input if present
    if CONFIG.get('mic'):
        audio_input_device = audio_plan.get('monitor_source') or CONFIG.get('mic')
        cmd.extend([
            '-thread_queue_size', '512',
            '-f', 'alsa',
            '-ar', '48000',
            '-ac', '1',
            '-fragment_size', '512',
            '-i', audio_input_device,
            '-c:a', 'aac',
            '-b:a', AUDIO_BITRATE,
            '-af', 'aresample=async=1:min_hard_comp=0.100:first_pts=0',
        ])
        cmd.extend(['-map', '0:v', '-map', '1:a'])

    # Output options for RTSP (append after inputs)
    rtsp_output_opts = [
        '-flush_packets', '1',
        '-fps_mode', 'passthrough',
        '-f', 'rtsp',
        '-rtsp_transport', CONFIG.get('protocolo'),
        f"{CONFIG.get('IPDestino')}"
    ]

    # SRT command (inputs similar to RTSP)
    cmd_srt = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning', '-nostats',
        '-fflags', 'nobuffer+genpts', '-flags', 'low_delay',
        '-use_wallclock_as_timestamps', '1',
        '-thread_queue_size', '4096',
        '-f', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-framerate', str(TARGET_FPS),
        '-i', '-'
    ]

    if CONFIG.get('mic'):
        audio_input_device = audio_plan.get('monitor_source') or CONFIG.get('mic')
        cmd_srt.extend([
            '-thread_queue_size', '512',
            '-f', 'alsa',
            '-ar', '48000',
            '-ac', '1',
            '-i', audio_input_device
        ])

    cmd_srt.extend([
        '-c:v', 'libx264',
        '-threads', '3',
        '-preset', CONFIG.get('preset'),
        '-b:v', CONFIG.get('bitrate'),
        '-maxrate', CONFIG.get('bitrate'),
        '-bufsize', CONFIG.get('bitrate'),
        '-tune', 'zerolatency',
        '-g', '60',
        '-x264opts', 'keyint=30:scenecut=0:repeat-headers=1',
        '-fps_mode', 'passthrough',
    ])

    if CONFIG.get('mic'):
        cmd_srt.extend([
            '-c:a', 'aac',
            '-b:a', AUDIO_BITRATE,
            '-af', 'aresample=async=1',
            '-map', '0:v', '-map', '1:a'
        ])

    if CONFIG.get('mic'):
        os.environ['ALSA_PCM_BUFFER_TIME'] = '20000'
        os.environ['ALSA_PCM_PERIOD_TIME'] = '5000'

    srt_url = f'srt://{CONFIG.get("IPDestinoSRT")}:{CONFIG.get("puertoDestinoSRT")}{CONFIG.get("extraDataSRT")}'
    # finalize SRT output options
    cmd_srt.extend(['-flush_packets', '1', '-f', 'mpegts', srt_url])

    proc = None
    monitor_proc = None
    
    if CONFIG.get("protocolo_stream") == "RTSP":
        # ensure XDG_RUNTIME_DIR for SDL/Wayland before launching
        ensure_xdg_runtime_dir()
        # append RTSP output options now that all inputs are defined
        cmd.extend(rtsp_output_opts)
        with open("stream_log.txt", "wb") as f:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)

    if CONFIG.get("protocolo_stream") == "SRT":
        with open("stream_log.txt", "wb") as f:
            proc = subprocess.Popen(cmd_srt, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)

    if audio_plan.get('enabled'):
        monitor_output = audio_plan.get('monitor_output') or 'default'
        monitor_cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning', '-nostats',
            '-thread_queue_size', '4096',
            '-f', 'alsa', '-ar', '48000', '-ac', '1',
            '-i', audio_plan.get('monitor_source'),
            '-thread_queue_size', '4096',
            '-f', 's16le', '-ar', '48000', '-ac', '1',
            '-i', FIFO_PATH,
            '-filter_complex',
            '[0:a]aresample=async=1:min_hard_comp=0.100:first_pts=0[a0];'
            '[1:a]aresample=async=1:min_hard_comp=0.100:first_pts=0[a1];'
            '[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]',
            '-map', '[aout]',
            '-f', 'alsa', monitor_output
        ]
        with open("audio_monitor_log.txt", "wb") as f:
            monitor_proc = subprocess.Popen(monitor_cmd, stdout=f, stderr=subprocess.STDOUT)
            if monitor_proc.poll() is not None:
                logger.warning("El proceso del monitor de audio falló al arrancar; se desactiva el monitor")
                monitor_proc = None

    stream_proc = proc

    stop_error = False
    _safe_start_blink()
    changeRunningCamera(True)

    try:
        while video_thread_running.is_set() and not stop_error:
            try:
                frame = picam2.capture_array("main")
                proc.stdin.write(memoryview(frame))
            except Exception as e:
                stop_error = True
                logger.error("Error en stream video: %s", e)
                _safe_stop_blink()
                changeRunningCamera(False)
    except Exception as e:
        stop_error = True
        logger.error("Error en hilo video: %s", e)
        _safe_stop_blink()
        changeRunningCamera(False)
    finally:
        video_thread_running.clear()
        if proc and proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
        for p in [proc, monitor_proc]:
            if p:
                try:
                    p.terminate()
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
        stream_proc = None
        # Stop overlay thread if running
        try:
            if overlay_stop:
                overlay_stop.set()
            if overlay_thread and overlay_thread.is_alive():
                overlay_thread.join(timeout=1)
            overlay_stop = None
            overlay_thread = None
        except Exception:
            pass
        try:
            release_camera_resources(picam2, wait_seconds=0.2)
        except Exception:
            pass
        logger.info("🔴 Hilo de video stream parado.")
        _safe_stop_blink()
        changeRunningCamera(False)

last_restart_time = 0
debounce_delay = 1.0  # segundos
def restart_video_thread():
    global video_thread, picam2, last_restart_time

    now = time.time()
    if now - last_restart_time < debounce_delay:
        logger.debug("Ignorado: debounce activo.")
        return
    last_restart_time = now

    if video_thread and video_thread.is_alive():
        logger.info("🔁 Deteniendo hilo de captura...")
    video_thread_running.clear()
    if video_thread and video_thread.is_alive():
        video_thread.join(timeout=3)
    if picam2 is not None:
        try:
            release_camera_resources(picam2, wait_seconds=0.2)
        except Exception:
            pass
        picam2 = None
    time.sleep(0.5)

    logger.info("▶️ Iniciando nuevos hilos de video...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()
    # arrancar watchdog que vigila el proceso ffmpeg
    try:
        start_stream_watchdog()
    except Exception:
        pass


def apply_config_to_active_camera(todo=False):
    global picam2, CONFIG
    if picam2 is not None:
        aplicar_camara_config(picam2, todo)
        CONFIG = load_config()

def stream_watchdog():
    """Vigila el proceso ffmpeg y reinicia si es necesario."""
    global stream_proc, watchdog_running, CONFIG
    logger.info("[WATCHDOG] iniciado")
    while watchdog_running.is_set():
        try:
            cfg = load_config()
            proc = stream_proc
            CONFIG = cfg
            if proc is None:
                time.sleep(2)
                continue
            if proc.poll() is not None:
                if cfg.get("AutoReconnect"):
                    logger.warning("[WATCHDOG] ffmpeg murió; intentando reiniciar stream...")
                    try:
                        with restart_lock:
                            restart_video_thread()
                    except Exception as e:
                        logger.error("[WATCHDOG] reinicio fallido: %s", e)
                        time.sleep(2)
                    else:
                        time.sleep(2)
                else:
                    watchdog_running.clear()
                    break
                continue
        except Exception as e:
            logger.error("[WATCHDOG] error: %s", e)
        time.sleep(1.0)


def start_stream_watchdog():
    global watchdog_thread, watchdog_running
    if watchdog_thread and watchdog_thread.is_alive():
        return
    watchdog_running.set()
    watchdog_thread = threading.Thread(target=stream_watchdog, daemon=True)
    watchdog_thread.start()