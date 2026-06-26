import threading
import time
import subprocess
import logging
from flask import request
from picamera2 import Picamera2
from picamera2.previews import DrmPreview
import cv2
from camera_config import WIDTH, HEIGHT, TARGET_FPS, IPDestino, aplicar_camara_config, generar_sdp, CONFIG, picam2, load_config, changeRunningCamera, getMute, get_audio_level
from threading import Thread
from lcd_preview import LCDPreview, monitorState, PrintImageDisplay, InMenu, lcd_preview, getInMenuState, getMonitorState
from queue import Queue, Empty
from PIL import Image, ImageOps
import time
import numpy as np
from datetime import datetime
import os

# Configurar logging para capturar mensajes de este módulo
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
    # Fallback: create a tmp runtime dir with safe perms
    fallback = f"/tmp/xdg-runtime-{os.getpid()}"
    try:
        os.makedirs(fallback, exist_ok=True)
        os.chmod(fallback, 0o700)
        os.environ["XDG_RUNTIME_DIR"] = fallback
    except Exception:
        os.environ["XDG_RUNTIME_DIR"] = "/tmp"

video_thread = None
preview_thread = None

video_thread_running = threading.Event()
rtsp_thread_running = threading.Event()

stream_proc = None
unclutter_proc = None
watchdog_thread = None
watchdog_running = threading.Event()
restart_lock = threading.Lock()

zoom_lock = threading.Lock()
zoom_state = {'direction': 0, 'factor': 1.0}
zoom_var = 0.04

latest_frame = None  # va a contener siempre el último frame
frame_lock = threading.Lock()

def zoom_loop():
    while True:
        if zoom_state['direction'] != 0:
            zoom_state['factor'] = max(1.0, min(4.0, zoom_state['factor'] + zoom_state['direction'] * zoom_var))
        time.sleep(0.05)

