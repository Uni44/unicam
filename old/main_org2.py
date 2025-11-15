from flask import Flask, render_template_string
from flask import Response, request
from flask_socketio import SocketIO
import cv2
import threading
import time
from flask import jsonify
from html import HTML_PW, HTML_OR, HTML_INICIO, HTML_COF
import json
import os
import queue
from concurrent.futures import ThreadPoolExecutor
import psutil
from gpiozero import LED, Button, Motor, OutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from turbojpeg import TurboJPEG
from picamera2 import Picamera2
import numpy as np
import requests
import subprocess

turbo_jpeg = TurboJPEG("/usr/lib/aarch64-linux-gnu/libturbojpeg.so")

# Guardamos el momento en que arranca la app
start_time = time.time()

# GPIO PINS
factory = LGPIOFactory()
led = LED(5, pin_factory=factory)
BUTTON_PINS = {
    'btn1': 26,
    'btn2': 16,
    'btn3': 12,
    'btn4': 4,
    'btn5': 22,
    'btn6': 27,
}
#motorZoom = Motor(forward=17, backward=27)  # forward = IN1, backward = IN2

# Pines GPIO (ajústalos según tu conexión)
DIR_PIN = 21  # Dirección
STEP_PIN = 20  # Pulsos

# Configuración de pines
#dir_pin = OutputDevice(DIR_PIN)
#step_pin = OutputDevice(STEP_PIN)

# Controles
blinking = False
focus_running = False
focus_thread = None

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode="threading")

# Config del GPIO
# Crear objetos Button con pull_up=True (equivalente a pull-up interno)
buttons = {name: Button(pin, pull_up=True, pin_factory=factory) for name, pin in BUTTON_PINS.items()}
    
CONFIG_FILE = "camera_config.json"

# Cargar configuración desde archivo
def load_config():
    default_config = {
        # Valores normalizados (0.0 a 1.0) o escalados correctos
        "brightness": 0.5,        # 0.0 - 1.0
        "contrast": 0.5,          # 0.0 - 1.0
        "saturation": 0.5,        # 0.0 - 1.0
        "sharpness": 0.5,         # 0.0 - 1.0
        "exposure": 0.5,          # 0.0 - 1.0 (si está en manual)
        "gamma": 1.0,             # Normalizado, típicamente 0.1 - 5.0
        "gain": 1.0,              # 1.0 es neutro, subir = más ISO
        "temperature": 4500,      # Kelvin (2000 = cálido, 8000 = frío)
        "whitebalance": "auto",   # auto | incandescent | fluorescent | daylight | cloudy
        "exposure-mode": "auto",  # auto | night | backlight | sports...
        
        # Resolución / FPS / Calidad
        "resolution": "1920x1080", 
        "fps": 30, 
        "calidad": 80,            # JPEG calidad (0-100)

        # Vista previa (más liviana para streaming)
        "resolutionVista": "640x480",
        "fpsVista": 24,
        "calidadVista": 50
    }

    if not os.path.exists(CONFIG_FILE):
        return default_config

    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)

    # Agregar claves nuevas si el archivo existe pero está incompleto
    for key, val in default_config.items():
        data.setdefault(key, val)

    return data

CONFIG = load_config()

VIDEO_PATH = "test.mp4"
WIDTH, HEIGHT = 1920, 1080
cap = None
camera_thread = None
running = False
picam2 = None

# 🔢 Actualizar resolución
res = CONFIG["resolution"]
if isinstance(res, str) and "x" in res:
    try:
        WIDTH, HEIGHT = map(int, res.lower().split("x"))
        print(f"✅ Resolución actualizada a {WIDTH}x{HEIGHT}")
    except ValueError:
        print(f"⚠️ Error al parsear resolución: {res}")
else:
    print(f"⚠️ Resolución inválida: {res}")

TARGET_FPS = CONFIG["fps"]
JPEG_QUALITY = int(CONFIG["calidad"])
zoom_factor = 1
zoom_lock = threading.Lock()
zoom_var = 0.04
zooming_in = False
zooming_out = False

PREVIEW_WIDTH, PREVIEW_HEIGHT = 1280, 720

