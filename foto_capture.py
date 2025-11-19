import threading
import time
import subprocess
from flask import request
from picamera2 import Picamera2
import cv2
from camera_config import WIDTH, HEIGHT, TARGET_FPS, IPDestino, aplicar_camara_config, generar_sdp, CONFIG, picam2
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

video_thread = None
preview_thread = None

video_thread_running = threading.Event()

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
    config = picam2.create_still_configuration(
        main={"format": "YUV420", "size": (WIDTH2, HEIGHT2)},
        buffer_count=2
    )
    picam2.configure(config)
    picam2.start()
    aplicar_camara_config(picam2, True)

    start_time = time.time()
    frame_count = 0
    stop_error = False
    
    try:
        while video_thread_running.is_set() and not stop_error:
            try:
                frame = picam2.capture_array("main")
                if fotoTake:
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
                # --- MOSTRAR EN MONITOR ---
                latest_frame = memoryview(frame)
            except Exception as e:
                stop_error = True
                print("❌ Error capturando frame:", e)
    except Exception as e:
        stop_error = True
        print("❌ Error en hilo video:", e)
    finally:
        video_thread_running.clear()
        picam2.close()
        cv2.destroyAllWindows()
        print("🔴 Hilo de captura de foto parado.")
        PrintImageDisplay("img/error_stream.png")

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