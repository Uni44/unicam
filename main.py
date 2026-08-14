from flask import Flask, render_template, send_from_directory, Response, request, jsonify, abort
from flask_socketio import SocketIO
try:
    from flask_sock import Sock
except Exception:  # pragma: no cover - fallback for environments without the extra package
    Sock = None
import threading
import time
import psutil
import subprocess
import uuid
from PIL import Image, ImageOps
import os
import shutil
import yappi
import logging
from camera_config import (
    save_config, get_camera_config, update_camera_config, CONFIG, getRunningCamera, list_mics, list_audio_outputs, list_storage_targets, resolve_storage_dir, load_config, get_storage_base_path, apply_digital_zoom_to_active_cameras
)
from media_cleanup import cleanup_media_directories
from encoder_guard import evaluate_encoder_warning
from overlay_utils import start_overlay_updater, clear_overlay
from video_stream import (
    video_stream_thread, restart_video_thread, apply_config_to_active_camera
)
from gpio_control import start_blink, blink_led, on_press, on_release
from wifi_manager import wifi
from foto_capture import restart_foto_thread, apply_config_to_active_camera_foto, capture_foto
from video_rec import restart_rec_thread, apply_config_to_active_camera_rec, capture_rec
import gpio_control
from ups_driver import INA219
from talkback import talkback_queue, try_acquire, release, touch, ensure_fifo, start_talkback_feeder, build_tts_chunk, build_tts_chunks, play_tts_audio

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode="threading")
sock = Sock(app) if Sock is not None else None

try:
    ensure_fifo()
    start_talkback_feeder()
except Exception as e:
    logging.warning("No se pudo inicializar talkback feeder: %s", e)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('sistema_status.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('socketio').setLevel(logging.ERROR)
logging.getLogger('engineio').setLevel(logging.ERROR)

try:
    gpio_control.register_button_handlers()
    gpio_control.set_camera_running(bool(getRunningCamera()))
    logging.info("GPIO handlers inicializados")
except Exception as e:
    logging.warning("GPIO no disponible o no inicializado: %s", e)

start_time = time.time()

try:
    sensor_ups = INA219(addr=0x41) 
except Exception as e:
    logging.error(f"Error inicializando INA219: {e}")
    sensor_ups = None
    
@app.route('/files')
def files():
    return "<h2>Explorador del sistema</h2><a href='/browse/'>Abrir navegador de archivos</a>"

# Ruta para explorar carpetas
@app.route('/browse/', defaults={'path': ''})
@app.route('/browse/<path:path>')
def browse(path):
    base_path = "/"  # raiz del sistema
    abs_path = os.path.join(base_path, path)

    if not os.path.exists(abs_path):
        try:
            os.makedirs(abs_path, exist_ok=True)
        except Exception:
            return render_template('browse.html', current_path=abs_path, parent_path=None, items=[]), 404

    if os.path.isfile(abs_path):
        try:
            return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))
        except Exception as e:
            return f"<h3>Error al abrir archivo: {e}</h3>"

    try:
        items = os.listdir(abs_path)
        items.sort()
    except PermissionError:
        return render_template('browse.html', current_path=abs_path, parent_path=None, items=[]), 403

    item_list = []
    for item in items:
        item_path = os.path.join(path, item)
        full_path = os.path.join(abs_path, item)
        item_list.append({
            'name': item,
            'url': f'/browse/{item_path}'.replace('\\', '/'),
        })

    parent_path = None
    if path:
        parent_path = f"/browse/{os.path.dirname(path)}".replace('\\', '/')

    return render_template('browse.html', current_path=abs_path, parent_path=parent_path, items=item_list)

@app.route("/api/storage-targets")
def api_storage_targets():
    try:
        return jsonify({"targets": list_storage_targets(), "default": os.getcwd()})
    except Exception as e:
        return jsonify({"targets": [], "default": os.getcwd(), "error": str(e)})

@app.route("/api/camera-config", methods=["GET"])
def api_get_camera_config():
    cfg = load_config()
    return jsonify({**cfg, "encoder_warning": evaluate_encoder_warning(cfg)})

