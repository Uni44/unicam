from __future__ import annotations

import importlib
import json
import logging
import threading
import time
import urllib.request

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from autofocus import SmoothContinuousAF
except Exception:  # pragma: no cover - entorno sin OpenCV o autofoco disponible
    SmoothContinuousAF = None

try:
    from gpiozero import LED as GPIOLED, Button as GPIOButton
    from gpiozero.pins.lgpio import LGPIOFactory
    GPIO_AVAILABLE = True
except Exception:
    GPIOLED = None
    GPIOButton = None
    LGPIOFactory = None
    GPIO_AVAILABLE = False

try:
    from camera_config import CONFIG, changeRunningCamera, getRunningCamera
except Exception:
    CONFIG = {}
    _local_camera_running = False

    def changeRunningCamera(estado):
        global _local_camera_running
        _local_camera_running = bool(estado)

    def getRunningCamera():
        return _local_camera_running

try:
    from focuser import Focuser
except Exception:  # pragma: no cover - entorno sin driver I2C
    Focuser = None

# Configuración futura para 8 botones y 4 LEDs.
BUTTON_PINS = {
    "btn1": 26,
    "btn2": 19,
    "btn3": 13,
    "btn4": 6,
    "btn5": 5,
    "btn6": 22,
    "btn7": 27,
    "btn8": 17,
}

LED_PINS = {
    "rec": 21,
    "power": 20,
    "autofocus": 16,
    "extra_speed_focus": 12,
}

# Mapeo de acciones por botón para preparar la actualización futura.
BUTTON_ACTIONS = {
    "btn1": "zoom_in",
    "btn2": "speed_zoom",
    "btn3": "zoom_out",
    "btn4": "focus_in",
    "btn5": "autofocus",
    "btn6": "focus_out",
    "btn7": "start",
    "btn8": "stop",
}

factory = None
buttons = {}
leds = {}
# Protege OPTICS_STATE y toda escritura al focuser (I2C) para que el loop de
# zoom/focus, las requests que llegan desde la web y el motor de autofoco no
# se pisen leyendo/escribiendo el mismo estado al mismo tiempo. Eso era lo
# que generaba pasos inconsistentes / movimiento "adelante-atrás".
optics_lock = threading.Lock()
blinking = False
BLINK_LED_NAME = "rec"
FOCUS_MODE = "autofocus"
ZOOM_SPEED_MODE = "fast"
zooming_in = False
zooming_out = False
focus_moving = False
focus_direction = None
zoom_thread = None
focus_thread = None
BUTTON_ACTIVE_STATE = {}
BUTTON_DEBOUNCE_SECONDS = 0.15

PHYSICAL_ZOOM_MAX = 3.5
DIGITAL_ZOOM_MAX = 2.5
TOTAL_ZOOM_MAX = 6.0
FOCUS_STEP = 0.05
FOCUS_INTERVAL = 0.08  # solo se usa si no hay focuser real conectado (modo simulado)
FOCUSER_BUS = 1
focuser = None
autofocus_engine = None
autofocus_thread = None
OPT_ZOOM = getattr(Focuser, "OPT_ZOOM", 0x1002) if Focuser is not None else 0x1002
OPT_FOCUS = getattr(Focuser, "OPT_FOCUS", 0x1001) if Focuser is not None else 0x1001

# Estado centralizado de óptica para overlay/GPIO/futuro hardware real.
OPTICS_STATE = {
    "zoom": 1.0,
    "focus": "AF-C",
    "focus_mode": "AF-C",
    "zoom_mode": "optical",
    "optical_zoom": 1.0,
    "focus_position": 0.0,
}


def _log(message):
    print(f"[gpio_control] {message}")


def _sleep_interruptible(total_seconds, keep_going_fn, chunk=0.02):
    """Duerme total_seconds pero en pedacitos, chequeando keep_going_fn() entre
    medio. Así, si soltás el botón a mitad del intervalo, el loop lo nota casi
    al instante en vez de terminar de dormir el intervalo entero antes de parar."""
    remaining = total_seconds
    while remaining > 0 and keep_going_fn():
        step = min(chunk, remaining)
        time.sleep(step)
        remaining -= step


