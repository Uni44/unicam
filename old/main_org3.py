from flask import Flask, render_template_string, send_from_directory
from flask import Response, request
from flask_socketio import SocketIO
import cv2
import threading
import time
from flask import jsonify
from htmlTemplates import HTML_PW, HTML_OR, HTML_INICIO, HTML_COF
import json
import os
import queue
from concurrent.futures import ThreadPoolExecutor
import psutil
from gpiozero import LED, Button, Motor, OutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from picamera2 import Picamera2
import numpy as np
import requests
import subprocess
from collections import deque
import socket
import math
import platform
from threading import Thread
from PIL import Image

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

# Controles
blinking = False

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode="threading")

# Config del GPIO
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
        "calidadVista": 50,
        "IPDestino": "192.168.0.18"
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

WIDTH, HEIGHT = 1920, 1080
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

IPDestino = "127.0.0.1"# CONFIG["IPDestino"]

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
        restart_video_thread()

    if reiniciar_vista:
        print("🔁 Se requiere reiniciar la cámara de vista previa.")
    aplicar_camara_config()

def aplicar_camara_config():
    so = platform.system()
    # print(picam2.camera_controls)  # Te muestra todos los controles disponibles

    try:
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
                #"AeMetering": int(CONFIG.get("ae-metering", 0)),
                "AeConstraintMode": int(CONFIG.get("ae-constraint-mode", 0)),
                "AeFlickerMode": int(CONFIG.get("ae-flicker-mode", 0))
            })

        # Gamma (si está soportado por tu driver)
        gamma = CONFIG.get("gamma", 1.0)
    except Exception:
        pass  # Algunas versiones no lo soportan
    try:
        picam2.set_controls({"Gamma": gamma})  # Rango 0.1 – 5.0 aprox.
    except Exception:
        pass  # Algunas versiones no lo soportan

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

def generar_sdp(ip="192.168.0.18", port=8444, payload=96, filename="stream.sdp"):
    sdp_template = f"""v=0
o=- 0 0 IN IP4 {ip}
s=H264 Stream
c=IN IP4 {ip}
t=0 0
m=video {port} RTP/AVP {payload}
a=rtpmap:{payload} H264/90000
a=fmtp:{payload} packetization-mode=1"""
    with open(filename, "w") as f:
        f.write(sdp_template)
    print(f"✅ Archivo SDP generado: {filename}")

rtsp_thread_running = threading.Event()

def zoom_yuv420(frame, width, height, zoom_factor):
    if zoom_factor == 1.0:
        return frame

    # Convertir YUV420 plano a BGR directamente
    yuv = frame.reshape((height*3//2, width))  # solo vista, no copia
    bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)

    # Hacer zoom
    new_w, new_h = int(width * zoom_factor), int(height * zoom_factor)
    bgr_zoom = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Recorte centrado al tamaño original
    start_x = (new_w - width)//2
    start_y = (new_h - height)//2
    bgr_crop = bgr_zoom[start_y:start_y+height, start_x:start_x+width]

    # Convertir de vuelta a YUV420 plano
    yuv_zoom = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2YUV_I420)
    return yuv_zoom.ravel()

