import time
import threading
import logging
import json
import os

import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    import cv2
except Exception:  # pragma: no cover - entorno sin OpenCV
    cv2 = None


class SmoothContinuousAF:
    def __init__(self, focuser, get_frame, get_focus_fom=None,
                 sample_interval=0.5, drop_threshold=0.15,
                 sustained_checks=3, step_size=15,
                 step_delay=0.08, search_range=800,
                 zoom_table_path=None, confirm_interval=None,
                 track_wait_threshold=None,
                 warm_start=True, warm_start_probe_range=150,
                 warm_start_improve_ratio=0.05,
                 warm_start_min_absolute_score=None):
        self.focuser = focuser
        self.get_frame = get_frame
        # Callable sin argumentos que devuelve el FocusFoM más reciente
        # (float/int) leído del metadata del sensor, o None si no está
        # disponible. Si se pasa, reemplaza a get_frame()+Laplacian como
        # fuente de nitidez: es gratis en CPU (lo calcula el ISP) y no
        # necesita traer el frame completo a userspace. Ejemplo típico con
        # picamera2, cacheado por un callback en background para que esta
        # llamada sea una simple lectura, no una captura bloqueante:
        #   self.get_focus_fom = lambda: self._last_metadata.get("FocusFoM")
        # Si es None o falla, cae automáticamente al Laplacian por CPU
        # sobre get_frame() (comportamiento anterior).
        self.get_focus_fom = get_focus_fom
        self._fom_fallback_warned = False
        # Warm-start: al arrancar (ej. cada vez que se reinicia el objeto
        # por un cambio de resolución que no tiene nada que ver con el
        # zoom/foco), en vez de asumir a ciegas que hace falta un barrido
        # completo de search_range, primero se hace un sondeo local barato
        # (warm_start_probe_range, mucho más chico) para ver si el foco ya
        # estaba razonablemente bien. Solo si el sondeo muestra una mejora
        # real (>= warm_start_improve_ratio) se escala al barrido completo.
        # Esto evita pagar 3-6s de búsqueda ciega en cada restart cuando el
        # lente ni se movió.
        self.warm_start = warm_start
        self.warm_start_probe_range = warm_start_probe_range
        self.warm_start_improve_ratio = warm_start_improve_ratio
        # Piso absoluto (en unidades de FocusFoM u otro score que uses):
        # si el score ANTES de sondear ya está por debajo de esto, no tiene
        # sentido ni sondear -- vamos directo al barrido completo. Esto es
        # necesario porque el % de mejora del sondeo local por sí solo NO
        # detecta "estoy realmente desenfocado lejos del pico": un sondeo
        # a rango chico partiendo de una zona mala puede encontrar una
        # mejora local pequeña (pocos %) sin que eso signifique que ya
        # estamos cerca del pico real -> el engine terminaba "arrastrándose"
        # de a poquito en cada reinicio en vez de buscar en serio. None
        # desactiva el piso (comportamiento solo por %). Ajustalo con tus
        # propios números: en tus logs, foco bueno ronda 24-28 de FocusFoM
        # y foco malo ronda 13-17, así que ~20 es un punto de partida para
        # probar, no un valor definitivo.
        self.warm_start_min_absolute_score = warm_start_min_absolute_score
        self.sample_interval = sample_interval
        self.drop_threshold = drop_threshold
        self.sustained_checks = sustained_checks
        self.step_size = step_size
        self.step_delay = step_delay
        self.search_range = search_range
        # Umbral (en unidades crudas del focuser) a partir del cual
        # track_zoom() espera a que el motor de foco confirme que llegó,
        # en vez de disparar y seguir. Por defecto, un salto de foco más
        # grande que un step_size normal ya alcanza para que el zoom le
        # saque ventaja si no lo esperamos.
        self.track_wait_threshold = track_wait_threshold if track_wait_threshold is not None else self.step_size
        # Intervalo para las repeticiones de confirmación de drop, separado
        # del polling normal: no tiene sentido esperar sample_interval entero
        # varias veces solo para confirmar que se perdió el foco.
        self.confirm_interval = confirm_interval if confirm_interval is not None else min(0.15, sample_interval)
        # Después de una búsqueda (search), la exposición/AGC de la cámara
        # puede tardar un rato en asentarse tras el movimiento del lente,
        # y el score de nitidez puede quedar ruidoso por 1-2 lecturas. Sin
        # esto, el loop principal compara ese ruido transitorio contra el
        # baseline recién puesto -> "drop" falso -> recalibra de nuevo ->
        # vuelve a quedar ruidoso -> se repite 2-3 veces seguidas aunque el
        # foco ya esté bien (esto es lo que generaba los barridos repetidos
        # inmediatamente después de encontrar foco).
        self.baseline_samples = 3
        self.baseline_settle_delay = 0.12
        self.post_search_cooldown = max(1.0, 2 * sample_interval)
        self._last_search_end = 0.0
        self._running = False
        self._baseline_sharpness = None
        self._force_recal = threading.Event()
        self._abort = threading.Event()
        self._pending_zoom_pos = None
        self._suppress_drop = False
        self.zoom_table_path = zoom_table_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "zoom_focus_table.json"
        )
        self.zoom_table = self._load_zoom_table()

    def _load_zoom_table(self):
        """Carga la tabla zoom->foco desde disco. Persiste entre reinicios:
        una vez calibrada, queda ahí para siempre hasta que corras la
        calibración de nuevo (ej: cambiaste de lente)."""
        try:
            if os.path.exists(self.zoom_table_path):
                with open(self.zoom_table_path) as f:
                    raw = json.load(f)
                table = sorted((int(k), int(v)) for k, v in raw.items())
                logger.info("AF tabla zoom->foco cargada: %d puntos desde %s", len(table), self.zoom_table_path)
                return table
        except Exception as exc:
            logger.warning("AF no se pudo cargar tabla zoom->foco: %s", exc)
        return []

    def reload_zoom_table(self):
        """Llamar después de correr una calibración nueva para que el engine
        la use sin reiniciar el proceso."""
        self.zoom_table = self._load_zoom_table()

    def predict_focus(self, zoom_pos):
        """Interpola linealmente entre los dos puntos calibrados más cercanos
        para estimar el foco correcto en un zoom_pos que quizás no esté
        exacto en la tabla. None si no hay tabla cargada."""
        if not self.zoom_table or zoom_pos is None:
            return None
        if zoom_pos <= self.zoom_table[0][0]:
            return self.zoom_table[0][1]
        if zoom_pos >= self.zoom_table[-1][0]:
            return self.zoom_table[-1][1]
        for (z0, f0), (z1, f1) in zip(self.zoom_table, self.zoom_table[1:]):
            if z0 <= zoom_pos <= z1:
                if z1 == z0:
                    return f0
                ratio = (zoom_pos - z0) / (z1 - z0)
                return int(round(f0 + ratio * (f1 - f0)))
        return None

    def notify_external_change(self, zoom_pos=None):
        """Llamar cuando algo externo (zoom, etc.) invalida el foco actual.
        Si se pasa zoom_pos y hay tabla calibrada, salta directo al foco
        predicho en vez de barrer a ciegas. Si no, cae al comportamiento
        anterior: hill-climb con search_range completo."""
        self._pending_zoom_pos = zoom_pos
        self._force_recal.set()

    def abort_current_search(self):
        """Corta cualquier hill-climb en curso a mitad de camino (ej: el zoom
        se volvió a mover, seguir midiendo ahora es tiempo perdido contra un
        target que ya cambió)."""
        self._abort.set()

    def track_zoom(self, zoom_pos):
        """Sigue el zoom EN VIVO moviendo el foco directo a la posición que
        predice la tabla, SIN hill-climb (no mide nitidez, no compite con el
        motor de zoom). Pensado para llamarse en cada paso del zoom loop,
        no solo cuando el zoom termina. Devuelve la posición predicha o None
        si no hay tabla para ese rango.

        Saltos chicos van fire-and-forget (flag=0) para no restarle
        velocidad al zoom. Saltos grandes esperan a que el motor de foco
        confirme que llegó (flag=1, usa el busy real del hardware) antes de
        devolver el control -> evita que el zoom le saque ventaja al foco
        en pulls grandes o rápidos, que es cuando más se nota el desenfoque."""
        predicted = self.predict_focus(zoom_pos)
        if predicted is None:
            return None
        try:
            current = self.focuser.get(self.focuser.OPT_FOCUS)
            jump = abs(predicted - current)
            flag = 1 if jump > self.track_wait_threshold else 0
            self.focuser.set(self.focuser.OPT_FOCUS, predicted, flag=flag)
        except Exception as exc:
            logger.warning("AF track_zoom error: %s", exc)
        return predicted

    def suppress_drop_detection(self):
        """Llamar mientras el zoom está activo: evita que el chequeo
        periódico de drop dispare una recalibración de más durante el
        movimiento (track_zoom ya se está ocupando de seguirlo)."""
        self._suppress_drop = True

    def resume_drop_detection(self):
        self._suppress_drop = False

    def _sharpness(self):
        """Devuelve un score de nitidez. Si hay get_focus_fom configurado,
        usa el FocusFoM que ya calculó el ISP (gratis, sin traer el frame
        completo). Si no está disponible o falla, cae al Laplacian por CPU
        sobre un frame capturado con get_frame() (comportamiento anterior).
        """
        if self.get_focus_fom is not None:
            try:
                fom = self.get_focus_fom()
                if fom is not None:
                    return float(fom)
            except Exception as exc:
                if not self._fom_fallback_warned:
                    logger.warning("AF FocusFoM falló, usando fallback Laplacian: %s", exc)
                    self._fom_fallback_warned = True
            else:
                if not self._fom_fallback_warned:
                    logger.warning("AF FocusFoM devolvió None, usando fallback Laplacian")
                    self._fom_fallback_warned = True

        return self._sharpness_laplacian(self.get_frame())

    def _sharpness_laplacian(self, frame):
        if frame is None or cv2 is None:
            return 0.0
        try:
            arr = np.asarray(frame)
            if arr.ndim == 2:
                gray = arr
            elif arr.shape[-1] == 1:
                gray = arr[..., 0]
            elif arr.shape[-1] == 4:
                gray = cv2.cvtColor(arr[..., :3], cv2.COLOR_BGR2GRAY)
            elif arr.shape[-1] == 3:
                gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            else:
                return 0.0

            return float(cv2.Laplacian(gray.astype(np.uint8), cv2.CV_64F).var())
        except Exception as exc:
            logger.warning("AF sharpness error: %s", exc)
            return 0.0

    def _move_smooth(self, target):
        current = self.focuser.get(self.focuser.OPT_FOCUS)
        distance = target - current
        steps = max(1, abs(distance) // self.step_size)
        for i in range(int(steps)):
            if self._abort.is_set() or not self._running:
                logger.info("AF _move_smooth interrumpido a mitad de camino")
                return
            progress = i / steps
            ease = 0.3 + 0.7 * (1 - abs(2 * progress - 1))
            move = int(self.step_size * ease) * (1 if distance > 0 else -1)
            current += move
            self.focuser.set(self.focuser.OPT_FOCUS, current, flag=0)
            time.sleep(self.step_delay)
        if self._abort.is_set() or not self._running:
            return
        self.focuser.set(self.focuser.OPT_FOCUS, target)

    def _move_direct(self, target):
        """Movimiento directo con confirmación de hardware (flag=1), sin el
        easing de _move_smooth. Para usar durante la búsqueda: ahí cada paso
        ya es chico (step_size/fine_step) y nadie está mirando la
        transición, así que el easing solo suma una escritura I2C de más
        por cada medición sin aportar nada. _move_smooth() sigue siendo el
        correcto para transiciones que sí se ven (salto post-tabla,
        posición final tras la búsqueda)."""
        try:
            self.focuser.set(self.focuser.OPT_FOCUS, target, flag=1)
        except Exception as exc:
            logger.warning("AF _move_direct error: %s", exc)

    def _continuous_sweep_search(self, start_pos, end_pos, max_samples=200,
                                  min_samples_for_estimate=4):
        """Barrido continuo (técnica del ejemplo CoarseAdjustment de
        Arducam): UN SOLO movimiento físico de start_pos a end_pos, sin
        frenar el motor en cada paso. Mientras el motor está en movimiento
        (focuser.isBusy()) se van sacando frames y midiendo nitidez todo el
        tiempo, en vez de pagar una escritura+espera de I2C por cada paso
        discreto. Al final, se estima a qué posición corresponde el frame
        más nítido interpolando por tiempo transcurrido (asume velocidad
        del motor razonablemente constante durante el recorrido).

        Es una ESTIMACIÓN, no una medición exacta -> pensada como fase de
        barrido grueso rápido, para después afinar con una búsqueda fina
        discreta de precisión (igual que ya hace la fase 2 de
        _hill_climb_search). Devuelve (posición_estimada, mejor_score), o
        (None, 0.0) si no se pudo estimar nada confiable.

        OJO con min_samples_for_estimate: si el movimiento físico dura
        menos que lo que tarda UNA medición de nitidez (ej. rango chico,
        o la fuente de nitidez es lenta), el barrido puede terminar con
        1 sola muestra. Con 1 sola muestra, ratio = (t_muestra - t_start)
        / total_time da SIEMPRE 1.0 (mismo timestamp en numerador y
        denominador) -> estimated_pos = end_pos SIEMPRE, sin importar
        dónde estaba el pico real. Esto no es una estimación grosera, es
        un resultado sistemáticamente sesgado hacia el extremo del rango
        que rompe cualquier búsqueda que confíe en él. Por eso, con menos
        de min_samples_for_estimate muestras, se descarta el resultado en
        vez de devolver un número que parece válido pero no lo es."""
        try:
            self._move_direct(start_pos)
        except Exception as exc:
            logger.warning("AF sweep: no se pudo ir al punto de partida: %s", exc)
            return None, 0.0

        if self._abort.is_set() or not self._running:
            return None, 0.0

        try:
            self.focuser.set(self.focuser.OPT_FOCUS, end_pos, flag=0)
        except Exception as exc:
            logger.warning("AF sweep: no se pudo iniciar el barrido: %s", exc)
            return None, 0.0

        scores = []
        timestamps = []
        t_start = time.monotonic()
        while True:
            if self._abort.is_set() or not self._running:
                logger.info("AF sweep abortado a mitad de camino")
                break
            scores.append(self._sharpness())
            timestamps.append(time.monotonic())
            try:
                if not self.focuser.isBusy():
                    break
            except Exception:
                break
            if len(scores) >= max_samples:
                logger.warning("AF sweep: llegó al máximo de muestras (%d) sin que el motor reporte fin de movimiento", max_samples)
                break

        if len(scores) < min_samples_for_estimate:
            elapsed = (timestamps[-1] - t_start) if timestamps else 0.0
            logger.warning(
                "AF sweep: solo %d muestra(s) en %.3fs (rango %s->%s) -- insuficiente "
                "para estimar posición por tiempo, probablemente cada medición de "
                "nitidez tarda más que el propio movimiento. Se descarta el sweep "
                "(revisar si get_focus_fom/get_frame está bloqueando).",
                len(scores), elapsed, start_pos, end_pos,
            )
            return None, 0.0


        if not scores:
            return start_pos, 0.0

        total_time = max(1e-6, timestamps[-1] - t_start)
        best_i = max(range(len(scores)), key=lambda i: scores[i])
        ratio = (timestamps[best_i] - t_start) / total_time
        estimated_pos = int(round(start_pos + ratio * (end_pos - start_pos)))
        logger.info(
            "AF sweep: %d muestras en %.2fs, mejor score=%.3f en pos estimada=%s",
            len(scores), total_time, scores[best_i], estimated_pos,
        )
        return estimated_pos, scores[best_i]

    def _stable_score(self, samples=None, delay=None):
        """Mide varias veces YA asentado en la posición actual y devuelve
        la mediana. Se usa para fijar el baseline después de una búsqueda:
        una sola lectura tomada justo al terminar puede caer en un
        instante en que la exposición/AGC todavía se está reacomodando
        tras el movimiento del lente, y ese valor ruidoso quedaba fijado
        como referencia -> generaba drops falsos apenas terminaba de
        buscar. Con la mediana de varias lecturas espaciadas, ese ruido
        puntual no contamina el baseline."""
        samples = samples or self.baseline_samples
        delay = self.baseline_settle_delay if delay is None else delay
        scores = []
        for i in range(samples):
            if i > 0:
                time.sleep(delay)
            scores.append(self._sharpness())
        return float(np.median(scores)) if scores else 0.0

    def _measure_at(self, pos, settle_delay=0.04):
        self._move_direct(pos)
        time.sleep(settle_delay)
        return self._sharpness()

    def _hill_climb_search(self, search_range=None, coarse_step=None,
                            fine_range=None, fine_step=None,
                            no_improve_limit=2, settle_delay=0.04,
                            use_sweep=True):
        search_range = search_range or self.search_range
        coarse_step = coarse_step or self.step_size
        # ANTES: fine_step se calculaba como coarse_step//5 pero el radio de
        # búsqueda fina usaba coarse_step directo como límite. Si
        # fine_step >= coarse_step (pasa fácil con coarse_step chico, por
        # el piso de 20), el primer paso ya se salía del rango permitido y
        # la fase fina terminaba en como máximo UNA medición por dirección,
        # sin importar no_improve_limit. Ahora fine_range es un parámetro
        # propio, independiente del step, para que la fase fina realmente
        # tenga margen para converger.
        fine_step = fine_step or max(10, coarse_step // 3)
        fine_range = fine_range or max(fine_step * (no_improve_limit + 4), coarse_step)
        self._abort.clear()

        current = self.focuser.get(self.focuser.OPT_FOCUS)
        best_focus, best_score = current, self._sharpness()
        logger.info("AF hill-climb: start focus=%s score=%.3f", current, best_score)

        if self._abort.is_set() or not self._running:
            return best_focus, best_score

        # Fase 1 (opcional): barrido continuo (un solo movimiento físico
        # cubre TODO el rango de una punta a la otra) en vez de
        # step-and-settle repetido en cada dirección -> ubica la zona del
        # pico mucho más rápido para rangos grandes. Para rangos chicos
        # (ej. el sondeo de warm-start) el movimiento físico dura tan poco
        # que ni siquiera entra una medición completa antes de terminar
        # -> ahí directamente NO tiene sentido pagar el costo de un
        # barrido físico, se salta y se va directo a la fase fina
        # (use_sweep=False), que a esa escala ya es lo bastante rápida.
        sweep_pos, sweep_score = (None, 0.0)
        if use_sweep:
            lo = max(0, current - search_range)
            hi = current + search_range
            sweep_pos, sweep_score = self._continuous_sweep_search(lo, hi)
        # OJO: sweep_score se midió con el motor EN MOVIMIENTO, y sweep_pos
        # es una posición ESTIMADA por tiempo transcurrido (asume velocidad
        # constante). Si el motor acelera/frena, esa posición puede no
        # coincidir con donde estaba el lente cuando salió el frame nítido.
        # Por eso no usamos sweep_score directo: nos movemos de verdad a
        # sweep_pos, medimos QUIETO (motor confirmado, sin blur), y esa
        # medición real es la que compite por "mejor score". Sin este paso,
        # un score inflado/mal atribuido queda de baseline imposible de
        # igualar -> el engine cree que perdió foco en cada ciclo posterior
        # y busca sin parar (esto era lo que te tenía trabado).
        #
        # Además: la estimación por tiempo puede errar por varios steps
        # (motor acelerando/frenando). Verificar UN solo punto castiga de
        # más un sweep que apuntó "cerca pero no exacto". Por eso medimos
        # una pequeña ventana [-fine_step, 0, +fine_step] alrededor del
        # punto estimado y nos quedamos con el mejor de los tres -> mucho
        # más tolerante a que el sweep haya errado por poco, sin pagar el
        # costo de un fine-search completo todavía.
        #
        # sweep_pos puede venir None si _continuous_sweep_search descartó
        # su propia estimación por falta de muestras (ver ese método) -> en
        # ese caso no hay nada que verificar, se salta directo a fase fina
        # partiendo de la posición actual real (best_focus ya la tiene).
        if sweep_pos is not None and not (self._abort.is_set() or not self._running):
            window_offsets = (0, -fine_step, fine_step)
            best_window_pos, best_window_score = sweep_pos, None
            for off in window_offsets:
                if self._abort.is_set() or not self._running:
                    break
                candidate = sweep_pos + off
                score = self._measure_at(candidate, settle_delay=settle_delay)
                if best_window_score is None or score > best_window_score:
                    best_window_score, best_window_pos = score, candidate
            logger.info(
                "AF sweep verificado: pos_estimada=%s score_barrido=%.3f mejor_real_en_ventana=%s score_real=%.3f",
                sweep_pos, sweep_score, best_window_pos, best_window_score if best_window_score is not None else -1,
            )
            if best_window_score is not None and best_window_score > best_score:
                best_score, best_focus = best_window_score, best_window_pos
                logger.info("AF sweep improved: focus=%s score=%.3f", best_focus, best_score)

        if self._abort.is_set() or not self._running:
            self._move_smooth(best_focus)
            return best_focus, best_score

        # Fase 2: paso fino solo alrededor del mejor punto encontrado -> movimiento suave, no a los saltos
        coarse_best = best_focus
        for direction in (1, -1):
            pos = coarse_best
            no_improve_count = 0
            while abs(pos - coarse_best) < fine_range and no_improve_count < no_improve_limit:
                if self._abort.is_set() or not self._running:
                    logger.info("AF hill-climb abortado (cambio externo durante la búsqueda)")
                    self._move_smooth(best_focus)
                    return best_focus, best_score
                pos += direction * fine_step
                score = self._measure_at(pos, settle_delay=settle_delay)
                if score > best_score:
                    best_score, best_focus = score, pos
                    no_improve_count = 0
                    logger.info("AF hill-climb fine improved: focus=%s score=%.3f", pos, best_score)
                else:
                    no_improve_count += 1

        self._move_smooth(best_focus)
        logger.info("AF hill-climb final: focus=%s score=%.3f", best_focus, best_score)
        return best_focus, best_score

    def run(self):
        self._running = True
        logger.info("AF loop started")
        score = self._sharpness()
        self._baseline_sharpness = score
        logger.info("AF baseline initialized to %.3f", score)

        if score > 0.0:
            try:
                skip_full_search = False
                below_floor = (
                    self.warm_start_min_absolute_score is not None
                    and score < self.warm_start_min_absolute_score
                )
                if self.warm_start and not below_floor:
                    logger.info("AF warm-start: sondeo local antes de barrido completo (rango=%s)", self.warm_start_probe_range)
                    # use_sweep=False: a este rango chico el movimiento
                    # físico dura menos que una medición de nitidez, así
                    # que el barrido continuo degenera (ver
                    # _continuous_sweep_search). Vamos directo a fase fina
                    # bidireccional, que a esta escala ya es rápida y no
                    # está sesgada hacia ningún extremo.
                    _, probe_score = self._hill_climb_search(
                        search_range=self.warm_start_probe_range, coarse_step=self.step_size,
                        fine_range=self.warm_start_probe_range, use_sweep=False,
                        no_improve_limit=2, settle_delay=0.05,
                    )
                    improve_ratio = (probe_score - score) / max(score, 1)
                    if improve_ratio < self.warm_start_improve_ratio:
                        logger.info(
                            "AF warm-start: foco ya estaba OK (mejora=%.1f%% < %.1f%%), salteando barrido completo",
                            improve_ratio * 100, self.warm_start_improve_ratio * 100,
                        )
                        self._baseline_sharpness = probe_score
                        skip_full_search = True
                    else:
                        logger.info(
                            "AF warm-start: mejora %.1f%% detectada, escalando a barrido completo",
                            improve_ratio * 100,
                        )
                elif below_floor:
                    logger.info(
                        "AF warm-start: score inicial=%.3f por debajo del piso=%.3f, "
                        "se salta el sondeo y se va directo al barrido completo",
                        score, self.warm_start_min_absolute_score,
                    )

                if not skip_full_search:
                    logger.info("AF running initial focus search on startup")
                    _, new_best = self._hill_climb_search(
                        search_range=self.search_range, coarse_step=self.step_size,
                        no_improve_limit=3, settle_delay=0.06,
                    )
                    self._baseline_sharpness = self._stable_score()
                    self._last_search_end = time.monotonic()
            except Exception as exc:
                logger.warning("AF initial search failed: %s", exc)

        while self._running:
            if self._force_recal.is_set():
                self._force_recal.clear()
                zoom_pos = self._pending_zoom_pos
                self._pending_zoom_pos = None
                predicted = self.predict_focus(zoom_pos)
                try:
                    if predicted is not None:
                        logger.info("AF salto por tabla: zoom=%s -> focus predicho=%s", zoom_pos, predicted)
                        self._move_smooth(predicted)
                        _, new_best = self._hill_climb_search(search_range=300, coarse_step=60)
                    else:
                        logger.info("AF recalibrando por cambio externo (zoom) sin tabla para zoom=%s", zoom_pos)
                        _, new_best = self._hill_climb_search(
                            search_range=self.search_range, coarse_step=self.step_size,
                            no_improve_limit=3, settle_delay=0.06,
                        )
                    self._baseline_sharpness = self._stable_score()
                    self._last_search_end = time.monotonic()
                except Exception as exc:
                    logger.warning("AF recalibración externa falló: %s", exc)
                time.sleep(self.sample_interval)
                continue

            score = self._sharpness()
            if self._suppress_drop:
                time.sleep(self.sample_interval)
                continue
            if self._baseline_sharpness is None:
                self._baseline_sharpness = score
                logger.info("AF baseline initialized to %.3f", score)
            # Cooldown: recién terminó una búsqueda, dejamos que la
            # exposición/pipeline de la cámara se asiente antes de volver
            # a chequear drops. Sin esto, un score transitorio (tomado
            # mientras la AGC todavía se está reacomodando tras mover el
            # lente) se comparaba contra el baseline recién puesto y
            # disparaba una recalibración de más, en cadena.
            if time.monotonic() - self._last_search_end < self.post_search_cooldown:
                time.sleep(self.sample_interval)
                continue
            drop = (self._baseline_sharpness - score) / max(self._baseline_sharpness, 1)
            if score <= 1.0:
                logger.warning("AF score too low: %.3f baseline=%.3f drop=%.4f", score, self._baseline_sharpness, drop)
            if drop > self.drop_threshold:
                logger.info("AF drop detected: score=%.3f baseline=%.3f drop=%.4f threshold=%.4f", score, self._baseline_sharpness, drop, self.drop_threshold)
                confirmed = 0
                for _ in range(self.sustained_checks):
                    time.sleep(self.confirm_interval)
                    new_score = self._sharpness()
                    new_drop = (self._baseline_sharpness - new_score) / max(self._baseline_sharpness, 1)
                    if new_drop > self.drop_threshold:
                        confirmed += 1
                if confirmed >= self.sustained_checks - 1:
                    try:
                        logger.info("AF recalibrating focus due to drop")
                        _, new_best = self._hill_climb_search(
                            search_range=self.search_range, coarse_step=self.step_size,
                            no_improve_limit=3,
                        )
                        self._baseline_sharpness = self._stable_score()
                        self._last_search_end = time.monotonic()
                    except Exception as exc:
                        logger.warning("AF hill-climb failed: %s", exc)
                        self._baseline_sharpness = score
            time.sleep(self.sample_interval)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self._running = False
        # abort_current_search() no es solo para el zoom: es lo único que
        # hace que un _hill_climb_search() en curso corte YA. Sin esto,
        # _running=False no se nota hasta que la búsqueda actual termina
        # sola (puede ser varios segundos), y durante ese tiempo el engine
        # sigue escribiendo al focuser mientras el usuario ya está moviendo
        # a mano -> pelea entre los dos.
        self._abort.set()