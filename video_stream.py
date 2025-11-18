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

video_thread = None
preview_thread = None

video_thread_running = threading.Event()
rtsp_thread_running = threading.Event()

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

def video_stream_thread():
    video_thread_running.set()
    print("📡 Hilo de video stream iniciado.")
    global picam2, zoom_state, latest_frame, frame_lock, CONFIG, WIDTH, HEIGHT, TARGET_FPS
    
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
    
    generar_sdp(ip=CONFIG.get("IPSDP"))

    cmd = [
        'ffmpeg',
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-r', str(TARGET_FPS),
        '-i', '-',
        '-g', '60',
        '-c:v', 'libx264',
        '-preset', CONFIG.get("preset"), #superfast
        "-b:v", CONFIG.get("bitrate"), #12
        "-maxrate", CONFIG.get("bitrate"), #12
        "-bufsize", CONFIG.get("bitrate"), #12
        '-tune', 'zerolatency',
        '-x264opts', 'keyint=30:scenecut=0:repeat-headers=1',
        '-f', 'rtsp',
        '-rtsp_transport', CONFIG.get("protocolo"),
        #"-loglevel", "debug",
        f'{CONFIG.get("IPDestino")}'
    ]
    
    cmd_srt = [
        'ffmpeg',
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-r', str(TARGET_FPS),
        '-i', '-',
        '-g', '60',
        '-c:v', 'libx264',
        '-preset', CONFIG.get("preset"),
        "-b:v", CONFIG.get("bitrate"),
        "-maxrate", CONFIG.get("bitrate"),
        "-bufsize", CONFIG.get("bitrate"),
        '-tune', 'zerolatency',
        '-x264opts', 'keyint=30:scenecut=0:repeat-headers=1',
        '-f', 'mpegts',
        f'srt://{CONFIG.get("IPDestinoSRT")}:{CONFIG.get("puertoDestinoSRT")}{CONFIG.get("extraDataSRT")}'
    ]
    
    proc = None
    
    if CONFIG.get("protocolo_stream") == "RTSP":
        with open("stream_log.txt", "wb") as f:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)

    if CONFIG.get("protocolo_stream") == "SRT":
        with open("stream_log.txt", "wb") as f:
            proc = subprocess.Popen(cmd_srt, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)

    stop_error = False
    start_blink()
    
    try:
        while video_thread_running.is_set() and not stop_error:
            try:
                frame = picam2.capture_array("main")
                current_zoom = zoom_state['factor']
                frame = zoom_yuv420(frame, WIDTH, HEIGHT, current_zoom)
                proc.stdin.write(memoryview(frame))
                latest_frame = memoryview(frame)
            except Exception as e:
                stop_error = True
                print("❌ Error en stream video:", e)
                PrintImageDisplay("img/error_stream.png")
    except Exception as e:
        stop_error = True
        print("❌ Error en hilo video:", e)
    finally:
        video_thread_running.clear()
        proc.stdin.close()
        proc.wait()
        picam2.close()
        cv2.destroyAllWindows()
        print("🔴 Hilo de video stream parado.")
        PrintImageDisplay("img/error_stream.png")
        stop_blink()

last_restart_time = 0
debounce_delay = 1.0  # segundos
def restart_video_thread():
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

    print("▶️ Iniciando nuevos hilos de video...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()
    preview_thread = Thread(target=lcd_preview_thread)
    preview_thread.start()

def lcd_preview_thread(): 
    global latest_frame, CONFIG
    start_time = datetime.now()
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
            zm = round(zoom_state['factor'], 2)
            Alevel = 100
            mute = True
                
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
                print("❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌")
                print("FFmpeg RTSP murió. Revisa ffmpeg_log.txt para detalles.")
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
    
from gpio_control import start_blink, stop_blink