import threading
import time
import subprocess
import logging
from picamera2 import Picamera2
from picamera2.previews import DrmPreview
from camera_config import aplicar_camara_config, CONFIG, picam2, load_config, changeRunningCamera, resolve_storage_dir, build_audio_monitor_plan, resolve_audio_monitor_plan
from camera_utils import release_camera_resources
import os
import shutil
from overlay_utils import start_overlay_updater
from hdmi_fallback import show_fallback_image

logger = logging.getLogger(__name__)

AUDIO_BITRATE = "192k"


def remux_recording_to_mp4(temp_path, final_path):
    try:
        remux_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-nostats",
            "-i", temp_path,
            "-c", "copy",
            "-movflags", "+faststart",
            final_path
        ]
        subprocess.run(remux_cmd, check=True)
        logger.info("✅ Remuxed recording to MP4: %s", final_path)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("❌ Error remuxing %s to %s: %s", temp_path, final_path, e)
        return False


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

recTake = False

# Crear carpeta si no existe
carpeta = resolve_storage_dir("videos", CONFIG)
os.makedirs(carpeta, exist_ok=True)

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

def video_stream_thread():
    global overlay_thread, overlay_stop
    video_thread_running.set()
    logger.info("📡 Hilo de captura de rec iniciado.")
    
    global picam2, recTake
    from gpio_control import start_blink, stop_blink

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
        logger.info("🎧 Monitor de audio activado para grabación: %s -> %s", audio_plan["monitor_source"], audio_plan["monitor_output"])
    else:
        logger.warning("⚠️ Monitor de audio desactivado para grabación: dispositivo ALSA no válido o no configurado")
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
    # start overlay thread if enabled
    try:
        cfg = load_config()
        if cfg.get("hdmi_overlay", True):
            overlay_thread, overlay_stop = start_overlay_updater(picam2, interval=1.0)
        else:
            logger.info("Overlay HDMI desactivado por configuración (hdmi_overlay=False)")
    except Exception:
        logger.debug("No se pudo iniciar overlay updater thread (rec)")
    aplicar_camara_config(picam2, True)
    
    changeRunningCamera(True)
    
    stop_error = False
    recording = False
    ffmpeg_proc = None
    monitor_proc = None
    temp_output_name = None
    final_output_name = None
    
    try:
        while video_thread_running.is_set() and not stop_error:
            frame = picam2.capture_array("main")
            # DrmPreview maneja la salida HDMI automáticamente
            
            if recTake and not recording:
                print("🎬 Iniciando grabación...")
                carpeta = resolve_storage_dir("videos", load_config())
                os.makedirs(carpeta, exist_ok=True)
                temp_output_name = os.path.join(carpeta, time.strftime("record_%Y%m%d_%H%M%S.mkv"))
                final_output_name = temp_output_name[:-4] + ".mp4"
                # Reordenado y optimizado
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-nostats",
                    "-thread_queue_size", "8",
                    "-f", "rawvideo",
                    "-pix_fmt", "yuv420p",
                    "-s", f"{WIDTH}x{HEIGHT}",
                    "-framerate", str(TARGET_FPS),
                    "-i", "-",  # Entrada de video
                ]

                if CONFIG.get("mic"):
                    audio_input_device = audio_plan.get("monitor_source") or CONFIG.get("mic")
                    cmd.extend([
                        "-thread_queue_size", "4096",
                        "-f", "alsa",
                        "-ac", "2", # Tu log dice que el mic es stereo
                        "-i", audio_input_device, # Entrada de audio
                    ])

                # Salida y Códecs
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", CONFIG.get("preset"), # CAMBIO CRÍTICO para no perder FPS
                    "-crf", "20",           # Un poco más de compresión para ayudar
                    "-tune", "zerolatency", # Ideal para capturas en tiempo real
                ])

                if CONFIG.get("mic"):
                    cmd.extend([
                        "-c:a", "aac",
                        "-b:a", AUDIO_BITRATE,
                        "-map", "0:v", "-map", "1:a"
                    ])
                cmd.append(temp_output_name)
                if audio_plan.get("enabled"):
                    monitor_output = audio_plan.get("monitor_output") or "default"
                    monitor_cmd = [
                        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-nostats",
                        "-thread_queue_size", "4096",
                        "-f", "alsa", "-ar", "48000", "-ac", "1",
                        "-i", audio_plan.get("monitor_source"),
                        "-vn",
                        "-f", "alsa", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "1",
                        monitor_output
                    ]
                    with open("audio_monitor_log.txt", "wb") as f:
                        monitor_proc = subprocess.Popen(monitor_cmd, stdout=f, stderr=subprocess.STDOUT)
                        if monitor_proc.poll() is not None:
                            logger.warning("El proceso del monitor de audio para grabación falló al arrancar; se desactiva")
                            monitor_proc = None
                with open("rec_log.txt", "wb") as f:
                    ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                recording = True
                start_blink()
            elif not recTake and recording:
                print("🛑 Deteniendo grabación...")
                if ffmpeg_proc and ffmpeg_proc.stdin:
                    try:
                        ffmpeg_proc.stdin.close()
                    except:
                        pass
                for p in [ffmpeg_proc, monitor_proc]:
                    if p:
                        try:
                            p.terminate()
                            p.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            p.kill()
                if temp_output_name and final_output_name and os.path.exists(temp_output_name):
                    if remux_recording_to_mp4(temp_output_name, final_output_name):
                        try:
                            os.remove(temp_output_name)
                        except Exception:
                            pass
                ffmpeg_proc = None
                temp_output_name = None
                final_output_name = None
                recording = False
                stop_blink()
            if recording and ffmpeg_proc:
                try:
                    ffmpeg_proc.stdin.write(memoryview(frame))
                except Exception as e:
                    print("⚠️ Error escribiendo a ffmpeg_proc stdin:", e)
                    recording = False
                    recTake = False
                    if ffmpeg_proc and ffmpeg_proc.stdin:
                        try:
                            ffmpeg_proc.stdin.close()
                        except:
                            pass
                    try:
                        ffmpeg_proc.terminate()
                        ffmpeg_proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        ffmpeg_proc.kill()
                    ffmpeg_proc = None
            # DrmPreview maneja la salida HDMI automáticamente
    except Exception as e:
        stop_error = True
        logger.error("❌ Error en hilo video: %s", e)
        stop_blink()
        changeRunningCamera(False)
    finally:
        video_thread_running.clear()
        try:
            release_camera_resources(picam2, wait_seconds=0.2)
        except Exception:
            pass
        # DrmPreview se cierra automaticamente con picam2
        print("🔴 Hilo de captura de rec parado.")
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