def get_optics_state():
    """Devuelve el estado compartido de zoom y foco."""
    return OPTICS_STATE


def set_optics_state(**updates):
    """Actualiza el estado compartido de óptica."""
    if "focus" in updates and updates["focus"] is not None:
        updates.setdefault("focus_mode", updates["focus"])
    if "focus_mode" in updates and updates["focus_mode"] is not None:
        updates.setdefault("focus", updates["focus_mode"])
    if "zoom" in updates and updates["zoom"] is not None:
        try:
            zoom_value = float(updates["zoom"])
        except (TypeError, ValueError):
            zoom_value = float(OPTICS_STATE.get("zoom", 1.0))
        updates["zoom_mode"] = "digital" if zoom_value > PHYSICAL_ZOOM_MAX else "optical"
        updates.setdefault("optical_zoom", zoom_value if zoom_value <= PHYSICAL_ZOOM_MAX else PHYSICAL_ZOOM_MAX)
    OPTICS_STATE.update(updates)
    if "focus" in OPTICS_STATE:
        OPTICS_STATE["focus"] = str(OPTICS_STATE["focus"])
    if "focus_mode" in OPTICS_STATE:
        OPTICS_STATE["focus_mode"] = str(OPTICS_STATE["focus_mode"])
    return OPTICS_STATE


def _update_speed_led():
    # En hardware con lógica invertida, considerar el LED como indicativo de velocidad normal
    set_led("extra_speed_focus", ZOOM_SPEED_MODE == "slow")


def set_zoom_speed(mode):
    global ZOOM_SPEED_MODE
    if mode not in {"slow", "fast"}:
        return False
    ZOOM_SPEED_MODE = mode
    _update_speed_led()
    _log(f"Modo zoom: {ZOOM_SPEED_MODE}")
    return True


def toggle_zoom_speed():
    return set_zoom_speed("fast" if ZOOM_SPEED_MODE == "slow" else "slow")


def get_zoom_step():
    # Antes 0.2/0.1. Con la escritura I2C duplicada ya arreglada, el costo
    # por paso (waitingForFree + roundtrip I2C) es fijo sin importar cuánto
    # te muevas en cada uno -> pasos más grandes cubren la misma distancia
    # total con menos pasos, o sea menos overhead acumulado = más rápido.
    # track_zoom recalcula el foco predicho en cada paso sea grande o chico,
    # así que esto no debería empeorar el seguimiento de foco si la tabla
    # está bien calibrada (probalo después de recalibrar, no antes).
    return 0.3 if ZOOM_SPEED_MODE == "fast" else 0.1


def get_zoom_interval():
    return 0.08 if ZOOM_SPEED_MODE == "fast" else 0.15


def _apply_zoom_to_active_cameras():
    try:
        from camera_config import apply_digital_zoom_to_active_cameras
        apply_digital_zoom_to_active_cameras()
    except Exception:
        pass


def ensure_focuser_ready():
    global focuser
    if focuser is not None:
        return focuser
    if Focuser is None:
        return None

    for bus in (FOCUSER_BUS, 0, 1):
        try:
            focuser = Focuser(bus)
            _log(f"Focuser inicializado en bus {bus}")
            return focuser
        except Exception as exc:
            _log(f"No se pudo abrir el focuser en bus {bus}: {exc}")
    return None


