import json
import os
import threading
import time
from flask import jsonify, request
import platform
import sounddevice as sd
import numpy as np
import alsaaudio
import subprocess
import re
import psutil

from digital_zoom import build_scaler_crop, calculate_effective_digital_zoom_factor


def ensure_xdg_runtime_dir():
    """Ensure XDG_RUNTIME_DIR is set to a valid directory so SDL/ffmpeg can open displays.
    This is safe to call on systems without getuid (Windows) — it falls back to /tmp.
    """
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


# Ensure XDG runtime dir early (import-time) so subprocesses inherit it
ensure_xdg_runtime_dir()
    
CAMERA_RUNNING = False
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PROJECT_DIR, "camera_config.json")
MIC_MUTE = False

MIC_DEVICE = None   # None → sounddevice elige el default (tu USB)
SAMPLE_RATE = 48000
FRAME_SIZE = 1024

def get_audio_level():
    """Devuelve el nivel del micrófono en una escala de 0 a 100."""
    try:
        audio = sd.rec(
            frames=FRAME_SIZE,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            device=MIC_DEVICE
        )
        sd.wait()

        rms = np.sqrt(np.mean(audio ** 2))
        db = 20 * np.log10(rms + 1e-8)   # evitar log(0)

        # Convertir dB a nivel 0-100
        # -60 dB = silencio → 0
        # 0 dB = volumen máximo → 100
        level = np.interp(db, [-60, 0], [0, 100])
        level = np.clip(level, 0, 100)

        return int(level)

    except Exception as e:
        print("❌ Error al medir audio:", e)
        return 0

def normalize_camera_mode(value):
    """Map UI labels and legacy values to the internal mode names used by the backend."""
    if not value:
        return None
    normalized = str(value).strip()
    aliases = {
        "Photo": "Foto",
        "Foto": "Foto",
        "Picture": "Foto",
        "Stream": "Stream",
        "Record": "Grabar",
        "Grabar": "Grabar",
        "Recording": "Grabar",
    }
    return aliases.get(normalized, normalized)


def parse_resolution(value):
    """Parsea valores como '1920x1080' y devuelve (width, height)."""
    if not value:
        return None
    try:
        parts = str(value).strip().lower().split("x")
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def parse_fps(value, default=30):
    """Devuelve un FPS válido entre 5 y 90 a partir de valores numéricos o cadenas."""
    try:
        fps = int(float(str(value).strip()))
    except Exception:
        return default
    if fps < 5:
        return 5
    if fps > 90:
        return 90
    return fps


def normalize_camera_config(data):
    if data is None:
        return data
    data = dict(data)
    data["resolution"] = str(data.get("resolution", "1920x1080")).strip()
    data["fps"] = parse_fps(data.get("fps", 30))
    camera_number = str(data.get("camera_number", "1") or "1").strip()
    data["camera_number"] = camera_number if camera_number else "1"
    return data


def load_config():
    global CONFIG_FILE
    config_path = os.path.abspath(CONFIG_FILE)
    if not os.path.isabs(CONFIG_FILE):
        config_path = os.path.join(PROJECT_DIR, CONFIG_FILE)
    CONFIG_FILE = config_path

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
        "encoder_warning_enabled": True,
        "encoder_warning_resolution": "",
        "encoder_warning_fps": "",
        "encoder_warning_preset": "",
        "protocolo_stream": "RTSP",
        "IPDestino": "rtsp://192.168.0.12:8554/cam",
        "IPSDP": "0.0.0.0",
        "protocolo": "tcp",
        "IPDestinoSRT": "152.170.252.9",
        "puertoDestinoSRT": "8890",
        "extraDataSRT": "?streamid=publish:cam&mode=caller&transtype=live&latency=600&peerlatency=300&pkt_size=1316",
        "mic": "",
        "audio_monitor_enabled": False,
        "audio_monitor_output": "default",
        "hdmi": "Full",
        "hdmi_overlay": True,
        "hdmi_fallback_enabled": True,
        "hdmi_fallback_image": "",
        "AutoReconnect": True,
        "storage_mode": "default",
        "storage_path": "",
        "storage_usb_path": "",
        "camera_number": "1"
    }

    if not os.path.exists(CONFIG_FILE):
        return normalize_camera_config(default_config)
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    for key, val in default_config.items():
        data.setdefault(key, val)
    return normalize_camera_config(data)

CONFIG = load_config()

WIDTH, HEIGHT = 1920, 1080
picam2 = None


