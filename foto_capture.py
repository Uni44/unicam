import threading
import time
import subprocess
from flask import request
from picamera2 import Picamera2
import cv2
from camera_config import WIDTH, HEIGHT, TARGET_FPS, IPDestino, aplicar_camara_config, generar_sdp, CONFIG, picam2, changeRunningCamera, load_config
from threading import Thread
from lcd_preview import LCDPreview, monitorState, PrintImageDisplay, InMenu, lcd_preview, getInMenuState, getMonitorState
from queue import Queue
from PIL import Image, ImageOps
from queue import Empty
import time
import numpy as np
from datetime import datetime
from video_stream import (
    zoom_lock, zoom_state, zoom_var, zoom_loop, zoom, zoom_yuv420
)
import os


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

video_thread = None
preview_thread = None

video_thread_running = threading.Event()

proc_hdmi = None
hdmi_restart_event = threading.Event()
hdmi_write_lock = threading.Lock()
hdmi_paused = threading.Event()

latest_frame = None  # va a contener siempre el último frame
frame_lock = threading.Lock()

fotoTake = False

# Crear carpeta si no existe
carpeta = "fotos"
os.makedirs(carpeta, exist_ok=True)

def video_stream_thread():
    video_thread_running.set()
    print("📡 Hilo de captura de foto iniciado.")
    
    global picam2, zoom_state, latest_frame, frame_lock, fotoTake
    from gpio_control import start_blink, stop_blink

    WIDTH2, HEIGHT2 = 4608, 2592

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH2, HEIGHT2)},
        buffer_count=2
    )
    picam2.configure(config)
    picam2.start()
    aplicar_camara_config(picam2, True)

    changeRunningCamera(True)

    start_time = time.time()
    frame_count = 0
    stop_error = False
    
    # Deshabilitar el mouse a nivel de X11
    os.system('xset m 0 0 2>/dev/null || true')
    # Ocultar con unclutter
    subprocess.Popen(['unclutter', '-idle', '0', '-keystroke'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Mover el cursor fuera de pantalla
    os.system('xdotool mousemove 9999 9999 2>/dev/null || true')
    hdmiState = True
    opcion_hdmi = CONFIG.get("hdmi")
    global proc_hdmi
    if opcion_hdmi == "Off":
        hdmiState = False
    res_hdmi = f"{WIDTH}x{HEIGHT}"
    if opcion_hdmi == "Mid":
        res_hdmi = "1280x720"
    elif opcion_hdmi == "Low": # El tercero
        res_hdmi = "640x360"
    cmd_hdmi = [
        'ffmpeg',
        '-hide_banner', '-loglevel', 'error', '-nostats',
        '-fflags', 'nobuffer+genpts',
        '-flags', 'low_delay',
        '-use_wallclock_as_timestamps', '1',
        '-thread_queue_size', '4096',
        '-f', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-framerate', str(TARGET_FPS),
        '-i', '-', 
        '-vf', f'scale={res_hdmi}:flags=neighbor,format=rgb565le', 
        '-f', 'fbdev',
        '-fps_mode', 'passthrough',
        '/dev/fb0'
    ]
    if hdmiState:
        ensure_xdg_runtime_dir()
        with open("hdmi_log.txt", "ab") as f:
            try:
                proc_hdmi = subprocess.Popen(cmd_hdmi, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                time.sleep(0.12)
            except Exception as e:
                print("❌ No se pudo iniciar HDMI ffmpeg:", e)
                proc_hdmi = None
    
    try:
        while video_thread_running.is_set() and not stop_error:
            try:
                frame = picam2.capture_array("main")
                # Handle external HDMI restart requests
                if hdmi_restart_event.is_set():
                    hdmi_restart_event.clear()
                    try:
                        hdmi_write_lock.acquire()
                        hdmi_paused.set()
                        if proc_hdmi:
                            try:
                                if proc_hdmi.stdin:
                                    try:
                                        proc_hdmi.stdin.close()
                                    except Exception:
                                        pass
                                proc_hdmi.terminate()
                                proc_hdmi.wait(timeout=1)
                            except Exception:
                                try:
                                    proc_hdmi.kill()
                                except Exception:
                                    pass
                            proc_hdmi = None
                        ensure_xdg_runtime_dir()
                        with open("hdmi_log.txt", "ab") as f:
                            try:
                                proc_hdmi = subprocess.Popen(cmd_hdmi, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                                print("🔁 HDMI ffmpeg forzado reiniciado (foto).")
                                time.sleep(0.12)
                            except Exception as e:
                                print("❌ Falló forzar reinicio HDMI ffmpeg (foto):", e)
                                proc_hdmi = None
                    except Exception as er:
                        print("⚠️ Error forzando reinicio HDMI (foto):", er)
                    finally:
                        hdmi_paused.clear()
                        try:
                            hdmi_write_lock.release()
                        except Exception:
                            pass
                if fotoTake:
                    print("fototate")
                    start_blink()
                    for i in range(10):  # cantidad de fotos
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        nombre_archivo = f"foto_{timestamp}.jpg"
                        ruta_completa = os.path.join(carpeta, nombre_archivo)
                        print("✅ Foto guardada en", ruta_completa)
                        picam2.capture_file(ruta_completa)
                        time.sleep(0.2)
                    stop_blink()
                    fotoTake = False
                # Try to write to HDMI with brief lock to avoid race with restart
                try:
                    if hdmi_write_lock.acquire(timeout=0.02):
                        try:
                            if hdmiState and proc_hdmi and not hdmi_paused.is_set() and proc_hdmi.stdin:
                                try:
                                    proc_hdmi.stdin.write(memoryview(frame))
                                except BrokenPipeError:
                                    print("⚠️ BrokenPipe al escribir HDMI (foto), reiniciando proc_hdmi")
                                    try:
                                        proc_hdmi.terminate()
                                    except Exception:
                                        pass
                                    proc_hdmi = None
                                except Exception as e:
                                    stop_error = True
                                    print("❌ Error escribiendo frame a HDMI:", e)
                                    try:
                                        if proc_hdmi:
                                            proc_hdmi.terminate()
                                    except Exception:
                                        pass
                                    proc_hdmi = None
                        finally:
                            hdmi_write_lock.release()
                except Exception:
                    # couldn't acquire lock fast - skip writing this frame
                    pass
                latest_frame = memoryview(frame)
            except Exception as e:
                stop_error = True
                print("❌ Error capturando frame:", e)
                PrintImageDisplay("img/error_stream.png")
                stop_blink()
                changeRunningCamera(False)
    except Exception as e:
        stop_error = True
        print("❌ Error en hilo video:", e)
        PrintImageDisplay("img/error_stream.png")
        stop_blink()
        changeRunningCamera(False)
    finally:
        video_thread_running.clear()
        picam2.close()
        cv2.destroyAllWindows()
        print("🔴 Hilo de captura de foto parado.")
        PrintImageDisplay("img/error_stream.png")
        stop_blink()
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
    preview_thread = Thread(target=lcd_preview_thread)
    preview_thread.start()


def request_hdmi_restart():
    """Request the foto capture thread to restart its HDMI ffmpeg process."""
    try:
        hdmi_restart_event.set()
        return True
    except Exception:
        return False

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

def lcd_preview_thread():
    global latest_frame, CONFIG
    start_time = datetime.now()
    last_cfg_update = 0
    UPDATE_DELAY = 2   # actualizar cada 2 segundos
    
    ae_mode = "AUTO"
    wb_mode = "AUTO"
    
    WIDTH2, HEIGHT2 = 4608, 2592
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
                
            elapsed_seconds = (datetime.now() - start_time).seconds
            zm = 0
            Alevel = 100
            mute = True
            
            lcd_preview.show(latest_frame, width=WIDTH2, height=HEIGHT2, fps=15, elapsed_seconds=elapsed_seconds, af_mode=ae_mode, wb_mode=wb_mode, zm=zm, recording=False, stream_active=fotoTake, mode="FOT", Alevel=Alevel, mute=mute)
            
            time.sleep(0.01)
    except Exception as e:
        print("Error en lcd_preview_thread_fast:", e)