@app.route("/api/camera-config", methods=["POST"])
def api_update_camera_config():
    old_cfg = load_config()
    old_mode = old_cfg.get("modo")
    data = request.get_json()
    save_config(data)
    new_cfg = load_config()
    new_mode = new_cfg.get("modo")
    if old_mode != new_mode:
        switch_camera_mode(old_mode, new_mode)
    else:
        apply_config_to_active_camera()
        apply_config_to_active_camera_foto()
        apply_config_to_active_camera_rec()
    return jsonify({"status": "ok", "message": "Configuración guardada", "encoder_warning": evaluate_encoder_warning(new_cfg)})

@app.route('/api/encoder-warning')
def api_encoder_warning():
    cfg = load_config()
    return jsonify(evaluate_encoder_warning(cfg))

@app.route('/api/hdmi-overlay', methods=['GET'])
def api_get_hdmi_overlay():
    cfg = load_config()
    return jsonify({"hdmi_overlay": bool(cfg.get("hdmi_overlay", True))})

@app.route('/api/media/cleanup', methods=['POST'])
def api_cleanup_media():
    try:
        cfg = load_config()
        media_dirs = []
        for kind in ("fotos", "videos"):
            try:
                target_dir = resolve_storage_dir(kind, cfg)
            except Exception:
                continue
            if target_dir:
                media_dirs.append(target_dir)

        if not media_dirs:
            return jsonify({"status": "error", "message": "No se encontraron carpetas de media configuradas", "removed_files": 0}), 400

        base_dir = get_storage_base_path(cfg) or os.getcwd()
        result = cleanup_media_directories(media_dirs, base_dir=base_dir)
        return jsonify({"status": "ok", **result})
    except Exception as e:
        logging.exception("Error limpiando media")
        return jsonify({"status": "error", "message": str(e), "removed_files": 0}), 500

@app.route('/api/hdmi-overlay', methods=['POST'])
def api_set_hdmi_overlay():
    payload = request.get_json(silent=True) or {}
    enabled = payload.get('enabled')
    if enabled is None:
        return jsonify({"status": "error", "message": "'enabled' field required"}), 400
    try:
        cfg = load_config()
        cfg['hdmi_overlay'] = bool(enabled)
        save_config(cfg)

        # Apply change to running modules if possible
        for module_name in ("video_stream", "foto_capture", "video_rec"):
            try:
                module = __import__(module_name)
                stop_event = getattr(module, 'overlay_stop', None)
                if stop_event is not None:
                    try:
                        stop_event.set()
                    except Exception:
                        pass
                if getattr(module, 'overlay_thread', None) and getattr(module.overlay_thread, 'is_alive', lambda: False)():
                    try:
                        module.overlay_thread.join(timeout=1)
                    except Exception:
                        pass
                module.overlay_stop = None
                module.overlay_thread = None

                if cfg['hdmi_overlay'] and getattr(module, 'picam2', None):
                    try:
                        module.overlay_thread, module.overlay_stop = start_overlay_updater(module.picam2, interval=1.0)
                    except Exception:
                        pass
                else:
                    try:
                        clear_overlay(getattr(module, 'picam2', None), size=(1920, 1080))
                    except Exception:
                        pass
            except Exception:
                pass

        return jsonify({"status": "ok", "hdmi_overlay": bool(cfg['hdmi_overlay'])})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _join_thread(thread, timeout=8):
    if thread is None:
        return True
    thread.join(timeout=timeout)
    if thread.is_alive():
        logging.warning("Hilo %s sigue vivo después de %s segundos", thread.name, timeout)
        return False
    return True


def stop_mode(mode):
    try:
        if mode == "Stream":
            import video_stream
            if getattr(video_stream, 'video_thread_running', None):
                video_stream.video_thread_running.clear()
            if getattr(video_stream, 'video_thread', None) and video_stream.video_thread.is_alive():
                if not _join_thread(video_stream.video_thread, timeout=8):
                    logging.warning("El hilo de Stream no terminó a tiempo.")
        elif mode == "Foto":
            import foto_capture
            if getattr(foto_capture, 'video_thread_running', None):
                foto_capture.video_thread_running.clear()
            if getattr(foto_capture, 'video_thread', None) and foto_capture.video_thread.is_alive():
                if not _join_thread(foto_capture.video_thread, timeout=8):
                    logging.warning("El hilo de Foto no terminó a tiempo.")
        elif mode == "Grabar":
            import video_rec
            try:
                video_rec.recTake = False
            except Exception:
                pass
            if getattr(video_rec, 'video_thread_running', None):
                video_rec.video_thread_running.clear()
            if getattr(video_rec, 'video_thread', None) and video_rec.video_thread.is_alive():
                if not _join_thread(video_rec.video_thread, timeout=8):
                    logging.warning("El hilo de Grabar no terminó a tiempo.")
    except Exception as e:
        logging.error(f"Error deteniendo modo {mode}: {e}")