# Arrancamos un único hilo para siempre
threading.Thread(target=zoom_loop, daemon=True).start()


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
    video_thread_running.set()
    logger.info("📡 Hilo de video stream iniciado.")
    global picam2, zoom_state, latest_frame, frame_lock, CONFIG, WIDTH, HEIGHT, TARGET_FPS, stream_proc, unclutter_proc
    
    CONFIG = load_config()
    mic_path = CONFIG.get("mic")
    is_mic_enabled = mic_path and not mic_path.startswith('!')
    if is_mic_enabled:
        logger.info(f"Micrófono detectado y activo: {mic_path}")
    else:
        CONFIG["mic"] = ""
        logger.info("Micrófono desactivado o comentado con '!'. Solo de video.")
    WIDTH, HEIGHT = map(int, CONFIG["resolution"].lower().split("x"))
    TARGET_FPS = CONFIG["fps"]

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH, HEIGHT)}
    )
    picam2.configure(config)
    
    # Iniciar DrmPreview después de picam2.start()
    opcion_hdmi = CONFIG.get("hdmi")
    if opcion_hdmi != "Off":
        time.sleep(0.5)  # Esperar a que se estabilice
        try:
            # DrmPreview con full screen: x=0, y=0, width y height de la pantalla
            picam2.start_preview(DrmPreview(x=0, y=0, width=1920, height=1080))
            logger.info("✅ DrmPreview iniciado para HDMI (1920x1080)")
        except Exception as e:
            logger.error(f"⚠️ No se pudo iniciar DrmPreview: {e}")

    picam2.start()
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
        cmd.extend([
            '-thread_queue_size', '512',
            '-f', 'alsa',
            '-ar', '48000',
            '-ac', '1',
            '-fragment_size', '512',
            '-i', CONFIG.get('mic'),
            '-c:a', 'aac',
            '-b:a', '96k',
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
        cmd_srt.extend([
            '-thread_queue_size', '512',
            '-f', 'alsa',
            '-ar', '48000',
            '-ac', '1',
            '-i', CONFIG.get('mic')
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
            '-b:a', '128k',
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

    # Expose subprocess to watchdog
    stream_proc = proc

    stop_error = False
    _safe_start_blink()
    changeRunningCamera(True)

    try:
        while video_thread_running.is_set() and not stop_error:
            try:
                frame = picam2.capture_array("main")
                current_zoom = zoom_state['factor']
                frame = zoom_yuv420(frame, WIDTH, HEIGHT, current_zoom)
                proc.stdin.write(memoryview(frame))
                # DrmPreview maneja la salida HDMI automáticamente
                latest_frame = memoryview(frame)
            except Exception as e:
                stop_error = True
                logger.error("Error en stream video: %s", e)
                PrintImageDisplay("img/error_stream.png")
                _safe_stop_blink()
                changeRunningCamera(False)
    except Exception as e:
        stop_error = True
        logger.error("Error en hilo video: %s", e)
        PrintImageDisplay("img/error_stream.png")
        _safe_stop_blink()
        changeRunningCamera(False)
    finally:
        video_thread_running.clear()
        if proc and proc.stdin:
            try:
                proc.stdin.close()
            except:
                pass
        # DrmPreview se cierra automáticamente con picam2
        for p in [proc]:
            if p:
                try:
                    p.terminate()
                    p.wait(timeout=2) 
                except subprocess.TimeoutExpired:
                    p.kill()
        # Clear watchdog-visible process
        try:
            stream_proc = None
        except:
            pass
        picam2.close()
        cv2.destroyAllWindows()
        logger.info("🔴 Hilo de video stream parado.")
        PrintImageDisplay("img/error_stream.png")
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
        video_thread.join()
    time.sleep(1)

    logger.info("▶️ Iniciando nuevos hilos de video...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()
    preview_thread = Thread(target=lcd_preview_thread)
    preview_thread.start()
    # arrancar watchdog que vigila el proceso ffmpeg
    try:
        start_stream_watchdog()
    except Exception:
        pass

def lcd_preview_thread(): 
    global latest_frame, CONFIG
    start_time = datetime.now()
    last_cfg_update = 0
    UPDATE_DELAY = 2   # actualizar cada 2 segundos
    ae_mode = "AUTO"
    wb_mode = "AUTO"
    Alevel = 100
    mute = True
    
    try:
        while video_thread_running.is_set():
            if not getMonitorState():
                time.sleep(0.1)
                continue
                
            if getInMenuState():
                time.sleep(0.1)
                continue
                
            if latest_frame is None:
                time.sleep(0.01)
                continue
                
            # Actualizar CONFIG cada X segundos
            now = time.time()
            if now - last_cfg_update >= UPDATE_DELAY:
                try:
                    CONFIG = load_config()
                    last_cfg_update = now
                except:
                    pass
                
                ae_mode = "AUTO"
                if not CONFIG.get("AeEnable"):
                    ae_mode = "MANUAL"
                
                wb_mode = "AUTO"
                if not CONFIG.get("AwbEnable"):
                    wb_mode = "MANUAL"
                    
                if getMute():
                    Alevel = 100
                    mute = True
                else:
                    Alevel = 44#get_audio_level()
                    mute = False
                    
            elapsed_seconds = (datetime.now() - start_time).seconds
            zm = round(zoom_state['factor'], 2)
            
            lcd_preview.show(latest_frame, width=WIDTH, height=HEIGHT, fps=TARGET_FPS, elapsed_seconds=elapsed_seconds, af_mode=ae_mode, wb_mode=wb_mode, zm=zm, recording=False, stream_active=True, mode="STR", Alevel=Alevel, mute=mute, bitrate=CONFIG.get("bitrate"))
            
            time.sleep(0.01)
    except Exception as e:
        print("Error en lcd_preview_thread_fast:", e)

def apply_config_to_active_camera(todo=False):
    global picam2, CONFIG
    if picam2 is not None:
        aplicar_camara_config(picam2, todo)
        CONFIG = load_config()

def zoom_yuv420(frame, width, height, zoom_factor):
    if zoom_factor == 1.0:
        return memoryview(frame)
    yuv = frame.reshape((height*3//2, width))
    bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
    new_w, new_h = int(width * zoom_factor), int(height * zoom_factor)
    bgr_zoom = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    start_x = (new_w - width)//2
    start_y = (new_h - height)//2
    bgr_crop = bgr_zoom[start_y:start_y+height, start_x:start_x+width]
    yuv_zoom = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2YUV_I420)
    return yuv_zoom.ravel()

def rtp_to_rtsp_thread():
    rtsp_thread_running.set()
    cmd = [
        'ffmpeg',
        '-protocol_whitelist', 'file,udp,rtp',
        '-i', 'stream.sdp',
        '-c', 'copy',
        '-f', 'rtsp',
        'rtsp://localhost:8554/cam'
    ]
    cmd2 = [
        'ffmpeg',
        '-protocol_whitelist', 'file,udp,rtp',
        '-i', 'stream.sdp',
        '-c', 'copy',
        '-f', 'rtsp',
        CONFIG.get("IPDestino")
    ]
    with open("ffmpeg_log.txt", "wb") as f:
        proc = subprocess.Popen(cmd2, stdout=f, stderr=subprocess.STDOUT)
    try:
        while rtsp_thread_running.is_set():
            if proc.poll() is not None:  # FFmpeg terminó
                logger.error("FFmpeg RTSP murió. Revisa ffmpeg_log.txt para detalles.")
                rtsp_thread_running.clear()
                video_thread_running.clear()
                break
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            proc.terminate()

def zoom():
    direction = request.form.get('direction')
    with zoom_lock:
        if direction == 'in':
            zoom_state['direction'] = +1
        elif direction == 'out':
            zoom_state['direction'] = -1
        elif direction == 'stop':
            zoom_state['direction'] = 0
    return ('', 204)
    

def stream_watchdog():
    """Monitorea el proceso ffmpeg en `stream_proc` y reinicia usando
    `restart_video_thread()` si `AutoReconnect` está activado en la configuración.
    Ejecuta en un hilo daemon separado."""
    global stream_proc, watchdog_running
    while watchdog_running.is_set():
        try:
            proc = stream_proc
            if proc is not None:
                if proc.poll() is not None:  # ffmpeg terminó
                    cfg = load_config()
                    if cfg.get("AutoReconnect"):
                        logger.info("[watchdog] ffmpeg murió, intentando reiniciar stream...")
                        try:
                            with restart_lock:
                                restart_video_thread()
                        except Exception as e:
                            logger.error("[watchdog] reinicio fallido: %s", e)
                            time.sleep(2)
                        else:
                            # dar tiempo al nuevo hilo para arrancar
                            time.sleep(2)
                    else:
                        watchdog_running.clear()
                        break
        except Exception as e:
            logger.error("[watchdog] error: %s", e)
        time.sleep(3)


def start_stream_watchdog():
    global watchdog_thread, watchdog_running
    if watchdog_thread and watchdog_thread.is_alive():
        return
    watchdog_running.set()
    watchdog_thread = threading.Thread(target=stream_watchdog, daemon=True)
    watchdog_thread.start()