# Cola para compartir frames entre hilos
latest_frame = None
frame_lock = threading.Lock()

# 🔢 Actualizar resolución
res = CONFIG["resolutionVista"]
if isinstance(res, str) and "x" in res:
    try:
        PREVIEW_WIDTH, PREVIEW_HEIGHT = map(int, res.lower().split("x"))
        print(f"✅ Resolución vista actualizada a {PREVIEW_WIDTH}x{PREVIEW_HEIGHT}")
    except ValueError:
        print(f"⚠️ Error al parsear resolución vista: {res}")
else:
    print(f"⚠️ Resolución vista inválida: {res}")

PREVIEW_FPS = int(CONFIG["fpsVista"])
PREVIEW_JPEG_QUALITY = int(CONFIG["calidadVista"])

video_thread = None
video_thread_running = threading.Event()
jpeg_thread = None

video_vista_thread = None
jpeg_thread_vista = None
video_vista_thread_running = threading.Event()

frame_queue = queue.Queue(maxsize=1)  # ajusta maxsize si quieres más buffer
frame_queue_vista = queue.Queue(maxsize=1)  # ajusta maxsize si quieres más buffer

def save_config(data):
    global CONFIG, WIDTH, HEIGHT, TARGET_FPS, JPEG_QUALITY, PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_FPS, PREVIEW_JPEG_QUALITY

    # Capturar valores anteriores
    prev_width = WIDTH
    prev_height = HEIGHT
    prev_fps = TARGET_FPS

    prev_preview_width = PREVIEW_WIDTH
    prev_preview_height = PREVIEW_HEIGHT
    prev_preview_fps = PREVIEW_FPS

    # Guardar configuración en el archivo
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ Error guardando configuración: {e}")
        return

    CONFIG = data

    # 🔢 Actualizar resolución
    res = data.get("resolution", "1920x1080")
    if isinstance(res, str) and "x" in res:
        try:
            WIDTH, HEIGHT = map(int, res.lower().split("x"))
            print(f"✅ Resolución actualizada a {WIDTH}x{HEIGHT}")
        except ValueError:
            print(f"⚠️ Error al parsear resolución: {res}")
    else:
        print(f"⚠️ Resolución inválida: {res}")

    # 🎯 Actualizar FPS
    try:
        fps = int(data.get("fps", 30))
        if fps < 5:
            print("⚠️ FPS demasiado bajo, usando mínimo 5")
            fps = 5
        elif fps > 90:
            print("⚠️ FPS demasiado alto, usando máximo 90")
            fps = 90
        TARGET_FPS = fps
        print(f"✅ FPS objetivo: {TARGET_FPS}")
    except Exception as e:
        print(f"⚠️ FPS inválido: {e}")

    # 🖼️ Calidad JPEG
    try:
        calidad = int(data.get("calidad", 80))
        if 10 <= calidad <= 100:
            JPEG_QUALITY = calidad
        else:
            print("⚠️ Calidad fuera de rango (10–100), usando 80")
            JPEG_QUALITY = 80
        print(f"✅ Calidad JPEG: {JPEG_QUALITY}")
    except Exception as e:
        print(f"⚠️ Calidad inválida: {e}")
        
    # 🔢 Actualizar resolución
    res = data.get("resolutionVista", "1920x1080")
    if isinstance(res, str) and "x" in res:
        try:
            PREVIEW_WIDTH, PREVIEW_HEIGHT = map(int, res.lower().split("x"))
            print(f"✅ Resolución vista actualizada a {PREVIEW_WIDTH}x{PREVIEW_HEIGHT}")
        except ValueError:
            print(f"⚠️ Error al parsear resolución vista: {res}")
    else:
        print(f"⚠️ Resolución vista inválida: {res}")
        
    # 🎯 Actualizar FPS
    try:
        fpsVista = int(data.get("fpsVista", 24))
        if fpsVista < 5:
            print("⚠️ FPS vista demasiado bajo, usando mínimo 5")
            fpsVista = 5
        elif fpsVista > 90:
            print("⚠️ FPS vista demasiado alto, usando máximo 90")
            fpsVista = 90
        PREVIEW_FPS = int(fpsVista)
        print(f"✅ FPS vista objetivo: {PREVIEW_FPS}")
    except Exception as e:
        print(f"⚠️ FPS vista inválido: {e}")
        
    # 🖼️ Calidad JPEG
    try:
        calidadVista = int(data.get("calidadVista", 80))
        if 10 <= calidadVista <= 100:
            PREVIEW_JPEG_QUALITY = calidadVista
        else:
            print("⚠️ Calidad vista fuera de rango (10–100), usando 80")
            PREVIEW_JPEG_QUALITY = 80
        print(f"✅ Calidad vista JPEG: {PREVIEW_JPEG_QUALITY}")
    except Exception as e:
        print(f"⚠️ Calidad vista inválida: {e}")
        
    reiniciar_original = (WIDTH != prev_width or HEIGHT != prev_height or TARGET_FPS != prev_fps)
    reiniciar_vista = (PREVIEW_WIDTH != prev_preview_width or PREVIEW_HEIGHT != prev_preview_height or PREVIEW_FPS != prev_preview_fps)

    if reiniciar_original:
        print("🔁 Se requiere reiniciar la cámara original.")
        start_camera_reader(WIDTH, HEIGHT, TARGET_FPS)
        restart_video_thread()

    if reiniciar_vista:
        print("🔁 Se requiere reiniciar la cámara de vista previa.")
        restart_video_vista_thread()
    aplicar_camara_config()
    