def start_mode(mode):
    try:
        if mode == "Stream":
            restart_video_thread()
        elif mode == "Foto":
            restart_foto_thread()
        elif mode == "Grabar":
            import video_rec
            if (getattr(video_rec, 'video_thread', None) is None or
                    not getattr(video_rec, 'video_thread').is_alive() or
                    not getattr(video_rec, 'video_thread_running', None).is_set()):
                video_rec.restart_rec_thread()
            # No iniciar la grabación automáticamente en modo Grabar.
            # El usuario debe pulsar el botón de grabación.

        try:
            import gpio_control
            gpio_control.stop_focus()
            gpio_control.FOCUS_MODE = 'autofocus'
            gpio_control.set_optics_state(focus='AF-C', focus_mode='autofocus')
            gpio_control.set_led('autofocus', False)
            gpio_control._stop_continuous_autofocus()
            gpio_control._start_continuous_autofocus()
        except Exception as exc:
            logging.warning(f"No se pudo activar autofocus al arrancar la cámara: {exc}")
    except Exception as e:
        logging.error(f"Error iniciando modo {mode}: {e}")


def switch_camera_mode(old_mode, new_mode):
    if old_mode == new_mode or not new_mode:
        return
    stop_mode(old_mode)
    start_mode(new_mode)

@app.post("/force_full_reload")
def force_full_reload():
    try:
        apply_config_to_active_camera(True)
        apply_config_to_active_camera_foto(True)
        apply_config_to_active_camera_rec(True)
        return {"status": "bien"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/talkback-ui')
def talkback_ui():
    return render_template('talkback.html')

@app.route('/api/optics/status')
def api_optics_status():
    optics_state = {}
    try:
        optics_state = gpio_control.get_optics_state() or {}
    except Exception:
        optics_state = {}

    return jsonify({
        "zoom_speed_mode": getattr(gpio_control, "ZOOM_SPEED_MODE", "slow"),
        "focus_mode": optics_state.get("focus_mode", getattr(gpio_control, "FOCUS_MODE", "manual")),
        "zoom": optics_state.get("zoom", optics_state.get("optical_zoom", 1.0)),
        "focus_position": optics_state.get("focus_position", 0.0),
        "zooming_in": bool(getattr(gpio_control, "zooming_in", False)),
        "zooming_out": bool(getattr(gpio_control, "zooming_out", False)),
        "focus_moving": bool(getattr(gpio_control, "focus_moving", False)),
        "focus_direction": getattr(gpio_control, "focus_direction", None),
    })

@app.route('/api/optics/control', methods=['POST'])
def api_optics_control():
    payload = request.get_json(silent=True) or {}
    action = (payload.get('action') or '').strip()

    if action == 'zoom_in':
        gpio_control.start_zoom('in')
        apply_digital_zoom_to_active_cameras()
        return jsonify({"status": "ok", "action": action})

    if action == 'zoom_out':
        gpio_control.start_zoom('out')
        apply_digital_zoom_to_active_cameras()
        return jsonify({"status": "ok", "action": action})

    if action == 'zoom_stop':
        gpio_control.stop_zoom()
        apply_digital_zoom_to_active_cameras()
        return jsonify({"status": "ok", "action": action})

    if action == 'zoom_speed_toggle':
        gpio_control.toggle_zoom_speed()
        return jsonify({"status": "ok", "action": action, "zoom_speed_mode": getattr(gpio_control, "ZOOM_SPEED_MODE", "slow")})

    if action == 'focus_in':
        if getattr(gpio_control, 'FOCUS_MODE', 'manual') == 'autofocus':
            gpio_control._stop_continuous_autofocus()
        gpio_control.FOCUS_MODE = 'manual'
        gpio_control.set_optics_state(focus='MF', focus_mode='manual')
        # En modo manual el LED de autofocus debe quedar apagado
        gpio_control.set_led('autofocus', True)
        gpio_control.start_focus('in')
        return jsonify({"status": "ok", "action": action})

    if action == 'focus_out':
        if getattr(gpio_control, 'FOCUS_MODE', 'manual') == 'autofocus':
            gpio_control._stop_continuous_autofocus()
        gpio_control.FOCUS_MODE = 'manual'
        gpio_control.set_optics_state(focus='MF', focus_mode='manual')
        # En modo manual el LED de autofocus debe quedar apagado
        gpio_control.set_led('autofocus', True)
        gpio_control.start_focus('out')
        return jsonify({"status": "ok", "action": action})

    if action == 'focus_stop':
        gpio_control.stop_focus()
        return jsonify({"status": "ok", "action": action})

    if action == 'autofocus_toggle':
        if getattr(gpio_control, 'FOCUS_MODE', 'manual') == 'autofocus':
            gpio_control.FOCUS_MODE = 'manual'
            gpio_control.set_optics_state(focus='MF', focus_mode='manual')
            gpio_control.set_led('autofocus', True)
            gpio_control.stop_focus()
            gpio_control._stop_continuous_autofocus()
        else:
            gpio_control.FOCUS_MODE = 'autofocus'
            gpio_control.set_optics_state(focus='AF-C', focus_mode='autofocus')
            gpio_control.set_led('autofocus', False)
            gpio_control.stop_focus()
            gpio_control._start_continuous_autofocus()
        return jsonify({"status": "ok", "action": action, "focus_mode": getattr(gpio_control, 'FOCUS_MODE', 'manual')})

    return jsonify({"status": "error", "message": "Acción no soportada"}), 400

@app.route('/api/optics/calibrate', methods=['POST'])
def api_optics_calibrate():
    payload = request.get_json(silent=True) or {}
    zoom_steps = payload.get('zoom_steps')
    output_path = payload.get('output_path')

    if zoom_steps is not None:
        if not isinstance(zoom_steps, list):
            return jsonify({"status": "error", "message": "zoom_steps debe ser una lista de enteros"}), 400
        try:
            zoom_steps = [int(value) for value in zoom_steps]
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "zoom_steps contiene valores no válidos"}), 400

    try:
        table = gpio_control.calibrate_zoom_focus_table(zoom_steps=zoom_steps, output_path=output_path)
        if table is None:
            return jsonify({"status": "error", "message": "No se pudo calibrar: autofoco no activo o error interno."}), 400
        return jsonify({"status": "ok", "table": table})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

