from flask import Flask, render_template_string, send_from_directory, Response, request, jsonify, abort
from flask_socketio import SocketIO
import threading
import time
import psutil
import subprocess
from htmlTemplates import HTML_INICIO, HTML_COF
from lcd_preview import PrintImageDisplay
from PIL import Image, ImageOps
import os
import yappi
import logging
from camera_config import (
    save_config, get_camera_config, update_camera_config, CONFIG, getRunningCamera, list_mics
)
from video_stream import (
    video_stream_thread, restart_video_thread, zoom_yuv420, zoom_loop, zoom, rtp_to_rtsp_thread, apply_config_to_active_camera
)
from gpio_control import start_blink, blink_led, on_press, on_release
from wifi_manager import wifi
from foto_capture import restart_foto_thread, apply_config_to_active_camera_foto, capture_foto
from video_rec import restart_rec_thread, apply_config_to_active_camera_rec, capture_rec
import gpio_control
from ups_driver import INA219

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode="threading")

logging.basicConfig(
    filename='sistema_status.log', # Nombre del archivo de log
    level=logging.INFO, # Nivel de registro (INFO para datos generales)
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S' # Formato de fecha y hora
)

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
        return f"<h3>Ruta no encontrada: {abs_path}</h3>", 404

    # Si es archivo -> mostrar o descargar
    if os.path.isfile(abs_path):
        try:
            return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))
        except Exception as e:
            return f"<h3>Error al abrir archivo: {e}</h3>"

    # Si es carpeta -> listar contenido
    try:
        items = os.listdir(abs_path)
        items.sort()
    except PermissionError:
        return f"<h3>Sin permisos para acceder a: {abs_path}</h3>"

    html = f"<h2>Directorio: /{path}</h2><ul>"
    # Boton para volver atras
    if path:
        parent = os.path.dirname(path)
        html += f'<li><a href="/browse/{parent}">- Volver</a></li>'

    for item in items:
        item_path = os.path.join(path, item)
        full_path = os.path.join(abs_path, item)
        if os.path.isdir(full_path):
            html += f'<li>- <a href="/browse/{item_path}">{item}</a></li>'
        else:
            html += f'<li>- <a href="/browse/{item_path}">{item}</a></li>'
    html += "</ul>"
    return html

@app.route("/api/camera-config", methods=["GET"])
def api_get_camera_config():
    return get_camera_config()

@app.route("/api/camera-config", methods=["POST"])
def api_update_camera_config():
    result = update_camera_config()
    apply_config_to_active_camera()
    apply_config_to_active_camera_foto()
    apply_config_to_active_camera_rec()
    return result

@app.post("/force_full_reload")
def force_full_reload():
    try:
        apply_config_to_active_camera(True)
        apply_config_to_active_camera_foto(True)
        apply_config_to_active_camera_rec(True)
        return {"status": "bien"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

@app.route('/zoom', methods=['POST'])
def api_zoom():
    return zoom()

@app.route('/')
def index():
    return render_template_string(HTML_INICIO)

@app.route('/status')
def status():
    cpu = int(psutil.cpu_percent())
    ram = int(psutil.virtual_memory().percent)
    temp = 0
    cpu_freq = gpio_control.get_cpu_freq()
    try:
        temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) // 1000
    except:
        temp = 0
    disk = int(psutil.disk_usage('/').percent)
    running = getRunningCamera()
    ups_data = {"status": "offline"}
    if sensor_ups:
        ups_data = sensor_ups.get_stats()
    log_message = (
        f"CPU={cpu}%, RAM={ram}%, Temp={temp}°C, "
        f"Disk={disk}%, Freq={cpu_freq}MHz, Camera={'ON' if running else 'OFF'}"
        f"Bat={ups_data.get('battery_percent', 0)}%, V={ups_data.get('voltage_v', 0)}V"
    )
    logging.info(log_message)

    return jsonify(cpu=cpu, ram=ram, temp=temp, disk=disk, cpu_freq=cpu_freq, running=running, ups=ups_data)

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
    logging.info(log_message)

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
            restart_video_thread()
        elif mode == "Foto":
            capture_foto()
        elif mode == "Grabar":
            try:
                import video_rec
            except Exception:
                video_rec = None

            # Asegurarnos que el hilo de captura/rec esté corriendo
            try:
                if video_rec and (getattr(video_rec, 'video_thread', None) is None or not getattr(video_rec, 'video_thread').is_alive() or not getattr(video_rec, 'video_thread_running', None).is_set()):
                    video_rec.restart_rec_thread()
            except Exception as e:
                logging.error(f"Error iniciando hilo de rec: {e}")

            # Iniciar grabación (si no estaba ya grabando)
            try:
                if video_rec and not getattr(video_rec, 'recTake', False):
                    video_rec.capture_rec()
            except Exception as e:
                logging.error(f"Error arrancando grabación: {e}")
    except Exception as e:
        logging.error(f"Error en start handler: {e}")
    return '', 204


@app.route('/api/mics')
def api_mics():
    try:
        return jsonify(list_mics())
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
    #yappi.start()
    PrintImageDisplay("img/loading.png")
    
    if CONFIG.get("modo") == "Foto":
        restart_foto_thread()
    if CONFIG.get("modo") == "Stream":
        restart_video_thread()
    if CONFIG.get("modo") == "Grabar":
        restart_rec_thread()
        
    log_thread = threading.Thread(target=background_logging_task, daemon=True)
    log_thread.start()
        
    try:
        socketio.run(app, host='0.0.0.0', port=8044, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        #yappi.stop()
        #print("\n=== Stats por funcion ===")
        #yappi.get_func_stats().print_all()
        #print("\n=== Stats por thread ===")
        #yappi.get_thread_stats().print_all()
        print("\n=== Unicam Finalizado ===")