import platform

def aplicar_camara_config():
    so = platform.system()
    # print(picam2.camera_controls)  # Te muestra todos los controles disponibles

    # Ajustes básicos (sliders normalizados 0.0 a 1.0)
    picam2.set_controls({
        "Brightness": CONFIG.get("brightness", 0.5),   # -1.0 a 1.0 (algunos drivers)
        "Contrast": CONFIG.get("contrast", 0.5),       # 0.0 a 1.0
        "Saturation": CONFIG.get("saturation", 0.5),   # 0.0 a 1.0
        "Sharpness": CONFIG.get("sharpness", 0.5),     # 0.0 a 1.0
        "AnalogueGain": CONFIG.get("gain", 1.0)        # 1.0 = ISO base
    })

    # White balance
    if CONFIG.get("whitebalance") != "auto":
        picam2.set_controls({
            "AwbEnable": False,
            "ColourTemperature": CONFIG.get("temperature", 4500),
            "AwbMode": int(CONFIG.get("awb-mode", 0))
        })
    else:
        picam2.set_controls({"AwbEnable": True, "AwbMode": 0})

    # Exposure
    if CONFIG.get("exposure-mode") == "auto":
        picam2.set_controls({
            "AeEnable": True
        })
    else:
        picam2.set_controls({
            "AeEnable": False,
            "ExposureTime": CONFIG.get("exposure", 0.5),
            "AnalogueGain": CONFIG.get("gain", 1.0),
            "AeExposureMode": int(CONFIG.get("ae-exposure-mode", 0)),
            "AeMetering": int(CONFIG.get("ae-metering", 0)),
            "AeConstraintMode": int(CONFIG.get("ae-constraint-mode", 0)),
            "AeFlickerMode": int(CONFIG.get("ae-flicker-mode", 0))
        })

    # Gamma (si está soportado por tu driver)
    gamma = CONFIG.get("gamma", 1.0)
    try:
        picam2.set_controls({"Gamma": gamma})  # Rango 0.1 – 5.0 aprox.
    except Exception:
        pass  # Algunas versiones no lo soportan

    picam2.set_controls({"Quality": 10})

    print("✅ Se aplicó la configuración de la cámara Arducam.")

# Obtener configuración actual
@app.route("/api/camera-config", methods=["GET"])
def get_camera_config():
    return jsonify(load_config())

# Guardar configuración nueva
@app.route("/api/camera-config", methods=["POST"])
def update_camera_config():
    data = request.get_json()
    save_config(data)
    return jsonify({"status": "ok", "message": "Configuración guardada"})
        