def _move_physical_zoom(direction):
    ensure_focuser_ready()

    with optics_lock:
        current_total_zoom = float(OPTICS_STATE.get("zoom", OPTICS_STATE.get("optical_zoom", 1.0)))
        current_optical_zoom = float(OPTICS_STATE.get("optical_zoom", min(current_total_zoom, PHYSICAL_ZOOM_MAX)))

        if direction == "in":
            if current_total_zoom < PHYSICAL_ZOOM_MAX:
                target_optical_zoom = round(min(PHYSICAL_ZOOM_MAX, current_optical_zoom + get_zoom_step()), 1)
                target_zoom = target_optical_zoom
            else:
                target_zoom = round(min(TOTAL_ZOOM_MAX, current_total_zoom + get_zoom_step()), 1)
                target_optical_zoom = PHYSICAL_ZOOM_MAX
        elif direction == "out":
            if current_total_zoom <= PHYSICAL_ZOOM_MAX:
                target_zoom = round(max(1.0, current_total_zoom - get_zoom_step()), 1)
                target_optical_zoom = target_zoom
            else:
                target_zoom = round(max(PHYSICAL_ZOOM_MAX, current_total_zoom - get_zoom_step()), 1)
                target_optical_zoom = PHYSICAL_ZOOM_MAX
        else:
            return None

        if target_zoom <= PHYSICAL_ZOOM_MAX and focuser is not None:
            try:
                mapped_value = int(round(3000 + (target_zoom - 1.0) * 17000 / max(1e-6, PHYSICAL_ZOOM_MAX - 1.0)))
                t0 = time.monotonic()
                # flag=0: no esperamos a que el motor TERMINE de moverse, solo
                # mandamos el comando y volvemos. Eso libera el hilo (y el lock)
                # casi al instante en vez de quedar bloqueado ~300ms adentro de
                # focuser.set() sin poder reaccionar a un stop. El siguiente
                # comando igual va a esperar automáticamente a que el motor esté
                # libre (waitingForFree adentro de set()), así que no se pisan.
                focuser.set(OPT_ZOOM, mapped_value, flag=0)
                elapsed = time.monotonic() - t0
                if elapsed > 0.05:
                    _log(f"ℹ️ focuser.set(zoom) tardó {elapsed*1000:.0f}ms en devolver el control (esperando al motor anterior)")

                # Foco parfocal: sigue al zoom en vivo usando la tabla calibrada,
                # sin hill-climb (no mide nitidez, solo salta a la posición predicha).
                if autofocus_engine is not None and FOCUS_MODE == "autofocus":
                    autofocus_engine.track_zoom(mapped_value)
            except Exception as exc:
                _log(f"Error moviendo zoom físico: {exc}")

        set_optics_state(optical_zoom=target_optical_zoom, zoom=target_zoom)

    _apply_zoom_to_active_cameras()
    return target_zoom


def _zoom_loop():
    while zooming_in or zooming_out:
        direction = "in" if zooming_in else "out"
        _move_physical_zoom(direction)
        _log(f"Zoom {direction} ({ZOOM_SPEED_MODE}) -> {OPTICS_STATE.get('zoom')}")
        # Pausa corta y chequeada en pedacitos (ver _sleep_interruptible) antes
        # de considerar un próximo paso. focuser.set() con flag=0 vuelve casi
        # instantáneo, así que sin esta pausa el loop siempre alcanza a
        # comprometerse a un segundo paso antes de que llegue el aviso de que
        # soltaste el botón — un tap corto terminaba moviendo 2 en vez de 1.
        # Esta pausa también sigue haciendo su trabajo original: frenar el
        # zoom digital puro, que no tiene motor que lo frene solo.
        _sleep_interruptible(get_zoom_interval(), lambda: zooming_in or zooming_out)
    _log("Zoom detenido")


def start_zoom(direction):
    global zooming_in, zooming_out, zoom_thread, _zoom_recal_timer
    if autofocus_engine is not None:
        autofocus_engine.abort_current_search()
        autofocus_engine.suppress_drop_detection()
    if _zoom_recal_timer is not None:
        _zoom_recal_timer.cancel()
        _zoom_recal_timer = None
    if direction == "in":
        zooming_in = True
        zooming_out = False
    elif direction == "out":
        zooming_out = True
        zooming_in = False
    else:
        return
    if zoom_thread is None or not zoom_thread.is_alive():
        zoom_thread = threading.Thread(target=_zoom_loop, daemon=True)
        zoom_thread.start()
    _log(f"Iniciando zoom {direction}")