if sock is not None:
    @sock.route('/talkback')
    def talkback_ws(ws):
        client_id = str(uuid.uuid4())
        granted = False
        try:
            while True:
                data = ws.receive()
                if data is None:
                    break
                if data == "__PTT_DOWN__":
                    granted = try_acquire(client_id)
                    ws.send("granted" if granted else "busy")
                    continue
                if data == "__PTT_UP__":
                    release(client_id)
                    granted = False
                    ws.send("released")
                    continue
                if data.startswith("__TTS__:"):
                    message = data[len("__TTS__:"):].strip()
                    if message:
                        if try_acquire(client_id):
                            play_tts_audio(message)
                            touch(client_id)
                            release(client_id)
                            ws.send("tts-ok")
                        else:
                            ws.send("busy")
                    continue
                if granted:
                    touch(client_id)
                    talkback_queue.put(data)
        finally:
            release(client_id)
else:
    @app.route('/talkback')
    def talkback_ws():
        return jsonify({"status": "unavailable"}), 501

def _get_disk_stats(path):
    try:
        usage = shutil.disk_usage(path)
    except Exception:
        return None

    total_gb = round(usage.total / (1024 ** 3), 1)
    used_gb = round(usage.used / (1024 ** 3), 1)
    free_gb = round(usage.free / (1024 ** 3), 1)
    percent = int((usage.used / usage.total) * 100) if usage.total else 0
    return {
        "path": path,
        "percent": percent,
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
    }