def apply_digital_zoom(frame, zoom):
    h, w = frame.shape[:2]
    new_w = int(w / zoom)
    new_h = int(h / zoom)
    x1 = int((w - new_w) / 2)
    y1 = int((h - new_h) / 2)
    x2 = x1 + new_w
    y2 = y1 + new_h
    cropped = frame[y1:y2, x1:x2]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

def get_frame_duration():
    return 1 / TARGET_FPS

def get_frame_duration_preview():
    return 1 / PREVIEW_FPS

def camera_reader(width, height, fps):
    global picam2, cap, latest_frame, running, frame_lock
    
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (width, height)}
    )
    picam2.configure(config)
    picam2.start()

    running = True
    while running:
        frame = picam2.capture_array()
        frame = frame.astype(np.uint8)
        
        with frame_lock:
            latest_frame = frame
    picam2.close()

def start_camera_reader(width, height, fps):
    global camera_thread, running
    
    # Si ya está corriendo, detenemos la captura
    if running:
        running = False
        camera_thread.join()  # Esperamos que termine
    
    # Arrancamos un nuevo hilo con la configuración nueva
    camera_thread = threading.Thread(target=camera_reader, args=(width, height, fps), daemon=True)
    camera_thread.start()

def postprocess_frame(frame):
    return frame

def encode_jpeg(frame, quality=JPEG_QUALITY):
    try:
        # Primero aplicamos postprocesado
        frame = postprocess_frame(frame)
        return turbo_jpeg.encode(frame, quality=quality)
    except Exception as e:
        raise RuntimeError(f"Error al codificar imagen JPEG: {e}")

def video_stream_thread():
    video_thread_running.set()
    global latest_frame
    print("📡 Hilo iniciado de video.")
    while video_thread_running.is_set():
        start = time.perf_counter()

        with frame_lock:
            if latest_frame is None:
                time.sleep(0.001)
                continue
            frame_full = latest_frame
            h, w = frame_full.shape[:2]

        # Resize si es necesario
        if (w, h) != (WIDTH, HEIGHT):
            frame_full = cv2.resize(frame_full, (WIDTH, HEIGHT))

        # Zoom si aplica
        if zoom_factor != 1:
            zf = zoom_factor
            frame_full = apply_digital_zoom(frame_full, zf)

        # Poner en cola (descartando si está llena para no atrasarse)
        try:
            frame_queue.put_nowait(frame_full)
        except queue.Full:
            pass  # descarta frame viejo

        # Mantener FPS objetivo
        elapsed = time.perf_counter() - start
        sleep_time = get_frame_duration() - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    print("🛑 Hilo de captura detenido.")

def jpeg_encode_and_send_thread():
    while video_thread_running.is_set():
        try:
            frame_full = frame_queue.get_nowait()
        except queue.Empty:
            time.sleep(0.001)
            continue

        # Codificar JPEG
        frame_bytes = encode_jpeg(frame_full, JPEG_QUALITY)

        # Enviar
        #socketio.start_background_task(socketio.emit, 'video_frame', frame_bytes)
        socketio.emit('video_frame', frame_bytes)

        frame_queue.task_done()

    print("🛑 Hilo de compresión/envío detenido.")

def video_vista_stream_thread():
    video_vista_thread_running.set()
    global latest_frame
    print("📡 Hilo iniciado de video vista.")
    while video_vista_thread_running.is_set():
        start = time.perf_counter()

        with frame_lock:
            if latest_frame is None:
                time.sleep(0.001)
                continue
            frame_full = latest_frame
            h, w = frame_full.shape[:2]

        # Resize si es necesario
        if (w, h) != (PREVIEW_WIDTH, PREVIEW_HEIGHT):
            frame_full = cv2.resize(frame_full, (PREVIEW_WIDTH, PREVIEW_HEIGHT))

        # Zoom si aplica
        if zoom_factor != 1:
            zf = zoom_factor
            frame_full = apply_digital_zoom(frame_full, zf)

        # Poner en cola (descartando si está llena para no atrasarse)
        try:
            frame_queue_vista.put_nowait(frame_full)
        except queue.Full:
            pass  # descarta frame viejo

        # Mantener FPS objetivo
        elapsed = time.perf_counter() - start
        sleep_time = get_frame_duration_preview() - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    print("🛑 Hilo de captura detenido vista.")