_zoom_recal_timer = None

def _trigger_af_recalibration_after_zoom(zoom_pos):
    global _zoom_recal_timer
    _zoom_recal_timer = None
    if autofocus_engine is None:
        return
    if zooming_in or zooming_out:
        return
    autofocus_engine.resume_drop_detection()
    autofocus_engine.notify_external_change(zoom_pos=zoom_pos)

def stop_zoom():
    global zooming_in, zooming_out, _zoom_recal_timer
    zooming_in = False
    zooming_out = False
    _log("Deteniendo zoom")
    if autofocus_engine is not None:
        autofocus_engine.abort_current_search()
        if _zoom_recal_timer is not None:
            _zoom_recal_timer.cancel()
        current_zoom_raw = None
        try:
            current_zoom_raw = focuser.get(OPT_ZOOM)
        except Exception:
            pass
        _zoom_recal_timer = threading.Timer(
            0.4, _trigger_af_recalibration_after_zoom, args=(current_zoom_raw,)
        )
        _zoom_recal_timer.daemon = True
        _zoom_recal_timer.start()


def _sync_focus_state_from_hardware():
    """Antes de mover el foco a mano, sincroniza OPTICS_STATE con la posición
    REAL del focuser. El autofoco (y track_zoom) mueven el lente directo por
    I2C sin pasar por set_optics_state(), así que sin esto el manual arranca
    calculando desde un valor de software desactualizado -> salto brusco."""
    if focuser is None:
        return
    try:
        raw = focuser.get(OPT_FOCUS)
        normalized = round((raw * 2.0 / 20000.0) - 1.0, 4)
        OPTICS_STATE["focus_position"] = normalized
    except Exception as exc:
        _log(f"No se pudo sincronizar focus_position desde hardware: {exc}")


def _move_physical_focus(direction):
    ensure_focuser_ready()

    with optics_lock:
        current_focus = float(OPTICS_STATE.get("focus_position", 0.0))
        if direction == "in":
            target_focus = round(min(1.0, current_focus + FOCUS_STEP), 2)
        elif direction == "out":
            target_focus = round(max(-1.0, current_focus - FOCUS_STEP), 2)
        else:
            return None

        if focuser is not None:
            try:
                mapped_value = int(round((target_focus + 1.0) * 20000 / 2.0))
                t0 = time.monotonic()
                focuser.set(OPT_FOCUS, mapped_value, flag=0)
                elapsed = time.monotonic() - t0
                if elapsed > 0.05:
                    _log(f"ℹ️ focuser.set(focus) tardó {elapsed*1000:.0f}ms en devolver el control (esperando al motor anterior)")
            except Exception as exc:
                _log(f"Error moviendo foco físico: {exc}")

        set_optics_state(
            focus_position=target_focus,
            focus="MF",
            focus_mode="manual",
        )
    return target_focus


def _focus_loop():
    while focus_moving and focus_direction:
        _move_physical_focus(focus_direction)
        _log(f"Focus {focus_direction}")
        _sleep_interruptible(FOCUS_INTERVAL, lambda: focus_moving and bool(focus_direction))
    _log("Focus detenido")


def start_focus(direction):
    global focus_moving, focus_direction, focus_thread
    _sync_focus_state_from_hardware()
    focus_moving = True
    focus_direction = direction
    if focus_thread is None or not focus_thread.is_alive():
        focus_thread = threading.Thread(target=_focus_loop, daemon=True)
        focus_thread.start()
    _log(f"Iniciando focus {direction}")


def stop_focus():
    global focus_moving, focus_direction
    focus_moving = False
    focus_direction = None
    _log("Deteniendo focus")


