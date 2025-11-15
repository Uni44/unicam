import json
import os
import threading
from flask import jsonify, request
import platform

CONFIG_FILE = "camera_config.json"

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
        "IPDestino": "rtsp://192.168.0.12:8554/cam",
        "IPSDP": "127.0.0.1",
        
        "bitrate": "12M",
        "protocolo": "tcp",
        "preset": "ultrafast",
        
        "protocolo_stream": "RTSP",
        "IPDestinoSRT": "127.0.0.1",
        "puertoDestinoSRT": 0000,
        "extraDataSRT": "?streamid=publish:cam&pkt_size=1316&latency=0"
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

IPDestino = CONFIG["IPSDP"]

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

def aplicar_camara_config(picam2):
    import platform
    so = platform.system()
    try:
        picam2.set_controls({
            "Brightness": CONFIG.get("brightness", 0.5),
            "Contrast": CONFIG.get("contrast", 0.5),
            "Saturation": CONFIG.get("saturation", 0.5),
            "Sharpness": CONFIG.get("sharpness", 0.5),
            "AnalogueGain": CONFIG.get("gain", 1.0)
        })
        picam2.set_controls({
            "NoiseReductionMode": CONFIG.get("noiseRed", 0),
            "HdrMode": CONFIG.get("hdr", 0)
        })
        if CONFIG.get("whitebalance") != "auto":
            picam2.set_controls({
                "AwbEnable": False,
                "ColourTemperature": CONFIG.get("temperature", 4500),
                "AwbMode": int(CONFIG.get("awb-mode", 0))
            })
        else:
            picam2.set_controls({"AwbEnable": True, "AwbMode": 0})
        if CONFIG.get("exposure-mode") == "auto":
            picam2.set_controls({"AeEnable": True})
        else:
            picam2.set_controls({
                "AeEnable": False,
                "ExposureTime": CONFIG.get("exposure", 0.5),
                "AnalogueGain": CONFIG.get("gain", 1.0),
                "AeExposureMode": int(CONFIG.get("ae-exposure-mode", 0)),
                "AeConstraintMode": int(CONFIG.get("ae-constraint-mode", 0)),
                "AeFlickerMode": int(CONFIG.get("ae-flicker-mode", 0))
            })
        gamma = CONFIG.get("gamma", 1.0)
    except Exception:
        pass
    try:
        picam2.set_controls({"Gamma": gamma})
    except Exception:
        pass
    print("✅ Se aplicó la configuración de la cámara Arducam.")

# Obtener configuración actual
def get_camera_config():
    return jsonify(load_config())

# Guardar configuración nueva
def update_camera_config():
    data = request.get_json()
    save_config(data)
    return jsonify({"status": "ok", "message": "Configuración guardada"})

def generar_sdp(ip="192.168.0.18", filename="stream.sdp"):
    sdp_template = f"""v=0
o=- 0 0 IN IP4 {ip}
s=Unicam RTSP Session
t=0 0
a=control:*
m=video 0 RTP/AVP 96
a=rtpmap:96 H264/90000
a=fmtp:96 packetization-mode=1
a=control:trackID=1
"""
    with open(filename, "w") as f:
        f.write(sdp_template)
    print(f"✅ Archivo SDP generado para RTSP: {filename}")