@app.route('/status')
def status():
    try:
        cpu = int(psutil.cpu_percent())
        ram = int(psutil.virtual_memory().percent)
        temp = 0
        cpu_freq = gpio_control.get_cpu_freq()
        try:
            temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) // 1000
        except Exception:
            temp = 0

        system_disk = _get_disk_stats('/') or {"percent": 0, "free_gb": 0, "used_gb": 0, "total_gb": 0}

        storage_cfg = load_config() if callable(load_config) else (CONFIG if CONFIG else {})
        storage_path = get_storage_base_path(storage_cfg)
        if not storage_path:
            storage_path = os.getcwd()

        expanded_storage_path = os.path.expanduser(storage_path)
        if not expanded_storage_path or expanded_storage_path.startswith("/dev"):
            expanded_storage_path = os.getcwd()
        storage_disk = _get_disk_stats(expanded_storage_path) or system_disk

        running = getRunningCamera()
        ups_data = {"status": "offline"}
        if sensor_ups:
            ups_data = sensor_ups.get_stats()
        try:
            gpio_control.update_power_led_state()
        except Exception:
            pass
        log_message = (
            f"CPU={cpu}%, RAM={ram}%, Temp={temp}°C, "
            f"Disk={system_disk['percent']}%, Freq={cpu_freq}MHz, Camera={'ON' if running else 'OFF'}"
            f"Bat={ups_data.get('battery_percent', 0)}%, V={ups_data.get('voltage_v', 0)}V"
        )
        logging.debug(log_message)

        return jsonify(
            cpu=cpu,
            ram=ram,
            temp=temp,
            disk=system_disk["percent"],
            storage_disk=storage_disk["percent"],
            storage_path=storage_path,
            disk_info=system_disk,
            storage_info=storage_disk,
            cpu_freq=cpu_freq,
            running=running,
            ups=ups_data,
        )
    except Exception as e:
        logging.exception("Error en /status")
        payload = {
            "cpu": 0,
            "ram": 0,
            "temp": 0,
            "disk": 0,
            "storage_disk": 0,
            "storage_path": os.getcwd(),
            "disk_info": {"percent": 0, "free_gb": 0, "used_gb": 0, "total_gb": 0},
            "storage_info": {"percent": 0, "free_gb": 0, "used_gb": 0, "total_gb": 0},
            "cpu_freq": 0,
            "running": False,
            "ups": {"status": "offline"},
            "error": str(e),
        }
        return jsonify(payload), 500

def log_system_status():
    cpu = int(psutil.cpu_percent())
    ram = int(psutil.virtual_memory().percent)
    temp = 0
    cpu_freq = gpio_control.get_cpu_freq() # Asumo que esta funcion existe
    try:
        temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) // 1000
    except:
        temp = 0
    disk = int(psutil.disk_usage('/').percent)
    running = getRunningCamera() # Asumo que esta funcion existe
    ups_data = {"status": "offline"}
    if sensor_ups:
        ups_data = sensor_ups.get_stats()
    log_message = (
        f"CPU={cpu}%, RAM={ram}%, Temp={temp}°C, "
        f"Disk={disk}%, Freq={cpu_freq}MHz, Camera={'ON' if running else 'OFF'}"
        f"Bat={ups_data.get('battery_percent', 0)}%, V={ups_data.get('voltage_v', 0)}V"
    )
    logging.debug(log_message)

# Funcion para ejecutar el registro cada 60 segundos
def background_logging_task():
    while True:
        log_system_status()
        time.sleep(60) # Espera 60 segundos (puedes ajustar este valor)

@app.route('/restart', methods=['POST'])
def restart():
    subprocess.Popen(['sudo','reboot'])
    return '', 204

@app.route('/shutdown', methods=['POST'])
def shutdown():
    subprocess.Popen(['sudo','poweroff'])
    return '', 204

@app.route('/start', methods=['POST'])
def start():
    try:
        import camera_config as cam_cfg
        cfg = cam_cfg.load_config()
        mode = cfg.get("modo")
    except Exception:
        mode = CONFIG.get("modo")

    try:
        if mode == "Stream":
            start_mode(mode)
        elif mode == "Foto":
            import foto_capture
            if getattr(foto_capture, 'video_thread', None) is None or not getattr(foto_capture, 'video_thread').is_alive():
                foto_capture.restart_foto_thread()
            foto_capture.capture_foto()
        elif mode == "Grabar":
            import video_rec
            if getattr(video_rec, 'video_thread', None) is None or not getattr(video_rec, 'video_thread').is_alive():
                video_rec.restart_rec_thread()
            video_rec.capture_rec()
        else:
            start_mode(mode)
    except Exception as e:
        logging.error(f"Error en start handler: {e}")
    return '', 204