def _get_active_camera():
    """Encuentra el objeto picam2 activo, sea cual sea el módulo que lo esté
    usando ahora mismo (camera_config, video_stream, foto_capture,
    video_rec). Compartida entre _get_frame_for_autofocus y
    _get_focus_fom_for_autofocus para no tener la misma lógica de búsqueda
    duplicada en dos lugares (y desincronizada si un día cambia)."""
    import camera_config
    active_cam = getattr(camera_config, "picam2", None)
    candidate_modules = [
        ("video_stream", getattr(__import__("video_stream", fromlist=["picam2"]), "picam2", None)),
        ("foto_capture", getattr(__import__("foto_capture", fromlist=["picam2"]), "picam2", None)),
        ("video_rec", getattr(__import__("video_rec", fromlist=["picam2"]), "picam2", None)),
    ]
    if active_cam is None:
        for module_name, module_cam in candidate_modules:
            if module_cam is not None:
                active_cam = module_cam
                camera_config.picam2 = module_cam
                break
    return active_cam


def _get_frame_for_autofocus():
    try:
        active_cam = _get_active_camera()
        if active_cam is None:
            logger.warning("AF frame: no active camera available in shared or module state")
            return None

        frame = None
        for attr in ("capture_array", "capture_arrays"):
            method = getattr(active_cam, attr, None)
            if callable(method):
                try:
                    frame = method()
                    logger.debug("AF frame capture via %s -> %s", attr, type(frame).__name__ if frame is not None else None)
                    break
                except Exception as exc:
                    logger.debug("AF frame capture failed on %s: %s", attr, exc)
                    continue
        if frame is None:
            logger.warning("AF frame: capture returned None")
            return None
        if isinstance(frame, list):
            frame = frame[0] if frame else None
        if frame is None:
            logger.warning("AF frame: frame list was empty")
            return None
        return frame
    except Exception as exc:
        logger.warning("AF frame: unexpected exception: %s", exc)
        return None


_focus_fom_warned = False


def _get_focus_fom_for_autofocus():
    """FocusFoM leído directo del metadata del sensor (lo calcula el ISP),
    en vez de capturar el frame completo y correr Laplacian por CPU como
    hace _get_frame_for_autofocus. capture_metadata() devuelve el metadata
    del último frame YA completado -> no dispara una captura de imagen
    nueva, así que es mucho más liviano que capture_array() (que sí trae
    y convierte los píxeles enteros).

    Devuelve None si algo falla; SmoothContinuousAF cae automáticamente
    al fallback de Laplacian en ese caso (ver autofocus.py), así que este
    fallo no rompe el autofoco, solo lo vuelve más lento otra vez."""
    global _focus_fom_warned
    try:
        active_cam = _get_active_camera()
        if active_cam is None:
            return None
        method = getattr(active_cam, "capture_metadata", None)
        if not callable(method):
            if not _focus_fom_warned:
                logger.warning("AF FocusFoM: la cámara activa no tiene capture_metadata()")
                _focus_fom_warned = True
            return None
        metadata = method()
        if not metadata:
            return None
        return metadata.get("FocusFoM")
    except Exception as exc:
        if not _focus_fom_warned:
            logger.warning("AF FocusFoM: error leyendo metadata: %s", exc)
            _focus_fom_warned = True
        return None


def _set_autofocus_state(active: bool):
    global FOCUS_MODE
    if active:
        FOCUS_MODE = "autofocus"
        set_optics_state(focus="AF-C", focus_mode="autofocus")
        set_led("autofocus", False)
    else:
        FOCUS_MODE = "manual"
        _sync_focus_state_from_hardware()
        set_optics_state(focus="MF", focus_mode="manual")
        set_led("autofocus", True)


