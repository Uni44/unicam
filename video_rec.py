import threading
import time
import subprocess
from flask import request
from picamera2 import Picamera2
import cv2
from camera_config import WIDTH, HEIGHT, TARGET_FPS, IPDestino, aplicar_camara_config, generar_sdp, CONFIG, picam2, load_config
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
import os, psutil
import shutil

video_thread = None
preview_thread = None

video_thread_running = threading.Event()

latest_frame = None  # va a contener siempre el último frame
frame_lock = threading.Lock()

recTake = False

# Crear carpeta si no existe
carpeta = "videos"
os.makedirs(carpeta, exist_ok=True)

def video_stream_thread():
    video_thread_running.set()
    print("📡 Hilo de captura de rec iniciado.")
    
    global picam2, zoom_state, latest_frame, frame_lock, recTake
    from gpio_control import start_blink, stop_blink

    CONFIG = load_config()
    WIDTH, HEIGHT = map(int, CONFIG["resolution"].lower().split("x"))
    TARGET_FPS = CONFIG["fps"]

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH, HEIGHT)}
    )
    picam2.configure(config)
    picam2.start()
    aplicar_camara_config(picam2, True)
    
    stop_error = False
    recording = False
    try:
        while video_thread_running.is_set() and not stop_error:
            frame = picam2.capture_array("main")
            current_zoom = zoom_state['factor']
            frame = zoom_yuv420(frame, WIDTH, HEIGHT, current_zoom)
            
            if recTake and not recording:
                print("🎬 Iniciando grabación...")
                output_name = os.path.join(carpeta, time.strftime("record_%Y%m%d_%H%M%S.mp4"))
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "rawvideo",
                    "-pix_fmt", "yuv420p",
                    "-s", f"{WIDTH}x{HEIGHT}",
                    '-r', str(TARGET_FPS),
                    "-i", "-",
                    "-c:v", "libx264",
                    "-preset", CONFIG.get("preset"),
                    "-crf", "20",
                    #"-fps_mode", "passthrough",
                    output_name
                ]
                with open("rec_log.txt", "wb") as f:
                    ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                recording = True
                start_blink()
            elif not recTake and recording:
                print("🛑 Deteniendo grabación...")
                ffmpeg_proc.stdin.close()
                ffmpeg_proc.wait(timeout=3)
                ffmpeg_proc = None
                recording = False
                stop_blink()
            if recording and ffmpeg_proc:
                ffmpeg_proc.stdin.write(memoryview(frame))
            latest_frame = memoryview(frame)
    except Exception as e:
        stop_error = True
        print("❌ Error en hilo video:", e)
    finally:
        video_thread_running.clear()
        picam2.close()
        cv2.destroyAllWindows()
        print("🔴 Hilo de captura de rec parado.")
        PrintImageDisplay("img/error_stream.png")
        stop_blink()

last_restart_time = 0
debounce_delay = 1.0  # segundos
def restart_rec_thread():
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

    print("▶️ Iniciando nuevos hilos de rec...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()
    preview_thread = Thread(target=lcd_preview_thread, daemon=True)
    preview_thread.start()

def capture_rec():
    global recTake, last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        print("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now
    
    recTake = not recTake

def apply_config_to_active_camera_rec(todo=False):
    global picam2, CONFIG
    if picam2 is not None:
        aplicar_camara_config(picam2, todo)
        CONFIG = load_config()

ESTIMADO_MB_POR_MINUTO = 370
minutos_restantes = 0

def minutos_disponibles(path="/home/pi/Unicam/videos"):
    # Obtiene espacio libre en MB
    total, usado, libre = shutil.disk_usage(path)
    libre_mb = libre / (1024 * 1024)
    # Calcula minutos disponibles
    return int(libre_mb / ESTIMADO_MB_POR_MINUTO)

def set_low_priority():
    p = psutil.Process(os.getpid())
    try:
        p.nice(10)  # mayor número = menos prioridad (Linux)
    except Exception:
        pass

def lcd_preview_thread(): 
    set_low_priority()
    global latest_frame, minutos_restantes
    start_time = datetime.now()
    recording = False
    last_info_update = 0
    minutos_restantes = minutos_disponibles()
    last_cfg_update = 0
    UPDATE_DELAY = 2   # actualizar cada 2 segundos
    ae_mode = "AUTO"
    wb_mode = "AUTO"
    
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
                
            elapsed_seconds = 0
                
            if recording and not recTake:
                recording = False
                
            if not recording and recTake:
                start_time = datetime.now()
                recording = True
                
            if recording and recTake:
                elapsed_seconds = (datetime.now() - start_time).seconds
                
            if time.time() - last_info_update > 60:
                minutos_restantes = minutos_disponibles()
                last_info_update = time.time()
                
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
                
            zm = round(zoom_state['factor'], 2)
            Alevel = 100
            mute = True
            
            lcd_preview.show(memoryview(latest_frame), width=WIDTH, height=HEIGHT, fps=TARGET_FPS, elapsed_seconds=elapsed_seconds, af_mode=ae_mode, wb_mode=wb_mode, zm=zm, recording=recTake, stream_active=False, mode="REC", Alevel=Alevel, mute=mute, bitrate=f"{minutos_restantes}M")
            
            time.sleep(0.01)
    except Exception as e:
        print("Error en lcd_preview_thread_fast:", e)