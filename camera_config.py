import json
import os
import threading
from flask import jsonify, request
import platform

CONFIG_FILE = "camera_config.json"

def load_config():
    default_config = {
    "Brightness": 0,
    "Contrast": 0.9,
    "Saturation": 1.1,
    "Sharpness": 1,
    "ColourTemperature": 3600,
    "ColourGains": 0,
    "ExposureTime": 112015013,
    "ExposureValue": 0,
    "AnalogueGain": 4.44,
    "AeFlickerPeriod": 500100,
    "LensPosition": 7.5,
    "SyncFrames": 500001,
    "AfWindows": None,
    "FrameDurationLimits": None,
    "ScalerCrop": None,
    "AwbEnable": True,
    "AeEnable": False,
    "AfTrigger": False,
    "StatsOutputEnable": False,
    "CnnEnableInputTensor": False,
    "AwbMode": "0",
    "AeExposureMode": "0",
    "AeConstraintMode": "0",
    "AeMeteringMode": "0",
    "AeFlickerMode": "0",
    "NoiseReductionMode": "4",
    "HdrMode": "0",
    "AfMode": "2",
    "AfRange": "0",
    "AfSpeed": "0",
    "AfMetering": "0",
    "AfPause": "2",
    "SyncMode": "0",
    "ExposureTimeMode": "0",
    "AnalogueGainMode": "0",
    "resolution": "1920x1080",
    "fps": "30",
    "modo": "Stream",
    "bitrate": "16M",
    "preset": "ultrafast",
    "protocolo_stream": "RTSP",
    "IPDestino": "rtsp://192.168.0.12:8554/cam",
    "IPSDP": "0.0.0.0",
    "protocolo": "tcp",
    "IPDestinoSRT": "152.170.252.9",
    "puertoDestinoSRT": "8890",
    "extraDataSRT": "?streamid=publish:cam&mode=caller&transtype=live&latency=600&peerlatency=300&pkt_size=1316"
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
IPDestino = CONFIG["IPSDP"]

def save_config(data):
    global CONFIG, WIDTH, HEIGHT, TARGET_FPS, PREVIEW_WIDTH

    # Capturar valores anteriores
    prev_width = WIDTH
    prev_height = HEIGHT
    prev_fps = TARGET_FPS

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
        
    #reiniciar_original = (WIDTH != prev_width or HEIGHT != prev_height or TARGET_FPS != prev_fps)

    #if reiniciar_original:
        #print("🔁 Se requiere reiniciar la cámara original.")
        #restart_video_thread()

# Guarda la última configuración aplicada
ULTIMA_CONFIG = {}

def aplicar_camara_config(picam2, todo=False):
    global ULTIMA_CONFIG

    if todo:
        ULTIMA_CONFIG = {}

    nueva = load_config()

    # Normalizar tipos
    config_json = nueva.copy()
    for k,v in list(config_json.items()):
        if isinstance(v,str) and v.isdigit():
            config_json[k] = int(v)

    # Convertir ColourGains simple → [R, B]
    if isinstance(config_json.get("ColourGains"), (int,float)):
        config_json["ColourGains"] = [config_json["ColourGains"]] * 2

    # Controles válidos
    control_list = [
        "Brightness", "Contrast", "Saturation", "Sharpness",
        "ColourTemperature", "ColourGains",
        "ExposureTime", "ExposureValue", "AnalogueGain",
        "AeFlickerPeriod", "LensPosition", "SyncFrames",
        "AfWindows", "FrameDurationLimits", "ScalerCrop",
        "AwbEnable", "AeEnable", "AfTrigger", "StatsOutputEnable",
        "CnnEnableInputTensor", "AwbMode", "AeExposureMode",
        "AeConstraintMode", "AeMeteringMode", "AeFlickerMode",
        "NoiseReductionMode", "HdrMode", "AfMode", "AfRange",
        "AfSpeed", "AfMetering", "AfPause", "SyncMode",
        "ExposureTimeMode", "AnalogueGainMode"
    ]

    # ----------------------------
    # IGNORAR valores conflictivos
    # ----------------------------
    # White Balance
    if config_json.get("AwbEnable", False):
        # Auto WB: no forzar ColourTemperature ni ColourGains
        config_json.pop("ColourTemperature", None)
        config_json.pop("ColourGains", None)
    else:
        # Manual WB: asegurarse de que AwbEnable esté desactivado
        config_json["AwbEnable"] = False

    # Auto Exposure
    if config_json.get("AeEnable", False):
        # Auto AE: no forzar ExposureTime ni AnalogueGain
        config_json.pop("ExposureTime", None)
        config_json.pop("AnalogueGain", None)
    else:
        # Manual AE: asegurar que AE esté off para poder aplicar valores
        config_json["AeEnable"] = False

    # Auto Focus
    af_mode = config_json.get("AfMode", 0)
    if af_mode in (1, 2):  # AUTO / CONTINUOUS
        config_json.pop("LensPosition", None)
    else:
        # Manual AF: asegurar modo manual para aplicar LensPosition
        config_json["AfMode"] = 0  # manual

    # ----------------------------
    # Detectar cambios reales
    # ----------------------------
    cambios = {}

    for key in control_list:
        if key not in config_json:
            continue

        nuevo = config_json[key]
        anterior = ULTIMA_CONFIG.get(key)

        if nuevo != anterior:
            cambios[key] = nuevo

    if not cambios:
        print("✔ Sin cambios.")
        return

    # Aplicar solo los que cambiaron
    picam2.set_controls(cambios)

    # Actualizar estado
    for k,v in cambios.items():
        ULTIMA_CONFIG[k] = v

    print("✔ Aplicado:", cambios)

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