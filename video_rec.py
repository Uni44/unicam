import threading
import time
import subprocess
from flask import request
from picamera2 import Picamera2
import cv2
from camera_config import WIDTH, HEIGHT, TARGET_FPS, IPDestino, aplicar_camara_config, generar_sdp, CONFIG, picam2, load_config, changeRunningCamera, getMute, get_audio_level
from threading import Thread
from lcd_preview import LCDPreview, monitorState, PrintImageDisplay, InMenu, lcd_preview, getInMenuState, getMonitorState
from queue import Queue
from PIL import Image, ImageOps
from queue import Empty
import time
import numpy as np
from datetime import datetime
from video_stream import (
    zoom_lock, zoom_state, zoom_var, zoom_loop, zoom, zoom_yuv420
)
import os, psutil
import shutil

video_thread = None
preview_thread = None

video_thread_running = threading.Event()

proc_hdmi = None
proc_audio_hdmi = None  # Proceso para audio micrófono -> HDMI
hdmi_restart_event = threading.Event()
hdmi_write_lock = threading.Lock()
hdmi_paused = threading.Event()

latest_frame = None  # va a contener siempre el último frame
frame_lock = threading.Lock()

recTake = False

# Crear carpeta si no existe
carpeta = "videos"
os.makedirs(carpeta, exist_ok=True)