def calibrate_zoom_focus_table(zoom_steps=None, output_path=None):
    """Corré esto UNA vez (apuntando a algo fijo y nítido a la distancia
    típica de uso). Guarda un JSON permanente que el autofocus_engine
    carga solo al iniciar. Volvé a correrlo solo si cambiás de lente
    o de distancia de referencia.

    Grilla de 250 en 250 (antes 1000): predict_focus() interpola LINEAL
    entre los puntos calibrados más cercanos, así que cuanto más separados
    estén, más error acumula la predicción en el medio de cada tramo -> eso
    se nota como que el foco se corre un poco al zoomear, incluso con la
    tabla cargada y funcionando bien. Con 250 hay ~4x más puntos, o sea
    ~4x menos distancia (y error) entre calibraciones vecinas."""
    global autofocus_engine

    if autofocus_engine is None:
        _log("No se puede calibrar: el autofoco continuo no está activo")
        return None

    ensure_focuser_ready()
    zoom_steps = zoom_steps or list(range(3000, 20001, 250))
    output_path = output_path or autofocus_engine.zoom_table_path

    table = {}
    for zoom_pos in zoom_steps:
        try:
            if focuser is not None:
                focuser.set(OPT_ZOOM, zoom_pos)
            time.sleep(0.5)  # asienta el motor de zoom

            autofocus_engine.abort_current_search()
            # no_improve_limit y settle_delay más generosos que en tiempo real:
            # esto corre una sola vez, así que vale la pena tardar un poco más
            # por punto a cambio de que cada uno quede bien preciso.
            best_focus, best_score = autofocus_engine._hill_climb_search(
                search_range=autofocus_engine.search_range,
                coarse_step=autofocus_engine.step_size,
                no_improve_limit=4,
                settle_delay=0.08,
            )
            table[str(zoom_pos)] = best_focus
            _log(f"Calibración zoom={zoom_pos} -> focus={best_focus} (score={best_score:.2f})")

            with open(output_path, "w") as f:
                json.dump(table, f, indent=2)
        except Exception as exc:
            _log(f"Error calibrando zoom={zoom_pos}: {exc}")

    autofocus_engine.reload_zoom_table()
    _log(f"Calibración completa: {len(table)} puntos guardados en {output_path}")
    return table


def _force_manual_af_mode():
    """Fuerza AfMode=0 (Manual) en libcamera ANTES de arrancar
    SmoothContinuousAF. Si la cámara queda en AfMode=2 (Continuo nativo de
    libcamera), su propio algoritmo de AF le escribe al lente en cada
    frame -> pelea directo contra las escrituras I2C de nuestro motor
    propio, que quedan pisadas casi al instante. El síntoma es que el
    hill-climb "mide" pero el score nunca cambia, porque libcamera devuelve
    el lente a su propia posición antes de que lleguemos a medir."""
    try:
        active_cam = _get_active_camera()
        if active_cam is None:
            _log("⚠️ No se pudo forzar AfMode=0: sin cámara activa")
            return
        method = getattr(active_cam, "set_controls", None)
        if callable(method):
            method({"AfMode": 0})
            _log("AfMode forzado a 0 (Manual) para que SmoothContinuousAF tenga el lente sin competencia")
    except Exception as exc:
        _log(f"⚠️ No se pudo forzar AfMode=0: {exc}")


def _start_continuous_autofocus():
    global autofocus_engine, autofocus_thread
    if autofocus_engine is not None and autofocus_thread is not None and autofocus_thread.is_alive():
        return autofocus_engine

    if SmoothContinuousAF is None:
        _log("Autofoco continuo no disponible porque el módulo no pudo cargarse")
        return None

    _force_manual_af_mode()

    engine = SmoothContinuousAF(
        focuser=ensure_focuser_ready(),
        get_frame=_get_frame_for_autofocus,
        get_focus_fom=_get_focus_fom_for_autofocus,
        sample_interval=0.3,        # antes 0.5 — poll más seguido
        drop_threshold=0.15,
        sustained_checks=3,
        step_size=400,
        step_delay=0.06,            # antes 0.08
        search_range=5000,
        confirm_interval=0.15,      # confirmación de drop rápida, no espera sample_interval x3
    )
    _set_autofocus_state(True)
    autofocus_engine = engine
    autofocus_thread = threading.Thread(target=engine.run, daemon=True)
    autofocus_thread.start()
    _log("Autofoco continuo iniciado")
    return engine