@app.route('/api/mics')
def api_mics():
    try:
        return jsonify(list_mics())
    except Exception as e:
        return jsonify([])


@app.route('/api/audio-outputs')
def api_audio_outputs():
    try:
        return jsonify(list_audio_outputs())
    except Exception as e:
        return jsonify([])


@app.route('/api/hdmi/restart', methods=['POST'])
def api_hdmi_restart():
    restarted = []
    errors = []
    # Try to signal each module that may manage HDMI
    try:
        import video_stream
        if hasattr(video_stream, 'request_hdmi_restart'):
            video_stream.request_hdmi_restart()
            restarted.append('video_stream')
    except Exception as e:
        errors.append(f"video_stream:{e}")
    try:
        import video_rec
        if hasattr(video_rec, 'request_hdmi_restart'):
            video_rec.request_hdmi_restart()
            restarted.append('video_rec')
    except Exception as e:
        errors.append(f"video_rec:{e}")
    try:
        import foto_capture
        if hasattr(foto_capture, 'request_hdmi_restart'):
            foto_capture.request_hdmi_restart()
            restarted.append('foto_capture')
    except Exception as e:
        errors.append(f"foto_capture:{e}")

    return jsonify({'restarted': restarted, 'errors': errors})


@app.route('/stop', methods=['POST'])
def stop():
    # Import modules (they are already loaded but import safely)
    try:
        import video_stream
    except Exception:
        video_stream = None
    try:
        import video_rec
    except Exception:
        video_rec = None
    try:
        import camera_config as cam_cfg
    except Exception:
        cam_cfg = None

    # Determine current mode using live config if possible
    try:
        cfg_mode = None
        if cam_cfg:
            try:
                cfg_mode = cam_cfg.load_config().get("modo")
            except Exception:
                cfg_mode = None
    except Exception:
        cfg_mode = None

    mode = cfg_mode if cfg_mode is not None else CONFIG.get("modo")

    # Stop stream thread if running
    try:
        if video_stream and mode == "Stream":
            video_stream.video_thread_running.clear()
            if getattr(video_stream, 'video_thread', None) and video_stream.video_thread.is_alive():
                video_stream.video_thread.join(timeout=2)
    except Exception as e:
        logging.error(f"Error stopping stream: {e}")

    # Stop recording if active
    try:
        if video_rec and mode == "Grabar":
            # ensure recording flag is false so recording stops cleanly
            try:
                video_rec.recTake = False
            except Exception:
                pass
            # Keep the capture thread running so HDMI/stream remain active.
            # The recording thread loop will detect `recTake == False` and
            # stop the ffmpeg subprocess without closing the camera.
    except Exception as e:
        logging.error(f"Error stopping recording: {e}")

    # mark camera as stopped (but don't mark camera STOPPED when in Grabar mode)
    try:
        if cam_cfg and mode != "Grabar":
            cam_cfg.changeRunningCamera(False)
    except Exception:
        pass

    return '', 204

@app.route("/wifi", methods=["GET", "POST"])
def api_wifi():
    return wifi()

if __name__ == '__main__':
    #yappi.set_clock_type("wall")
    #yappi.start()
    logging.info("Iniciando Unicam")
    
    start_mode(CONFIG.get("modo"))
    
    log_thread = threading.Thread(target=background_logging_task, daemon=True)
    log_thread.start()
        
    try:
        socketio.run(app, host='0.0.0.0', port=8044, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        #yappi.stop()

        #stats = yappi.get_func_stats()
        #stats.sort("ttot", "desc")  # ordena por tiempo total (incluye subllamadas)

        #print("\n=== TOP 30 funciones por tiempo total ===")
        #stats.print_all(
        #    columns={
        #        0: ("name", 90),
        #        1: ("ncall", 10),
        #        2: ("tsub", 8),
        #        3: ("ttot", 8),
        #        4: ("tavg", 8),
        #    }
        #)

        # Guardá también un archivo para inspección visual
        #stats.save("/tmp/unicam.callgrind", type="callgrind")
        #print("\nGuardado en /tmp/unicam.callgrind (abrir con qcachegrind)")

        #print("\n=== Stats por thread ===")
        #yappi.get_thread_stats().print_all()

        print("\n=== Unicam Finalizado ===")