def video_stream_thread():

    def ensure_xdg_runtime_dir():
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
    video_thread_running.set()
    print("📡 Hilo de captura de rec iniciado.")
    
    global picam2, zoom_state, latest_frame, frame_lock, recTake, proc_hdmi, proc_audio_hdmi
    from gpio_control import start_blink, stop_blink

    CONFIG = load_config()
    mic_path = CONFIG.get("mic")
    is_mic_enabled = mic_path and not mic_path.startswith('!')
    if is_mic_enabled:
        print(f"Micrófono detectado y activo: {mic_path}")
    else:
        CONFIG["mic"] = ""
        print("Micrófono desactivado o comentado con '!'. Solo de video.")
    WIDTH, HEIGHT = map(int, CONFIG["resolution"].lower().split("x"))
    TARGET_FPS = CONFIG["fps"]

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"format": "YUV420", "size": (WIDTH, HEIGHT)}
    )
    picam2.configure(config)
    picam2.start()
    aplicar_camara_config(picam2, True)
    
    changeRunningCamera(True)
    
    stop_error = False
    recording = False
    # Deshabilitar el mouse a nivel de X11
    os.system('xset m 0 0 2>/dev/null || true')
    # Ocultar con unclutter
    subprocess.Popen(['unclutter', '-idle', '0', '-keystroke'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Mover el cursor fuera de pantalla
    os.system('xdotool mousemove 9999 9999 2>/dev/null || true')
    hdmiState = True
    opcion_hdmi = CONFIG.get("hdmi")
    if opcion_hdmi == "Off":
        hdmiState = False
    res_hdmi = f"{WIDTH}x{HEIGHT}"
    if opcion_hdmi == "Mid":
        res_hdmi = "1280x720"
    elif opcion_hdmi == "Low": # El tercero
        res_hdmi = "640x360"
    cmd_hdmi = [
        'ffmpeg',
        '-hide_banner', '-loglevel', 'error', '-nostats',
        '-fflags', 'nobuffer+genpts',
        '-flags', 'low_delay',
        '-use_wallclock_as_timestamps', '1',
        '-thread_queue_size', '4096',
        '-f', 'rawvideo',
        '-pix_fmt', 'yuv420p',
        '-s', f'{WIDTH}x{HEIGHT}',
        '-framerate', str(TARGET_FPS),
        '-i', '-', 
        '-vf', f'scale={res_hdmi}:flags=neighbor,format=rgb565le', 
        '-f', 'fbdev',
        '-fps_mode', 'passthrough',
        '/dev/fb0'
    ]
    if hdmiState:
        # Abrir en modo append para no truncar logs previos
        ensure_xdg_runtime_dir()
        with open("hdmi_log.txt", "ab") as f:
            try:
                proc_hdmi = subprocess.Popen(cmd_hdmi, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                time.sleep(0.12)
            except Exception as e:
                print("❌ No se pudo iniciar HDMI ffmpeg:", e)
                proc_hdmi = None
    
    # Iniciar audio micrófono -> HDMI si está habilitado
    #if is_mic_enabled:
        # Audio HDMI desactivado para evitar conflicto con FFmpeg en el mismo dispositivo
        # try:
        #     # Detectar dispositivo HDMI (intentar primero card 0, luego card 1)
        #     hdmi_device = "hw:0,0"  # HDMI 0 por defecto
        #     mic_device = mic_path
        #     
        #     cmd_audio = [
        #         'arecord', '-D', mic_device, '-t', 'wav', 
        #         '-c', '2', '-r', '48000', '-f', 'S16_LE'
        #     ]
        #     cmd_audio_play = [
        #         'aplay', '-D', hdmi_device, '-'
        #     ]
        #     
        #     # Crear pipe: arecord | aplay
        #     proc_audio_rec = subprocess.Popen(cmd_audio, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        #     proc_audio_hdmi = subprocess.Popen(cmd_audio_play, stdin=proc_audio_rec.stdout, 
        #                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #     print(f"🎙️ Audio capturado de {mic_device} → HDMI {hdmi_device}")
        # except Exception as e:
        #     print(f"⚠️ No se pudo iniciar audio HDMI: {e}")
        #     proc_audio_hdmi = None
            
    try:
        while video_thread_running.is_set() and not stop_error:
            frame = picam2.capture_array("main")
            current_zoom = zoom_state['factor']
            frame = zoom_yuv420(frame, WIDTH, HEIGHT, current_zoom)
            # Respect external HDMI restart requests
            if hdmi_restart_event.is_set():
                hdmi_restart_event.clear()
                try:
                    hdmi_write_lock.acquire()
                    hdmi_paused.set()
                    if proc_hdmi:
                        try:
                            if proc_hdmi.stdin:
                                try:
                                    proc_hdmi.stdin.close()
                                except Exception:
                                    pass
                            proc_hdmi.terminate()
                            proc_hdmi.wait(timeout=1)
                        except Exception:
                            try:
                                proc_hdmi.kill()
                            except Exception:
                                pass
                        proc_hdmi = None
                    ensure_xdg_runtime_dir()
                    with open("hdmi_log.txt", "ab") as f:
                        try:
                            proc_hdmi = subprocess.Popen(cmd_hdmi, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                            print("🔁 HDMI ffmpeg forzado reiniciado (rec).")
                            time.sleep(0.12)
                        except Exception as e:
                            print("❌ Falló forzar reinicio HDMI ffmpeg (rec):", e)
                            proc_hdmi = None
                except Exception as er:
                    print("⚠️ Error forzando reinicio HDMI (rec):", er)
                finally:
                    hdmi_paused.clear()
                    try:
                        hdmi_write_lock.release()
                    except Exception:
                        pass
            
            if recTake and not recording:
                print("🎬 Iniciando grabación...")
                output_name = os.path.join(carpeta, time.strftime("record_%Y%m%d_%H%M%S.mp4"))
                # Reordenado y optimizado
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-nostats",
                    "-thread_queue_size", "1024",
                    "-f", "rawvideo",
                    "-pix_fmt", "yuv420p",
                    "-s", f"{WIDTH}x{HEIGHT}",
                    "-framerate", str(TARGET_FPS),
                    "-i", "-",  # Entrada de video
                ]

                if CONFIG.get("mic"):
                    cmd.extend([
                        "-thread_queue_size", "4096",
                        "-f", "alsa",
                        "-ac", "2", # Tu log dice que el mic es stereo
                        "-i", CONFIG.get("mic"), # Entrada de audio
                    ])

                # Salida y Códecs
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", CONFIG.get("preset"), # CAMBIO CRÍTICO para no perder FPS
                    "-crf", "20",           # Un poco más de compresión para ayudar
                    "-tune", "zerolatency", # Ideal para capturas en tiempo real
                ])

                if CONFIG.get("mic"):
                    cmd.extend([
                        "-c:a", "aac",
                        "-b:a", "128k",
                        "-map", "0:v", "-map", "1:a"
                    ])
                cmd.append(output_name)
                with open("rec_log.txt", "wb") as f:
                    ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                recording = True
                start_blink()
            elif not recTake and recording:
                print("🛑 Deteniendo grabación...")
                if ffmpeg_proc and ffmpeg_proc.stdin:
                    try:
                        ffmpeg_proc.stdin.close()
                    except:
                        pass
                for p in [ffmpeg_proc]:
                    if p:
                        try:
                            p.terminate()
                            p.wait(timeout=2) 
                        except subprocess.TimeoutExpired:
                            p.kill()
                ffmpeg_proc = None            
                recording = False
                stop_blink()
            if recording and ffmpeg_proc:
                try:
                    ffmpeg_proc.stdin.write(memoryview(frame))
                except Exception as e:
                    print("⚠️ Error escribiendo a ffmpeg_proc stdin:", e)
            if hdmiState:
                try:
                    if proc_hdmi is None or (hasattr(proc_hdmi, 'poll') and proc_hdmi.poll() is not None):
                        # try to restart cleanly while holding lock
                        try:
                            hdmi_write_lock.acquire()
                            hdmi_paused.set()
                            if proc_hdmi:
                                try:
                                    if proc_hdmi.stdin:
                                        try:
                                            proc_hdmi.stdin.close()
                                        except Exception:
                                            pass
                                    proc_hdmi.terminate()
                                    proc_hdmi.wait(timeout=1)
                                except Exception:
                                    try:
                                        proc_hdmi.kill()
                                    except Exception:
                                        pass
                                proc_hdmi = None
                        except Exception:
                            proc_hdmi = None

                        ensure_xdg_runtime_dir()
                        with open("hdmi_log.txt", "ab") as f:
                            try:
                                proc_hdmi = subprocess.Popen(cmd_hdmi, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT)
                                print("🔁 HDMI ffmpeg reiniciado.")
                                time.sleep(0.12)
                            except Exception as e:
                                print("❌ Falló reiniciar HDMI ffmpeg:", e)
                                proc_hdmi = None
                    # Try to write to HDMI with brief lock
                    try:
                        if hdmi_write_lock.acquire(timeout=0.02):
                            try:
                                if proc_hdmi and not hdmi_paused.is_set() and proc_hdmi.stdin:
                                    try:
                                        proc_hdmi.stdin.write(memoryview(frame))
                                    except BrokenPipeError:
                                        print("⚠️ BrokenPipe al escribir HDMI (rec), reiniciando proc_hdmi")
                                        try:
                                            proc_hdmi.terminate()
                                        except Exception:
                                            pass
                                        proc_hdmi = None
                                    except Exception as e:
                                        print("⚠️ Error HDMI write (rec):", e)
                                        try:
                                            proc_hdmi.terminate()
                                        except Exception:
                                            pass
                                        proc_hdmi = None
                            finally:
                                hdmi_write_lock.release()
                    except Exception:
                        pass
                except Exception as e:
                    print("⚠️ Error HDMI write/restart:", e)
                    try:
                        if proc_hdmi:
                            proc_hdmi.terminate()
                    except Exception:
                        pass
                    proc_hdmi = None
            latest_frame = memoryview(frame)
    except Exception as e:
        stop_error = True
        print("❌ Error en hilo video:", e)
        PrintImageDisplay("img/error_stream.png")
        stop_blink()
        changeRunningCamera(False)
    finally:
        # Limpiar proceso de audio (desactivado)
        # if proc_audio_hdmi:
        #     try:
        #         proc_audio_hdmi.terminate()
        #         proc_audio_hdmi.wait(timeout=1)
        #     except Exception:
        #         try:
        #             proc_audio_hdmi.kill()
        #         except Exception:
        #             pass
        #     proc_audio_hdmi = None
        
        video_thread_running.clear()
        picam2.close()
        cv2.destroyAllWindows()
        print("🔴 Hilo de captura de rec parado.")
        PrintImageDisplay("img/error_stream.png")
        stop_blink()
        changeRunningCamera(False)

last_restart_time = 0
debounce_delay = 1.0  # segundos
def restart_rec_thread():
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

    print("▶️ Iniciando nuevos hilos de rec...")
    video_thread_running.set()
    video_thread = threading.Thread(target=video_stream_thread, daemon=True)
    video_thread.start()
    preview_thread = Thread(target=lcd_preview_thread, daemon=True)
    preview_thread.start()


def request_hdmi_restart():
    """Request the recording thread to restart its HDMI ffmpeg process."""
    try:
        hdmi_restart_event.set()
        return True
    except Exception:
        return False

def capture_rec():
    global recTake, last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        print("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now
    
    recTake = not recTake

def apply_config_to_active_camera_rec(todo=False):
    global picam2, CONFIG
    if picam2 is not None:
        # Guardar valores críticos actuales
        old_resolution = str(CONFIG.get("resolution", ""))
        old_fps = str(CONFIG.get("fps", ""))
        old_bitrate = str(CONFIG.get("bitrate", ""))

        # Aplicar configuración a la cámara activa
        aplicar_camara_config(picam2, todo)
        CONFIG = load_config()

        # Valores nuevos tras aplicar configuración
        new_resolution = str(CONFIG.get("resolution", ""))
        new_fps = str(CONFIG.get("fps", ""))
        new_bitrate = str(CONFIG.get("bitrate", ""))

        # Si hay cambios en resolución, fps o bitrate, reiniciar hilo de grabación
        if todo or (old_resolution != new_resolution) or (old_fps != new_fps) or (old_bitrate != new_bitrate):
            print("🔁 Cambios críticos en config detectados; reiniciando hilo de grabación.")
            try:
                restart_rec_thread()
            except Exception as e:
                print("❌ Error reiniciando hilo rec:", e)

ESTIMADO_MB_POR_MINUTO = 370
minutos_restantes = 0

def minutos_disponibles(path="/home/pi/Unicam/videos"):
    # Obtiene espacio libre en MB
    total, usado, libre = shutil.disk_usage(path)
    libre_mb = libre / (1024 * 1024)
    # Calcula minutos disponibles
    return int(libre_mb / ESTIMADO_MB_POR_MINUTO)

def set_low_priority():
    p = psutil.Process(os.getpid())
    try:
        p.nice(10)  # mayor número = menos prioridad (Linux)
    except Exception:
        pass

def lcd_preview_thread(): 
    set_low_priority()
    global latest_frame, CONFIG, minutos_restantes
    start_time = datetime.now()
    recording = False
    last_info_update = 0
    minutos_restantes = minutos_disponibles()
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
                
            elapsed_seconds = 0
                
            if recording and not recTake:
                recording = False
                
            if not recording and recTake:
                start_time = datetime.now()
                recording = True
                
            if recording and recTake:
                elapsed_seconds = (datetime.now() - start_time).seconds
                
            if time.time() - last_info_update > 60:
                minutos_restantes = minutos_disponibles()
                last_info_update = time.time()
                
            # Actualizar CONFIG cada X segundos
            Alevel = 100
            mute = True
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
                    
                if getMute():
                    Alevel = 100
                    mute = True
                else:
                    Alevel = 44#get_audio_level()
                    mute = False
                    
            zm = round(zoom_state['factor'], 2)
            
            lcd_preview.show(memoryview(latest_frame), width=WIDTH, height=HEIGHT, fps=TARGET_FPS, elapsed_seconds=elapsed_seconds, af_mode=ae_mode, wb_mode=wb_mode, zm=zm, recording=recTake, stream_active=False, mode="REC", Alevel=Alevel, mute=mute, bitrate=f"{minutos_restantes}M")
            
            time.sleep(0.01)
    except Exception as e:
        print("Error en lcd_preview_thread_fast:", e)