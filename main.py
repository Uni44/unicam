from flask import Flask, render_template_string, send_from_directory, Response, request, jsonify, abort
from flask_socketio import SocketIO
import threading
import time
import psutil
import subprocess
from htmlTemplates import HTML_PW, HTML_OR, HTML_INICIO, HTML_COF
from lcd_preview import PrintImageDisplay
from PIL import Image, ImageOps
import os
import yappi
from camera_config import (
    load_config, save_config, aplicar_camara_config, get_camera_config, update_camera_config, CONFIG
)
from video_stream import (
    video_stream_thread, restart_video_thread, zoom_yuv420, zoom_loop, zoom, rtp_to_rtsp_thread, apply_config_to_active_camera
)
from gpio_control import (
    start_blink, blink_led, on_press, on_release, buttons
)
from wifi_manager import (
    wifi, configurar_wifi, ComprobeWifi, tiene_internet
)
from foto_capture import restart_foto_thread, apply_config_to_active_camera_foto, capture_foto
from video_rec import restart_rec_thread, apply_config_to_active_camera_rec, capture_rec
import gpio_control

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode="threading")

start_time = time.time()

@app.route('/files')
def files():
    return "<h2>Explorador del sistema</h2><a href='/browse/'>Abrir navegador de archivos</a>"

# 🔍 Ruta para explorar carpetas
@app.route('/browse/', defaults={'path': ''})
@app.route('/browse/<path:path>')
def browse(path):
    base_path = "/"  # raíz del sistema
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
    # Botón para volver atrás
    if path:
        parent = os.path.dirname(path)
        html += f'<li><a href="/browse/{parent}">🔙 Volver</a></li>'

    for item in items:
        item_path = os.path.join(path, item)
        full_path = os.path.join(abs_path, item)
        if os.path.isdir(full_path):
            html += f'<li>📁 <a href="/browse/{item_path}">{item}</a></li>'
        else:
            html += f'<li>📄 <a href="/browse/{item_path}">{item}</a></li>'
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

@app.route('/zoom', methods=['POST'])
def api_zoom():
    return zoom()

@app.route('/')
def index():
    return render_template_string(HTML_INICIO)

@app.route('/preview')
def preview():
    return render_template_string(HTML_PW)

@app.route('/original')
def original():
    return render_template_string(HTML_OR)

@app.route("/system-info")
def system_info():
    cpu_percent = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    temp = gpio_control.get_temperature()
    disk = int(psutil.disk_usage('/').percent)
    return jsonify({
        "cpu": cpu_percent,
        "ram_used": round(ram.used / 1024 / 1024 / 1024, 1),
        "ram_total": round(ram.total / 1024 / 1024 / 1024, 1),
        "temperature": temp,
        "disk": disk,
        "uptime": start_time
    })

@app.route('/status')
def status():
    cpu = int(psutil.cpu_percent())
    ram = int(psutil.virtual_memory().percent)
    temp = 0
    cpu_freq = gpio_control.get_cpu_freq()
    try:
        temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) // 1000
    except:
        temp = 50
    disk = int(psutil.disk_usage('/').percent)
    return jsonify(cpu=cpu, ram=ram, temp=temp, disk=disk, cpu_freq=cpu_freq)

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
    if CONFIG.get("modo") == "Stream":
        restart_video_thread()
    if CONFIG.get("modo") == "Foto":
        capture_foto()
    if CONFIG.get("modo") == "Grabar":
        capture_rec()
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
        
    try:
        socketio.run(app, host='0.0.0.0', port=8044, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        #yappi.stop()
        #print("\n=== Stats por función ===")
        #yappi.get_func_stats().print_all()
        #print("\n=== Stats por thread ===")
        #yappi.get_thread_stats().print_all()
        print("\n=== Unicam Finalizado ===")