def normalize_audio_monitor_output(value):
    """Normaliza el dispositivo de salida ALSA para el monitor sin forzar un hardware fijo."""
    monitor_output = str(value or "").strip()
    if not monitor_output or monitor_output.lower() == "default":
        return "default"
    if monitor_output.startswith("hw:"):
        return "plughw:" + monitor_output[3:]
    return monitor_output


def build_audio_monitor_plan(cfg=None):
    source_cfg = cfg if cfg is not None else CONFIG
    mic_path = str(source_cfg.get("mic") or "").strip()
    enabled = bool(source_cfg.get("audio_monitor_enabled")) and bool(mic_path) and not mic_path.startswith("!")
    if not enabled:
        return {"enabled": False, "input_device": "", "monitor_source": "", "monitor_output": ""}

    monitor_source = "mic_mon"  # dsnoop compartido, definido en ~/.asoundrc
    monitor_output = normalize_audio_monitor_output(source_cfg.get("audio_monitor_output"))

    return {
        "enabled": True,
        "input_device": mic_path,
        "monitor_source": monitor_source,
        "monitor_output": monitor_output,
    }


def is_alsa_device_available(device_name):
    """Comprueba si un dispositivo ALSA parece existir antes de lanzarlo en ffmpeg."""
    if not device_name:
        return False
    try:
        if device_name.startswith("dsnoop:"):
            device_name = device_name[len("dsnoop:"):]
        result = subprocess.run(
            ["ffprobe", "-f", "alsa", "-i", device_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def resolve_audio_monitor_plan(cfg=None):
    """Devuelve un plan seguro para el monitor de audio usando valores válidos."""
    plan = build_audio_monitor_plan(cfg)
    if not plan["enabled"]:
        return plan

    if is_alsa_device_available(plan["monitor_source"]):
        return plan

    fallback = {
        "enabled": True,
        "input_device": "",
        "monitor_source": "",
        "monitor_output": plan.get("monitor_output") or "default",
    }
    return fallback


def is_usb_device(device):
    """Detecta si un dispositivo es un disco USB real y no un pseudo-dispositivo del sistema."""
    if not device:
        return False
    device = str(device).lower()
    return device.startswith("/dev/sd")


def list_storage_targets():
    """Devuelve solo rutas montadas en discos USB reales."""
    candidates = []
    seen = set()

    ignored_mounts = {
        "/", "/boot", "/boot/firmware", "/dev", "/dev/shm", "/proc", "/proc/sys", "/sys",
        "/run", "/tmp", "/var", "/var/lib", "/var/run", "/snap", "/root"
    }
    ignored_fstypes = {"tmpfs", "overlay", "proc", "sysfs", "debugfs", "devtmpfs", "squashfs", "devpts"}

    try:
        for part in psutil.disk_partitions(all=False):
            mountpoint = part.mountpoint
            device = part.device
            if not mountpoint or not device or mountpoint in seen or mountpoint in ignored_mounts:
                continue
            if not os.path.exists(mountpoint):
                continue
            if part.fstype in ignored_fstypes:
                continue
            if not is_usb_device(device):
                continue
            lower = mountpoint.lower()
            if any(token in lower for token in ["/sys", "/dev", "/proc", "/run", "/var", "/tmp", "/boot"]):
                continue
            candidates.append(mountpoint)
            seen.add(mountpoint)
    except Exception:
        pass

    return candidates


def is_safe_storage_path(path):
    """Comprueba si una ruta es usable para guardar archivos de forma segura."""
    try:
        candidate = os.path.expanduser(str(path or "").strip())
    except Exception:
        return False

    if not candidate:
        return False

    forbidden_prefixes = ("/dev", "/proc", "/sys", "/run", "/var", "/tmp")
    if candidate.startswith(forbidden_prefixes):
        return False

    try:
        if not os.path.exists(candidate):
            os.makedirs(candidate, exist_ok=True)
        if not os.path.isdir(candidate):
            return False
        test_file = os.path.join(candidate, ".unicam_write_test")
        with open(test_file, "w") as fh:
            fh.write("ok")
        os.remove(test_file)
        return True
    except Exception:
        return False


def detect_storage_path(cfg=None):
    """Intenta encontrar una ruta de almacenamiento externa disponible en una USB real."""
    if cfg is None:
        cfg = CONFIG or load_config()

    preferred = str(cfg.get("storage_usb_path", "") or "").strip()
    if preferred and is_safe_storage_path(preferred):
        return preferred

    fallback_path = str(cfg.get("storage_path", "") or "").strip()
    if fallback_path and is_safe_storage_path(fallback_path):
        return fallback_path

    for candidate in list_storage_targets():
        if is_safe_storage_path(candidate):
            return candidate

    return os.getcwd()


def get_storage_base_path(cfg=None):
    """Devuelve la ruta base de almacenamiento según el modo configurado."""
    if cfg is None:
        cfg = CONFIG or load_config()

    mode = str(cfg.get("storage_mode", "default") or "default").strip().lower()
    if mode == "usb":
        for key in ("storage_usb_path", "storage_path"):
            value = str(cfg.get(key, "") or "").strip()
            if value:
                return value
        return detect_storage_path(cfg)
    if mode == "custom":
        return str(cfg.get("storage_path", "") or "").strip() or PROJECT_DIR
    return PROJECT_DIR


def resolve_storage_dir(kind, cfg=None):
    """Devuelve la carpeta destino para fotos o vídeos según la configuración."""
    if cfg is None:
        cfg = CONFIG or load_config()

    mode = str(cfg.get("storage_mode", "default") or "default").strip().lower()
    base_path = ""

    if mode == "usb":
        base_path = get_storage_base_path(cfg)
        target_dir = os.path.abspath(base_path)
    elif mode == "custom":
        base_path = str(cfg.get("storage_path", "") or "").strip() or PROJECT_DIR
        target_dir = os.path.abspath(os.path.join(base_path, kind))
    else:
        base_path = PROJECT_DIR
        target_dir = os.path.abspath(os.path.join(base_path, kind))

    if not base_path:
        base_path = PROJECT_DIR
        target_dir = os.path.abspath(os.path.join(base_path, kind))

    base_path = os.path.expanduser(base_path)
    if not is_safe_storage_path(base_path):
        base_path = PROJECT_DIR
        target_dir = os.path.abspath(os.path.join(base_path, kind))

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        fallback_dir = os.path.abspath(os.path.join(PROJECT_DIR, kind))
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir
    return target_dir


def mic_mute_mixer(enable: bool):
    try:
        print("Mixer muteando.")
        mixer.setrec(0 if enable else 1)
        return True
    except Exception as e:
        print("Error al mutear:", e)
        return False


def changeRunningCamera(estado):
    global CAMERA_RUNNING
    CAMERA_RUNNING = estado


def getRunningCamera():
    global CAMERA_RUNNING
    return CAMERA_RUNNING


def changeMute(estado):
    global MIC_MUTE
    MIC_MUTE = estado
    print("Muteando mic.")
    if CONFIG.get("mic"):
        mic_mute_mixer(MIC_MUTE)


def getMute():
    global MIC_MUTE
    return MIC_MUTE


# 🔢 Actualizar resolución
res = CONFIG["resolution"]
if isinstance(res, str) and "x" in res:
    try:
        WIDTH, HEIGHT = map(int, res.lower().split("x"))
        print(f"✅ Resolución actualizada a {WIDTH}x{HEIGHT}")
    except ValueError:
        print(f"⚠️ Error al parsear resolución: {res}")
        WIDTH, HEIGHT = 1920, 1080
else:
    print(f"⚠️ Resolución inválida: {res}")
    WIDTH, HEIGHT = 1920, 1080

TARGET_FPS = parse_fps(CONFIG.get("fps", 30))
IPDestino = CONFIG.get("IPSDP")


def save_config(data):
    global CONFIG, WIDTH, HEIGHT, TARGET_FPS

    data = dict(data or {})
    mode = str(data.get("storage_mode", "default") or "default").strip().lower()
    if mode == "usb":
        usb_path = str(data.get("storage_usb_path", "") or "").strip()
        custom_path = str(data.get("storage_path", "") or "").strip()
        if usb_path and not custom_path:
            data["storage_path"] = usb_path
        elif custom_path and not usb_path:
            data["storage_usb_path"] = custom_path
    elif mode == "custom" and not data.get("storage_path") and data.get("storage_usb_path"):
        data["storage_path"] = data.get("storage_usb_path")

    prev_width = WIDTH
    prev_height = HEIGHT
    prev_fps = TARGET_FPS

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ Error guardando configuración: {e}")
        return

    CONFIG = normalize_camera_config(data)

    res = CONFIG.get("resolution", "1920x1080")
    if isinstance(res, str) and "x" in res:
        try:
            WIDTH, HEIGHT = map(int, res.lower().split("x"))
            print(f"✅ Resolución actualizada a {WIDTH}x{HEIGHT}")
        except ValueError:
            print(f"⚠️ Error al parsear resolución: {res}")
            WIDTH, HEIGHT = 1920, 1080
    else:
        print(f"⚠️ Resolución inválida: {res}")
        WIDTH, HEIGHT = 1920, 1080

    TARGET_FPS = CONFIG["fps"]
    print(f"✅ FPS objetivo: {TARGET_FPS}")

# Guarda la última configuración aplicada
ULTIMA_CONFIG = {}


def _get_effective_zoom_factor():
    """Devuelve el factor de zoom digital a aplicar por encima del zoom físico máximo."""
    try:
        import gpio_control
        optics_state = getattr(gpio_control, "get_optics_state", lambda: {})()
        zoom_value = optics_state.get("zoom", 1.0)
        return calculate_effective_digital_zoom_factor(zoom_value)
    except Exception:
        return 1.0


def apply_digital_zoom_to_camera(picam2_obj=None):
    """Aplica un crop digital en la cámara activa si el zoom supera el rango físico."""
    if picam2_obj is None:
        return False
    try:
        full_res = None
        camera_props = getattr(picam2_obj, "camera_properties", None)
        if isinstance(camera_props, dict):
            full_res = camera_props.get("PixelArraySize")
        if not full_res:
            full_res = getattr(picam2_obj, "sensor_resolution", None)
        if not full_res:
            return False

        zoom_factor = _get_effective_zoom_factor()
        if zoom_factor <= 1.0:
            crop = (0, 0, int(full_res[0]), int(full_res[1]))
        else:
            crop = build_scaler_crop(full_res, zoom_factor, center_x=0.5, center_y=0.5)
        picam2_obj.set_controls({"ScalerCrop": crop})
        return True
    except Exception:
        return False


def apply_digital_zoom_to_active_cameras():
    """Aplica el zoom digital a las cámaras activas de Stream/Foto/Grabar."""
    for module_name in ("video_stream", "foto_capture", "video_rec"):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        cam = getattr(module, "picam2", None)
        if cam is not None:
            apply_digital_zoom_to_camera(cam)
    return True


def _apply_auto_mode_rearm_if_needed(picam2_obj, cambios, config_json, delay_seconds=0.2):
    """Rearma los modos automáticos al arrancar para que AWB/AE queden verdaderamente activos.

    En algunas arrancadas Picamera2 puede dejar los controles automáticos en un estado
    intermedio hasta que el pipeline recibe un cambio extra. Este rearm fuerza un ciclo
    desactivar/activar sin modificar el resto de la configuración.
    """
    if picam2_obj is None:
        return

    try:
        if config_json.get("AwbEnable", False):
            picam2_obj.set_controls({"AwbEnable": False, "AwbMode": 0})
            if delay_seconds:
                time.sleep(delay_seconds)
            picam2_obj.set_controls({"AwbEnable": True, "AwbMode": 0})
        if config_json.get("AeEnable", False):
            picam2_obj.set_controls({"AeEnable": False})
            if delay_seconds:
                time.sleep(delay_seconds)
            picam2_obj.set_controls({"AeEnable": True})
    except Exception:
        pass


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
        apply_digital_zoom_to_camera(picam2)
        print("✔ Sin cambios.")
        return

    # Aplicar solo los que cambiaron
    picam2.set_controls(cambios)
    apply_digital_zoom_to_camera(picam2)

    # Rearmar modos automáticos al arrancar para que AWB/AE entren correctamente en auto.
    if todo:
        _apply_auto_mode_rearm_if_needed(picam2, cambios, config_json)

    # Actualizar estado
    for k,v in cambios.items():
        ULTIMA_CONFIG[k] = v

    print("✔ Aplicado:", cambios)

# Obtener configuración actual
def get_camera_config():
    return jsonify(load_config())


def _parse_dsnoop_target(pcm_name='dsnoop_mic', asoundrc_path=None):
    """Lee ~/.asoundrc y devuelve (card, device) del hardware que envuelve
    el PCM `pcm_name` (ej. dsnoop_mic -> hw:2,0), o None si no lo encuentra.

    Soporta las dos formas típicas de declarar la tarjeta en un bloque
    pcm.dsnoop_mic { ... }:
        ipc_key ...
        slave.pcm "hw:2,0"
    o bien:
        slave {
            pcm "hw:2,0"
        }
    """
    path = asoundrc_path or os.path.expanduser('~/.asoundrc')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    # Aislar el bloque pcm.<pcm_name> { ... } contando llaves, porque el
    # archivo puede tener varios bloques pcm.* y no queremos mezclarlos.
    marker = f'pcm.{pcm_name}'
    start = content.find(marker)
    if start == -1:
        return None
    brace_start = content.find('{', start)
    if brace_start == -1:
        return None
    depth = 0
    end = None
    for i in range(brace_start, len(content)):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        return None
    block = content[brace_start:end]

    # Buscar "hw:CARD,DEVICE" en cualquier forma dentro del bloque
    # (slave.pcm "hw:2,0"  /  pcm "hw:2,0"  /  slave.pcm hw:2,0 sin comillas)
    m = re.search(r'hw:\s*(\d+)\s*,\s*(\d+)', block)
    if m:
        return m.group(1), m.group(2)

    # Variante donde se declara "card 2" / "device 0" por separado en vez
    # de un string "hw:2,0"
    card_m = re.search(r'\bcard\s+(\d+)', block)
    device_m = re.search(r'\bdevice\s+(\d+)', block)
    if card_m:
        device_num = device_m.group(1) if device_m else '0'
        return card_m.group(1), device_num

    return None


def list_mics(shared_pcm_name='dsnoop_mic'):
    """Devuelve una lista de dispositivos de captura ALSA en formato usable
    por FFmpeg/sounddevice.

    Si el dispositivo detectado coincide con la tarjeta/device que envuelve
    `shared_pcm_name` (definido en ~/.asoundrc, ej. dsnoop_mic -> hw:2,0),
    devuelve ese nombre compartido en vez de 'plughw:card,device' — así
    cualquier proceso (HUD, intercom, streaming) puede abrir el mic al mismo
    tiempo sin pelearse por el device físico.
    """
    devices = []
    dsnoop_target = _parse_dsnoop_target(shared_pcm_name)

    try:
        out = subprocess.check_output(['arecord', '-l'], stderr=subprocess.STDOUT).decode(errors='ignore')
    except Exception:
        out = ''

    def _make_entry(card, device, card_label, dev_label):
        if dsnoop_target is not None and (card, device) == dsnoop_target:
            return {
                'value': shared_pcm_name,
                'label': f"{card_label} - {dev_label} (compartido vía {shared_pcm_name})",
            }
        return {
            'value': f'plughw:{card},{device}',
            'label': f"{card_label} - {dev_label} (card {card}, device {device})",
        }

    # Parsear líneas tipo: card 1: Device [USB PnP Audio Device], device 0: USB Audio [USB Audio]
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'card\s+(\d+):\s*(.*?)\s*\[(.*?)\],\s*device\s+(\d+):\s*(.*?)\s*\[(.*?)\]', line)
        if m:
            card = m.group(1)
            card_label = m.group(3)
            device = m.group(4)
            dev_label = m.group(6)
            devices.append(_make_entry(card, device, card_label, dev_label))

    # Fallback leyendo /proc/asound/cards si arecord no devolvió nada
    if not devices:
        try:
            with open('/proc/asound/cards', 'r') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            for l in lines:
                # formato: 0 [bcm2835_alsa]: bcm2835_alsa - bcm2835 ALSA
                parts = l.split(None, 2)
                if not parts:
                    continue
                cardnum = parts[0]
                label = parts[-1] if len(parts) >= 2 else f'card {cardnum}'
                devices.append(_make_entry(cardnum, '0', label, 'device 0'))
        except Exception:
            pass

    # Añadir opción por defecto si no encontramos nada
    if not devices:
        devices.append({'value': '', 'label': 'No mic detected'})

    # Dedup y orden
    seen = set()
    unique = []
    for d in devices:
        if d['value'] in seen:
            continue
        unique.append(d)
        seen.add(d['value'])
    return unique


def list_audio_outputs():
    """Devuelve una lista de dispositivos de salida ALSA para el monitor de audio."""
    devices = []
    try:
        out = subprocess.check_output(['aplay', '-l'], stderr=subprocess.STDOUT).decode(errors='ignore')
    except Exception:
        out = ''

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'card\s+(\d+):\s*(.*?)\s*\[(.*?)\],\s*device\s+(\d+):\s*(.*?)\s*\[(.*?)\]', line)
        if m:
            card = m.group(1)
            card_label = m.group(3)
            device = m.group(4)
            dev_label = m.group(6)
            value = f'plughw:{card},{device}'   # <-- antes: f'hw:{card},{device}'
            label = f"{card_label} - {dev_label} (card {card}, device {device})"
            devices.append({'value': value, 'label': label})

    if not devices:
        devices.append({'value': 'default', 'label': 'Default output'})

    seen = set()
    unique = []
    for d in devices:
        if d['value'] in seen:
            continue
        unique.append(d)
        seen.add(d['value'])
    return unique

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