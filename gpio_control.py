from gpiozero import LED, Button
from gpiozero.pins.lgpio import LGPIOFactory
import threading
import time
from video_stream import zoom_state, zoom_lock, restart_video_thread
from foto_capture import capture_foto
from video_rec import capture_rec
from lcd_preview import changeMonitorState, InMenu, changeMenuState, DrawMenu, getInMenuState, lcd_preview, SelecChange, ButtonClick, getMonitorState
from camera_config import CONFIG
import os

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
#buttons = {name: Button(pin, pull_up=True, pin_factory=factory) for name, pin in BUTTON_PINS.items()}

blinking = False

def start_blink():
    if True:
        return "Codigo de LED Desactivado."
    global blinking
    if not blinking:
        blinking = True
        threading.Thread(target=blink_led).start()
        return "LED empezó a parpadear."
    return "Ya está parpadeando."

def stop_blink():
    if True:
        return "Codigo de LED Desactivado."
    global blinking
    if blinking:
        blinking = False
        return "LED termino de parpadear."
    return "No está parpadeando."

def blink_led():
    while blinking:
        led.on()
        time.sleep(1)
        led.off()
        time.sleep(1)

def on_press(name):
    print(f"🔘 Se presionó {name}")
    with zoom_lock:
        if name in ('btn4'):
            if getInMenuState():
                SelecChange(-1)
                DrawMenu()
            else:
                zoom_state['direction'] = +1   # Zoom in
        elif name in ('btn2'):
            if getInMenuState():
                SelecChange(+1)
                DrawMenu()
            else:
                zoom_state['direction'] = -1   # Zoom out
        elif name in ('btn3'):
            if not getInMenuState():
                if getMonitorState():
                    changeMenuState()
                    time.sleep(0.1)
                    lcd_preview.selected = 0
                    DrawMenu("main")
                else:
                    changeMonitorState()
            else:
                 ButtonClick()
        elif name in ('btn1'):
            if CONFIG.get("modo") == "Stream":
                restart_video_thread()
            if CONFIG.get("modo") == "Foto":
                capture_foto()
            if CONFIG.get("modo") == "Grabar":
                capture_rec()

def on_release(name):
    print(f"🔼 Se soltó {name}")
    with zoom_lock:
        zoom_state['direction'] = 0

# Asignar handlers
#for name, button in buttons.items():
#    button.when_pressed = lambda n=name: on_press(n)
#    button.when_released = lambda n=name: on_release(n)

def get_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_str = f.read()
        return round(int(temp_str) / 1000.0, 1)  # °C
    except:
        return None

def get_cpu_freq():
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq") as f:
            # El valor viene en kHz, lo pasamos a MHz o GHz
            freq_khz = int(f.read().strip())
            return round(freq_khz / 1000, 1)  # MHz
    except:
        return None