def jpeg_encode_and_send_thread_vista():
    while video_vista_thread_running.is_set():
        try:
            frame_full = frame_queue_vista.get_nowait()
        except queue.Empty:
            time.sleep(0.001)
            continue

        # Codificar JPEG
        frame_bytes = encode_jpeg(frame_full, PREVIEW_JPEG_QUALITY)

        # Enviar
        #socketio.start_background_task(socketio.emit, 'video_preview', frame_bytes)
        socketio.emit('video_preview', frame_bytes)

        frame_queue_vista.task_done()

    print("🛑 Hilo de compresión/envío detenido vista.")

def move_focus(direction):
    global focus_running
    focus_running = True

    if direction == "in":
        dir_pin.on()
    else:
        dir_pin.off()  

    delay = 0.009  # más lento al inicio
    min_delay = 0.005  # velocidad máxima
    accel_steps = 100   # cuántos pasos tarda en llegar a velocidad máxima

    step_count = 0
    while focus_running:
        step_pin.on()
        time.sleep(delay)
        step_pin.off()
        time.sleep(delay)

        if step_count < accel_steps and delay > min_delay:
            delay -= (0.005 - min_delay) / accel_steps  # acelerar
        step_count += 1

def stop_focus():
    global focus_running
    focus_running = False

@app.route('/zoom', methods=['POST'])
def zoom():
    global zoom_factor, focus_thread, zooming_in, zooming_out
    direction = request.form.get('direction')
    with zoom_lock:
        if direction == 'in' and zoom_factor < 4:
            zooming_in = True
            zooming_out = False
            threading.Thread(target=zoom_in_loop, daemon=True).start()
        elif direction == 'out' and zoom_factor > 1.0:
            zooming_in = False
            zooming_out = True
            threading.Thread(target=zoom_out_loop, daemon=True).start()
        elif direction == 'stop':
            zooming_in = False
            zooming_out = False
        elif direction == 'inCamera':
            motorZoom.forward()
            print(f"🔭 zoomCamera IN")
        elif direction == 'outCamera':
            motorZoom.backward()
            print(f"🔭 zoomCamera OUT")
        elif direction == 'stopCamera':
            motorZoom.stop()
            print("🔭 motor zoom detenido")
        elif direction == 'inFocus':
            print("🔍 Focus IN")
            if not focus_thread or not focus_thread.is_alive():
                focus_thread = threading.Thread(target=move_focus, args=("in",))
                focus_thread.start()
        elif direction == 'outFocus':
            print("🔍 Focus OUT")
            if not focus_thread or not focus_thread.is_alive():
                focus_thread = threading.Thread(target=move_focus, args=("out",))
                focus_thread.start()
        elif direction == 'stopFocus':
            print("🔍 Focus STOP")
            stop_focus()
    return ('', 204)  # Sin respuesta visual

@app.route('/')
def index():
    return render_template_string(HTML_INICIO)

@app.route('/preview')
def preview():
    return render_template_string(HTML_PW)
    
@app.route('/original')
def original():
    return render_template_string(HTML_OR)

# Simular pulsación desde el navegador
@app.route('/simulate/<btn>')
def simulate_button(btn):
    pin = BUTTON_PINS.get(btn)
    if pin:
        GPIO.simulate_press(pin)
        time.sleep(0.2)
        GPIO.simulate_release(pin)
        return f"Simulaste un click en {btn} (pin {pin})"
    return "Botón no válido", 404

### Funciones de reinicio de videos
def restart_video_thread():
    global video_thread, jpeg_thread

    if video_thread and video_thread.is_alive():
        print("🔁 Deteniendo hilo de captura...")
    if jpeg_thread and jpeg_thread.is_alive():
        print("🔁 Deteniendo hilo de compresión/envío...")

    # Apagar ambos
    video_thread_running.clear()

    # Esperar a que terminen
    if video_thread and video_thread.is_alive():
        video_thread.join()
    if jpeg_thread and jpeg_thread.is_alive():
        jpeg_thread.join()

    time.sleep(1)

    # Reiniciar bandera y crear hilos
    print("▶️ Iniciando nuevos hilos de video...")
    video_thread_running.set()

    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    jpeg_thread = threading.Thread(target=jpeg_encode_and_send_thread, daemon=True)

    video_thread.start()
    jpeg_thread.start()