def restart_rec_thread():
    global video_thread, picam2, last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        logger.debug("⏳ Ignorado: debounce activo.")
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

    logger.info("▶️ Iniciando nuevos hilos de rec...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()


def capture_rec():
    global recTake, last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        logger.debug("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now
    
    recTake = not recTake

def apply_config_to_active_camera_rec(todo=False):
    global picam2, CONFIG
    if picam2 is not None:
        # Guardar valores críticos actuales
        old_resolution = str(CONFIG.get("resolution", ""))
        old_fps = str(CONFIG.get("fps", ""))
        old_bitrate = str(CONFIG.get("bitrate", ""))
        old_mic = str(CONFIG.get("mic", ""))

        # Aplicar configuración a la cámara activa
        aplicar_camara_config(picam2, todo)
        CONFIG = load_config()

        # Valores nuevos tras aplicar configuración
        new_resolution = str(CONFIG.get("resolution", ""))
        new_fps = str(CONFIG.get("fps", ""))
        new_bitrate = str(CONFIG.get("bitrate", ""))
        new_mic = str(CONFIG.get("mic", ""))

        # Si hay cambios en resolución, fps, bitrate o micrófono, reiniciar hilo de grabación
        if todo or (old_resolution != new_resolution) or (old_fps != new_fps) or (old_bitrate != new_bitrate) or (old_mic != new_mic):
            logger.info("🔁 Cambios críticos en config detectados; reiniciando hilo de grabación.")
            try:
                restart_rec_thread()
            except Exception as e:
                logger.error("❌ Error reiniciando hilo rec: %s", e)

ESTIMADO_MB_POR_MINUTO = 370
minutos_restantes = 0

def minutos_disponibles(path="/home/pi/Unicam/videos"):
    # Obtiene espacio libre en MB
    total, usado, libre = shutil.disk_usage(path)
    libre_mb = libre / (1024 * 1024)
    # Calcula minutos disponibles
    return int(libre_mb / ESTIMADO_MB_POR_MINUTO)