def video_stream_thread():
    video_thread_running.set()
    print("📡 Hilo de video stream iniciado.")
    global picam2
    
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"format": "YUV420", "size": (WIDTH, HEIGHT)}
    )
    picam2.configure(config)
    picam2.set_controls({"AfMode": 2, "LensPosition": 0})
    frame_time_us = int(1_000_000 / TARGET_FPS)
    picam2.set_controls({"FrameDurationLimits": (frame_time_us, frame_time_us)})
    picam2.start()
    aplicar_camara_config()

    generar_sdp(IPDestino)

    cmd = [
        'ffmpeg',
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-r', str(TARGET_FPS),
        '-i', '-',
        '-c:v', 'libx264',
        '-preset', 'ultrafast', #superfast
        "-b:v", "10M",
        "-maxrate", "10M",
        "-bufsize", "12M",
        '-tune', 'zerolatency',
        '-x264opts', 'keyint=30:scenecut=0:repeat-headers=1',
        '-f', 'rtp',
        f'rtp://{IPDestino}:8444'
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    rtsp_thread = Thread(target=rtp_to_rtsp_thread)
    rtsp_thread.start()
    
    frame_time = 1 / TARGET_FPS
    try:
        while video_thread_running.is_set():
            try:
                start = time.time()
                frame = picam2.capture_array("main")
                # --- ZOOM ---
                frame = zoom_yuv420(frame, WIDTH, HEIGHT, zoom_factor)
                # --- ENVIAR A RTSP ---
                proc.stdin.write(memoryview(frame))
                # --- MOSTRAR EN MONITOR ---
                #nadaxxdxdxdxdxdxdxdxdxd
            except Exception as e:
                print("❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌")
                print("Error capturando frame:", e)
    except Exception as e:
        print("❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌")
        print("Error en hilo video:", e)
    finally:
        video_thread_running.clear()
        proc.stdin.close()
        proc.wait()
        picam2.close()
        rtsp_thread_running.clear()
        rtsp_thread.join()
        cv2.destroyAllWindows()
        print("🔴 Hilo de video stream parado.")

def rtp_to_rtsp_thread():
    rtsp_thread_running.set()  # activo
    cmd = [
        'ffmpeg',
        '-protocol_whitelist', 'file,udp,rtp',
        '-i', 'stream.sdp',
        '-c', 'copy',
        '-f', 'rtsp',
        'rtsp://localhost:8554/cam'
    ]
    
    with open("ffmpeg_log.txt", "wb") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    
    try:
        while rtsp_thread_running.is_set():
            if proc.poll() is not None:  # FFmpeg terminó
                print("❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌ ❌")
                print("FFmpeg RTSP murió.")
                rtsp_thread_running.clear()
                video_thread_running.clear()
                restart_video_thread()
                break
            time.sleep(0.1)
    finally:
        if proc.poll() is None:
            proc.terminate()
    
@app.route('/zoom', methods=['POST'])
def zoom():
    global zoom_direction
    direction = request.form.get('direction')
    with zoom_lock:
        if direction == 'in':
            zoom_direction = +1
        elif direction == 'out':
            zoom_direction = -1
        elif direction == 'stop':
            zoom_direction = 0
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

### Funciones de reinicio de videos
def restart_video_thread():
    global video_thread, jpeg_thread

    if video_thread and video_thread.is_alive():
        print("🔁 Deteniendo hilo de captura...")
    # Apagar ambos
    video_thread_running.clear()
    # Esperar a que terminen
    if video_thread and video_thread.is_alive():
        video_thread.join()

    time.sleep(1)

    # Reiniciar bandera y crear hilos
    print("▶️ Iniciando nuevos hilos de video...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()

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
        
zoom_lock = threading.Lock()
zoom_direction = 0

def zoom_loop():
    global zoom_factor, zoom_direction
    while True:
        if zoom_direction != 0:
            with zoom_lock:
                zoom_factor = max(1.0, min(4.0, zoom_factor + zoom_direction * zoom_var))
        time.sleep(0.05)

# Arrancamos un único hilo para siempre
threading.Thread(target=zoom_loop, daemon=True).start()

def on_press(name):
    global zoom_direction
    print(f"🔘 Se presionó {name}")

    if name in ('btn1', 'btn4'):
        zoom_direction = +1   # Zoom in
    elif name in ('btn2', 'btn3'):
        zoom_direction = -1   # Zoom out

def on_release(name):
    global zoom_direction
    print(f"🔼 Se soltó {name}")
    zoom_direction = 0

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
@app.route('/hls/<path:filename>')
def hls(filename):
    HLS_FOLDER = "/home/pi/Unicam/hls"
    return send_from_directory(HLS_FOLDER, filename)

def get_cpu_freq():
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq") as f:
            # El valor viene en kHz, lo pasamos a MHz o GHz
            freq_khz = int(f.read().strip())
            return round(freq_khz / 1000, 1)  # MHz
    except:
        return None

@app.route('/status')
def status():
    cpu = int(psutil.cpu_percent())
    ram = int(psutil.virtual_memory().percent)
    temp = 0
    cpu_freq = get_cpu_freq()
    
    try:
        # Para Pi: lectura de temperatura
        temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) // 1000
    except:
        temp = 50  # fallback
    disk = int(psutil.disk_usage('/').percent)
    return jsonify(cpu=cpu, ram=ram, temp=temp, disk=disk, cpu_freq=cpu_freq)

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
    time.sleep(4)
    restart_video_thread()
    try:
        socketio.run(app, host='0.0.0.0', port=8044, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()