def _stop_continuous_autofocus():
    global autofocus_engine, autofocus_thread
    if autofocus_engine is not None:
        autofocus_engine.stop()
    if autofocus_thread is not None:
        autofocus_thread = None
    autofocus_engine = None
    _set_autofocus_state(False)
    _log("Autofoco continuo detenido")


def ensure_gpio_ready():
    """Inicializa los objetos GPIO solo cuando sea posible, sin romper el sistema en PC/Windows."""
    global factory, buttons, leds

    if buttons or leds:
        return

    if not GPIO_AVAILABLE:
        return

    try:
        if factory is None and LGPIOFactory is not None:
            factory = LGPIOFactory()
    except Exception:
        factory = None

    for name, pin in BUTTON_PINS.items():
        try:
            buttons[name] = GPIOButton(
                pin,
                pull_up=True,
                bounce_time=BUTTON_DEBOUNCE_SECONDS,
                hold_time=0.08,
                pin_factory=factory,
            )
        except Exception:
            buttons[name] = None

    for name, pin in LED_PINS.items():
        try:
            leds[name] = GPIOLED(pin, pin_factory=factory)
        except Exception:
            leds[name] = None


def set_led(name, state):
    """Activa o desactiva un LED por nombre."""
    ensure_gpio_ready()
    led = leds.get(name)
    if led is None:
        return False

    try:
        if state:
            led.on()
        else:
            led.off()
        return True
    except Exception:
        return False


def start_blink():
    """Inicia el parpadeo de un LED de aviso."""
    global blinking
    ensure_gpio_ready()
    if blinking:
        return "Ya está parpadeando."

    blinking = True
    set_led("rec", False)
    threading.Thread(target=blink_led, daemon=True).start()
    return "LED empezó a parpadear."


def stop_blink():
    """Detiene el parpadeo de un LED de aviso."""
    global blinking
    blinking = False
    set_led("rec", False)
    return "LED terminó de parpadear."


def _get_ups_power_state():
    """Devuelve el estado real de la UPS según la corriente del sensor.

    charging: corriente positiva
    discharging: corriente negativa
    idle: sin corriente relevante
    error: no pudo leerse el sensor
    """
    try:
        from ups_driver import classify_current_state
    except Exception:
        return "error"

    try:
        import sys
        main_module = sys.modules.get("main")
        if main_module is not None:
            sensor = getattr(main_module, "sensor_ups", None)
            if sensor is not None:
                stats = sensor.get_stats()
                current_a = stats.get("current_a") if isinstance(stats, dict) else None
                if current_a is not None:
                    return classify_current_state(current_a)
    except Exception:
        pass

    try:
        import importlib
        main_module = importlib.import_module("main")
        sensor = getattr(main_module, "sensor_ups", None)
        if sensor is not None:
            stats = sensor.get_stats()
            current_a = stats.get("current_a") if isinstance(stats, dict) else None
            if current_a is not None:
                return classify_current_state(current_a)
    except Exception:
        pass

    try:
        from ups_driver import INA219
        import os
        if INA219 is not None and os.path.exists("/dev/i2c-1"):
            sensor = INA219()
            stats = sensor.get_stats()
            current_a = stats.get("current_a") if isinstance(stats, dict) else None
            if current_a is not None:
                return classify_current_state(current_a)
    except Exception:
        return "error"

    return "idle"


def update_power_led_state():
    """LED power: encendido al cargar, apagado al descargar o en reposo."""
    state = _get_ups_power_state()
    if state == "charging":
        set_led("power", False)
    elif state == "discharging":
        set_led("power", True)
    elif state in {"idle", "unknown", None}:
        set_led("power", True)
    else:
        set_led("power", True)


def set_camera_running(running):
    """Actualiza el estado de cámara y deja el LED power ligado a la UPS."""
    changeRunningCamera(bool(running))
    current = getRunningCamera()
    update_power_led_state()
    if current:
        start_blink()
    else:
        stop_blink()
        set_led("rec", False)
    _log(f"CAMERA_RUNNING = {current}")
    return current


