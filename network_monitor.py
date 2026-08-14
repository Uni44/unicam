import re
import subprocess
import threading
import time
import os

_PING_TIME_RE = re.compile(r"time[=<]([\d.]+)\s*ms", re.IGNORECASE)


class NetworkMonitor:
    """Chequea la conexión en background y expone un estado cacheado que
    el HUD puede leer sin bloquear nunca el loop de render.

    Uso:
        monitor = NetworkMonitor(get_config=self._runtime_config,
                                  extract_host=self._extract_host,
                                  classify_kind=self._classify_network_kind,
                                  wifi_status_fn=get_wifi_device_status)
        monitor.start()
        ...
        state = monitor.get_state()   # no bloquea, siempre instantáneo
    """

    def __init__(self, get_config, extract_host, classify_kind,
                 wifi_status_fn=None, interval=4.0, ping_count=3,
                 smoothing=2):
        self._get_config = get_config
        self._extract_host = extract_host
        self._classify_kind = classify_kind
        self._wifi_status_fn = wifi_status_fn
        self.interval = interval
        self.ping_count = ping_count
        # cuántas mediciones fallidas seguidas hacen falta antes de bajar
        # la calidad a 0 (evita que un solo paquete perdido tire la barra)
        self.smoothing = smoothing

        self._lock = threading.Lock()
        self._state = {"quality": 0, "connected": False, "connection": "--", "kind": "OFFLINE"}
        self._consecutive_failures = 0
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def get_state(self):
        """Lectura no bloqueante — es lo único que debería llamar el HUD."""
        with self._lock:
            return dict(self._state)

    # -- internals -----------------------------------------------------

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                new_state = self._measure()
                self._apply_with_smoothing(new_state)
            except Exception:
                pass
            self._stop_event.wait(self.interval)

    def _apply_with_smoothing(self, new_state):
        with self._lock:
            if new_state["connected"]:
                self._consecutive_failures = 0
                self._state = new_state
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.smoothing:
                    self._state = new_state
                # si todavía no acumulamos suficientes fallos, mantenemos
                # el último estado bueno conocido (evita parpadeo)

    def _measure(self):
        cfg = self._get_config()
        host = self._extract_host(cfg.get("IPDestinoSRT") or cfg.get("IPDestino") or "")

        if callable(self._wifi_status_fn):
            try:
                state, connection = self._wifi_status_fn()
                if state == "connected":
                    # Wifi "conectado" no es lo mismo que "buena señal": si
                    # tenés el host, igual medimos RTT real hacia él.
                    if host:
                        rtt = self._ping_rtt(host)
                        return {
                            "quality": self._rtt_to_quality(rtt),
                            "connected": rtt is not None,
                            "connection": connection or "WiFi",
                            "kind": "WIFI",
                        }
                    return {"quality": 5, "connected": True, "connection": connection or "WiFi", "kind": "WIFI"}
                if state:
                    return {"quality": 2, "connected": False, "connection": connection or "WiFi", "kind": "WIFI"}
            except Exception:
                pass

        if not host:
            return {"quality": 0, "connected": False, "connection": "--", "kind": "OFFLINE"}

        rtt = self._ping_rtt(host)
        if rtt is not None:
            kind = self._classify_kind(host)
            return {"quality": self._rtt_to_quality(rtt), "connected": True, "connection": host, "kind": kind}

        return {"quality": 0, "connected": False, "connection": host, "kind": "OFFLINE"}

    def _ping_rtt(self, host):
        """Manda varios pings y devuelve el RTT promedio en ms, o None si
        no hubo ni una respuesta. Correr esto en background es lo que
        permite usar varios pings sin trabar nada."""
        count_flag = "-n" if os.name == "nt" else "-c"
        wait_flag = "-w" if os.name == "nt" else "-W"
        wait_val = "1000" if os.name == "nt" else "1"
        # Mantener el timeout de subprocess lo más corto posible para que un
        # fallo puntual no se acumule y no bloquee el render o la cámara.
        timeout_s = max(1.5, min(2.5, self.ping_count * 0.75))

        cmd = ["ping", count_flag, str(self.ping_count), wait_flag, wait_val, host]
        try:
            completed = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=timeout_s, text=True,
            )
        except Exception:
            return None

        if completed.returncode != 0:
            return None

        times = [float(m) for m in _PING_TIME_RE.findall(completed.stdout)]
        if not times:
            return None
        return sum(times) / len(times)

    @staticmethod
    def _rtt_to_quality(rtt_ms):
        if rtt_ms is None:
            return 0
        if rtt_ms < 50:
            return 5
        if rtt_ms < 100:
            return 4
        if rtt_ms < 200:
            return 3
        if rtt_ms < 400:
            return 2
        if rtt_ms < 800:
            return 1
        return 0