def restart_video_vista_thread():
    global video_vista_thread, jpeg_thread_vista

    if video_vista_thread and video_vista_thread.is_alive():
        print("🔁 Deteniendo hilo de captura vista...")
    if jpeg_thread_vista and jpeg_thread_vista.is_alive():
        print("🔁 Deteniendo hilo de compresión/envío vista...")

    # Apagar ambos
    video_vista_thread_running.clear()

    # Esperar a que terminen
    if video_vista_thread and video_vista_thread.is_alive():
        video_vista_thread.join()
    if jpeg_thread_vista and jpeg_thread_vista.is_alive():
        jpeg_thread_vista.join()

    time.sleep(1)

    # Reiniciar bandera y crear hilos
    print("▶️ Iniciando nuevos hilos de video vista...")
    video_vista_thread_running.set()

    video_vista_thread = threading.Thread(target=video_vista_stream_thread, daemon=True)
    jpeg_thread_vista = threading.Thread(target=jpeg_encode_and_send_thread_vista, daemon=True)

    video_vista_thread.start()
    jpeg_thread_vista.start()

### Funciones de GPIO
def start_blink():
    global blinking
    if not blinking:
        blinking = True
        threading.Thread(target=blink_led).start()
        return "LED empezó a parpadear."
    return "Ya está parpadeando."

def blink_led():
    while blinking:
        led.on()
        time.sleep(0.5)  # Encendido 1 segundo
        led.off()
        time.sleep(10)  # Apagado 10 segundo

def zoom_in_loop():
    global zoom_factor
    while zooming_in:
        with zoom_lock:
            if zoom_factor < 4:
                zoom_factor += zoom_var
        time.sleep(0.05)

def zoom_out_loop():
    global zoom_factor
    while zooming_out:
        with zoom_lock:
            if zoom_factor > 1.0:
                zoom_factor -= zoom_var
        time.sleep(0.05)

def zoomCamera_in_loop():
    global zoomCamera
    while zoomCamera_in:
        motorZoom.forward()
        print(f"🔭 zoomCamera IN")
        time.sleep(0.05)
        motorZoom.stop()

def zoomCamera_out_loop():
    global zoomCamera
    while zoomCamera_out:
        motorZoom.backward()
        print(f"🔭 zoomCamera OUT")
        time.sleep(0.05)
        motorZoom.stop()

# Definimos los handlers para press y release
def on_press(name):
    global zooming_in, zooming_out, zoomCamera_in, zoomCamera_out, focus_thread
    print(f"🔘 Se presionó {name}")
    
    if name == 'btn1' or name == 'btn4':
        zooming_in = True
        threading.Thread(target=zoom_in_loop, daemon=True).start()
    elif name == 'btn2' or name == 'btn3':
        zooming_out = True
        threading.Thread(target=zoom_out_loop, daemon=True).start()
    #elif name == 'btn3':
    #    #zoomCamera_in = True
    #    #threading.Thread(target=zoomCamera_in_loop, daemon=True).start()
    #elif name == 'btn4':
    #    zoomCamera_out = True
    #    threading.Thread(target=zoomCamera_out_loop, daemon=True).start()
    #elif name == 'btn5':
    #    print("🔍 Focus IN")
    #    if not focus_thread or not focus_thread.is_alive():
    #        focus_thread = threading.Thread(target=move_focus, args=("in",))
    #        focus_thread.start()
    #elif name == 'btn6':
    #    print("🔍 Focus OUT")
    #    if not focus_thread or not focus_thread.is_alive():
    #        focus_thread = threading.Thread(target=move_focus, args=("out",))
    #        focus_thread.start()