def blink_led():
    while blinking:
        led = leds.get(BLINK_LED_NAME)
        if led is None:
            time.sleep(1)
            continue

        try:
            led.on()
            time.sleep(1)
            led.off()
            time.sleep(1)
        except Exception:
            break

    try:
        set_led("rec", False)
    except Exception:
        pass


def _trigger_mode_action():
    """Invoca la ruta de stop del servidor web para que el comportamiento sea igual al botón START del frontend."""
    try:
        request = urllib.request.Request("http://127.0.0.1:8044/start", method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status in {200, 204}
    except Exception as exc:
        _log(f"No se pudo llamar al stop web: {exc}")
        return False


def _trigger_web_stop():
    """Invoca la ruta de stop del servidor web para que el comportamiento sea igual al botón STOP del frontend."""
    try:
        request = urllib.request.Request("http://127.0.0.1:8044/stop", method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status in {200, 204}
    except Exception as exc:
        _log(f"No se pudo llamar al stop web: {exc}")
        return False


def on_press(name):
    """Handler de pulsación de botón con protección contra rebotes."""
    global FOCUS_MODE
    if BUTTON_ACTIVE_STATE.get(name, False):
        return

    BUTTON_ACTIVE_STATE[name] = True
    print(f"🔘 Se presionó {name}")
    action = BUTTON_ACTIONS.get(name, name)

    if action == "zoom_in":
        start_zoom("in")
        return

    if action == "zoom_out":
        start_zoom("out")
        return

    if action == "speed_zoom":
        toggle_zoom_speed()
        return

    if action == "focus_in":
        if FOCUS_MODE == "autofocus":
            _stop_continuous_autofocus()
        FOCUS_MODE = "manual"
        set_optics_state(focus="MF", focus_mode="manual")
        # En modo manual el LED de autofocus debe estar apagado
        set_led("autofocus", True)
        start_focus("in")
        return

    if action == "focus_out":
        if FOCUS_MODE == "autofocus":
            _stop_continuous_autofocus()
        FOCUS_MODE = "manual"
        set_optics_state(focus="MF", focus_mode="manual")
        # En modo manual el LED de autofocus debe estar apagado
        set_led("autofocus", True)
        start_focus("out")
        return

    if action == "autofocus":
        if FOCUS_MODE == "autofocus":
            stop_focus()
            _stop_continuous_autofocus()
            print("🔧 Modo manual activado")
        else:
            stop_focus()
            _stop_continuous_autofocus()
            _start_continuous_autofocus()
            print("🤖 Autofoco activado")
        return

    if action == "start":
        _trigger_mode_action()
        print("▶️ Inicio")
        return

    if action == "stop":
        _trigger_web_stop()
        print("⏹️ Stop")
        return


def on_release(name):
    """Liberación del botón con protección contra rebotes."""
    if not BUTTON_ACTIVE_STATE.get(name, False):
        return

    BUTTON_ACTIVE_STATE[name] = False
    print(f"🔼 Se soltó {name}")
    action = BUTTON_ACTIONS.get(name, name)

    if action in {"zoom_in", "zoom_out"}:
        stop_zoom()
        return

    if action in {"focus_in", "focus_out"}:
        stop_focus()
        return


def register_button_handlers():
    """Asocia los callbacks de pulsación y liberación a los botones."""
    ensure_gpio_ready()
    for name, button in buttons.items():
        if button is None:
            continue
        try:
            button.when_pressed = lambda n=name: on_press(n)
            button.when_released = lambda n=name: on_release(n)
        except Exception:
            pass


def get_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_str = f.read()
        return round(int(temp_str) / 1000.0, 1)  # °C
    except Exception:
        return None


def get_cpu_freq():
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq") as f:
            # El valor viene en kHz, lo pasamos a MHz o GHz
            freq_khz = int(f.read().strip())
            return round(freq_khz / 1000, 1)  # MHz
    except Exception:
        return None