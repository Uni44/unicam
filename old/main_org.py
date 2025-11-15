from flask import Flask, render_template_string
from flask import Response, request
from flask_socketio import SocketIO
import cv2
import threading
import time
from flask import jsonify
from html import HTML_PW, HTML_OR
import json
import os
import queue
from concurrent.futures import ThreadPoolExecutor
import psutil
from gpiozero import LED, Button, Motor, OutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

# GPIO PINS
factory = LGPIOFactory()
led = LED(5, pin_factory=factory)
BUTTON_PINS = {
    'btn1': 13,
    'btn2': 18,
    'btn3': 24,
    'btn4': 4,
    'btn5': 26,
    'btn6': 16,
}
motorZoom = Motor(forward=17, backward=27)  # forward = IN1, backward = IN2

# Pines GPIO (ajústalos según tu conexión)
DIR_PIN = 21  # Dirección
STEP_PIN = 20  # Pulsos

# Configuración de pines
dir_pin = OutputDevice(DIR_PIN)
step_pin = OutputDevice(STEP_PIN)

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
        "brightness": 128,
        "contrast": 128,
        "saturation": 128,
        "sharpness": 128,
        "exposure": -5,
        "gamma": 128,
        "gain": 128,
        "temperature": 4000,
        "whitebalance": "auto",
        "exposure-mode": "auto",
        "resolution": "1920x1080",
        "fps": 30,
        "calidad": 100,
        "resolutionVista": "1920x1080",
        "fpsVista": 30,
        "calidadVista": 100
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

frame_queue = queue.Queue(maxsize=2)  # ajusta maxsize si quieres más buffer
frame_queue_vista = queue.Queue(maxsize=2)  # ajusta maxsize si quieres más buffer

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
    aplicar_camara_cofig()
    
import platform

def aplicar_camara_cofig():
    so = platform.system()  # "Linux" o "Windows"

    property_map = {
        "brightness": cv2.CAP_PROP_BRIGHTNESS,
        "contrast": cv2.CAP_PROP_CONTRAST,
        "saturation": cv2.CAP_PROP_SATURATION,
        "gamma": cv2.CAP_PROP_GAMMA,
        "gain": cv2.CAP_PROP_GAIN,
        "whitebalance": cv2.CAP_PROP_WHITE_BALANCE_BLUE_U,
    }

    for key, val in CONFIG.items():
        if key == "exposure-mode":
            if val == "auto":
                if so == "Linux":
                    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                else:
                    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            else:
                if so == "Linux":
                    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
                    cap.set(cv2.CAP_PROP_EXPOSURE, CONFIG["exposure"])  # ej: -6
                else:
                    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
                    cap.set(cv2.CAP_PROP_EXPOSURE, CONFIG["exposure"])  # ej: 200

        elif key == "whitebalance":
            if val == "auto":
                cap.set(cv2.CAP_PROP_AUTO_WB, 1)
            else:
                cap.set(cv2.CAP_PROP_AUTO_WB, 0)
                cap.set(cv2.CAP_PROP_WB_TEMPERATURE, CONFIG["temperature"])
        else:
            prop_id = property_map.get(key)
            if prop_id is not None:
                cap.set(prop_id, val)

    print("Se actualizó la configuración de la cámara.")

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
    global cap, latest_frame, running
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ No se pudo abrir la cámara.")
        running = False
        return
    
    # Configurar el formato a MJPG:
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    
    running = True
    while running:
        ret, frame = cap.read()
        if not ret:
            continue
        with frame_lock:
            latest_frame = frame.copy()
    cap.release()

def start_camera_reader(width, height, fps):
    global camera_thread, running
    
    # Si ya está corriendo, detenemos la captura
    if running:
        running = False
        camera_thread.join()  # Esperamos que termine
    
    # Arrancamos un nuevo hilo con la configuración nueva
    camera_thread = threading.Thread(target=camera_reader, args=(width, height, fps), daemon=True)
    camera_thread.start()