def on_release(name):
    global zooming_in, zooming_out, zoomCamera_in, zoomCamera_out, focus_in, focus_out
    print(f"🔼 Se soltó {name}")
    
    if name == 'btn1' or name == 'btn4':
        zooming_in = False
    elif name == 'btn2' or name == 'btn3':
        zooming_out = False
    #elif name == 'btn3':
    #    zoomCamera_in = False
    #elif name == 'btn4':
    #    zoomCamera_out = False
    #elif name == 'btn5':
    #    stop_focus()
    #elif name == 'btn6':
    #    stop_focus()

# Asignar handlers
for name, button in buttons.items():
    button.when_pressed = lambda n=name: on_press(n)
    button.when_released = lambda n=name: on_release(n)

def get_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_str = f.read()
        return round(int(temp_str) / 1000.0, 1)  # °C
    except:
        return None

@app.route("/system-info")
def system_info():
    cpu_percent = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    temp = get_temperature()
    disk = int(psutil.disk_usage('/').percent)
    return jsonify({
        "cpu": cpu_percent,
        "ram_used": round(ram.used / 1024 / 1024 / 1024, 1),
        "ram_total": round(ram.total / 1024 / 1024 / 1024, 1),
        "temperature": temp,
        "disk": disk,
        "uptime": start_time
    })

# Endpoint de sistema
@app.route('/status')
def status():
    cpu = int(psutil.cpu_percent())
    ram = int(psutil.virtual_memory().percent)
    temp = 0
    try:
        # Para Pi: lectura de temperatura
        temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) // 1000
    except:
        temp = 50  # fallback
    disk = int(psutil.disk_usage('/').percent)
    return jsonify(cpu=cpu, ram=ram, temp=temp, disk=disk)

@app.route('/restart', methods=['POST'])
def restart():
    subprocess.Popen(['sudo','reboot'])
    return '', 204

# Shutdown Pi
@app.route('/shutdown', methods=['POST'])
def shutdown():
    subprocess.Popen(['sudo','poweroff'])
    return '', 204

@app.route("/wifi", methods=["GET", "POST"])
def wifi():
    if request.method == "POST":
        ssid = request.form['ssid']
        password = request.form['password']
        configurar_wifi(ssid, password)
        return "Configuración guardada. Reinicia la Raspberry Pi."
    return render_template_string(HTML_COF)

def forzar_conexion_wifi():
    print("Forzando conexión WiFi...")

    # Reinicia los servicios de red
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
    subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])
    subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"])
    subprocess.run(["sudo", "systemctl", "restart", "wpa_supplicant"])

    # Espera unos segundos para que levante
    time.sleep(5)

    # Fuerza reconfiguración de wpa_supplicant
    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])
    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reassociate"])

    print("Intentando conectar a la red WiFi...")

def configurar_wifi(ssid, password):
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
        
    wpa_conf = f"""
network={{
    ssid="{ssid}"
    psk="{password}"
}}
"""
    with open("/etc/wpa_supplicant/wpa_supplicant.conf", "w") as f:
        f.write('ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n')
        f.write('update_config=1\n')
        f.write('country=AR\n')  # Ajusta tu país
        f.write(wpa_conf)
    # Reiniciar el servicio de Wi-Fi
    subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
    subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])

    subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"])
    subprocess.run(["sudo", "systemctl", "restart", "wpa_supplicant"])

    subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])
    ComprobeWifi()

def tiene_internet():
    try:
        requests.get("http://google.com", timeout=5)
        return True
    except requests.RequestException:
        return False

def ComprobeWifi():
    forzar_conexion_wifi()
    if not tiene_internet():
        print("No hay Internet, levantando AP...")
        subprocess.run(["sudo", "systemctl", "start", "hostapd"])
        subprocess.run(["sudo", "systemctl", "start", "dnsmasq"])
    else:
        print("Hay Internet, apagando AP...")
        subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
        subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])

if __name__ == '__main__':
    print(start_blink())
    ComprobeWifi()
    start_camera_reader(HEIGHT, WIDTH, TARGET_FPS)
    restart_video_thread()
    restart_video_vista_thread()
    try:
        socketio.run(app, host='0.0.0.0', port=8044, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()