jpeg_executor = ThreadPoolExecutor(max_workers=4)

def encode_jpeg(frame, quality=JPEG_QUALITY):
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded_image = cv2.imencode('.jpg', frame, encode_param)
    if not success:
        raise RuntimeError("Error al codificar imagen JPEG")
    return encoded_image.tobytes()

def video_stream_thread():
    video_thread_running.set()
    global latest_frame
    print("🛑 Hilo iniciado de video.")
    while video_thread_running.is_set():
        start = time.perf_counter()

        with frame_lock:
            if latest_frame is None:
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
            frame_full = frame_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        # Codificar JPEG
        frame_bytes = encode_jpeg(frame_full, JPEG_QUALITY)

        # Enviar
        socketio.start_background_task(socketio.emit, 'video_frame', frame_bytes)

        frame_queue.task_done()

    print("🛑 Hilo de compresión/envío detenido.")

def video_vista_stream_thread():
    video_vista_thread_running.set()
    global latest_frame
    print("🛑 Hilo iniciado de video vista.")
    while video_vista_thread_running.is_set():
        start = time.perf_counter()

        with frame_lock:
            if latest_frame is None:
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
            frame_full = frame_queue_vista.get(timeout=0.5)
        except queue.Empty:
            continue

        # Codificar JPEG
        frame_bytes = encode_jpeg(frame_full, PREVIEW_JPEG_QUALITY)

        # Enviar
        socketio.start_background_task(socketio.emit, 'video_preview', frame_bytes)

        frame_queue_vista.task_done()

    print("🛑 Hilo de compresión/envío detenido vista.")

def move_focus(direction):
    global focus_running
    focus_running = True

    if direction == "in":
        dir_pin.on()
    else:
        dir_pin.off()  

    delay = 0.005  # más lento al inicio
    min_delay = 0.001  # velocidad máxima
    accel_steps = 50   # cuántos pasos tarda en llegar a velocidad máxima

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
    return "Test"

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
    
    if name == 'btn1':
        zooming_in = True
        threading.Thread(target=zoom_in_loop, daemon=True).start()
    elif name == 'btn2':
        zooming_out = True
        threading.Thread(target=zoom_out_loop, daemon=True).start()
    elif name == 'btn3':
        zoomCamera_in = True
        threading.Thread(target=zoomCamera_in_loop, daemon=True).start()
    elif name == 'btn4':
        zoomCamera_out = True
        threading.Thread(target=zoomCamera_out_loop, daemon=True).start()
    elif name == 'btn5':
        print("🔍 Focus IN")
        if not focus_thread or not focus_thread.is_alive():
            focus_thread = threading.Thread(target=move_focus, args=("in",))
            focus_thread.start()
    elif name == 'btn6':
        print("🔍 Focus OUT")
        if not focus_thread or not focus_thread.is_alive():
            focus_thread = threading.Thread(target=move_focus, args=("out",))
            focus_thread.start()

def on_release(name):
    global zooming_in, zooming_out, zoomCamera_in, zoomCamera_out, focus_in, focus_out
    print(f"🔼 Se soltó {name}")
    
    if name == 'btn1':
        zooming_in = False
    elif name == 'btn2':
        zooming_out = False
    elif name == 'btn3':
        zoomCamera_in = False
    elif name == 'btn4':
        zoomCamera_out = False
    elif name == 'btn5':
        stop_focus()
    elif name == 'btn6':
        stop_focus()

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
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    temp = get_temperature()

    return jsonify({
        "cpu": cpu_percent,
        "ram_used": round(ram.used / 1024 / 1024 / 1024, 1),
        "ram_total": round(ram.total / 1024 / 1024 / 1024, 1),
        "temperature": temp
    })

if __name__ == '__main__':
    print(start_blink())
    start_camera_reader(HEIGHT, WIDTH, TARGET_FPS)
    restart_video_thread()
    restart_video_vista_thread()
    try:
        socketio.run(app, host='0.0.0.0', port=8044, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()