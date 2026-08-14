import audioop
import logging
import math
import os
import queue
import re
import struct
import subprocess
import tempfile
import threading
import time
import unicodedata
import wave

TTS_AUDIO_PATH = "/tmp/unicam_tts.wav"

FIFO_PATH = "/tmp/talkback.pcm"
logger = logging.getLogger(__name__)
CHUNK_BYTES = 1920  # 20ms a 48000Hz, mono, 16-bit signed
SAMPLE_RATE = 48000
SILENCE = b"\x00" * CHUNK_BYTES


class TalkbackState:
    def __init__(self):
        self.holder_id = None
        self.last_audio_at = 0.0


talkback_queue = queue.Queue()
talk_state = TalkbackState()
talk_state_lock = threading.Lock()
TALK_TIMEOUT = 0.5
feeder_thread = None


def _normalize_text_for_tts(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9 .,!;:?()\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _build_fallback_tts_audio(text):
    """Fallback local y en español: sintetiza una voz simple sin depender de red."""
    cleaned = _normalize_text_for_tts(text)
    if not cleaned:
        return SILENCE

    sample_count = int(SAMPLE_RATE * 0.9)
    data = []
    for index in range(sample_count):
        position = index / max(1, sample_count)
        char_weight = sum(ord(ch) for ch in cleaned[:16]) % 11
        base_freq = 220 + char_weight * 25
        freq = base_freq + (len(cleaned) % 5) * 30
        envelope = min(1.0, max(0.05, 1.0 - abs(position - 0.5) * 1.6))
        phase = (index / SAMPLE_RATE) * freq * 2 * math.pi
        sample = math.sin(phase) * envelope * 12000
        sample *= 0.7 if (index // 180) % 2 else 1.0
        data.append(int(max(-32767, min(32767, sample))))
    return struct.pack("<%dh" % len(data), *data)


def build_tts_audio(text):
    """Intenta TTS local en español y cae a un fallback sintético si no hay herramientas."""
    cleaned = _normalize_text_for_tts(text)
    if not cleaned:
        return SILENCE

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        wav_path = handle.name

    try:
        for command in (
            ["espeak", "-v", "es", "-s", "140", "-w", wav_path, cleaned],
            ["pico2wave", "-w", wav_path, "-l", "es-ES", cleaned],
        ):
            try:
                subprocess.run(command, check=True, capture_output=True)
            except Exception:
                continue

            try:
                with wave.open(wav_path, "rb") as wav_file:
                    channels = wav_file.getnchannels()
                    sample_width = wav_file.getsampwidth()
                    frame_rate = wav_file.getframerate()
                    pcm_bytes = wav_file.readframes(wav_file.getnframes())
                if channels == 1 and sample_width == 2:
                    if frame_rate != SAMPLE_RATE:
                        pcm_bytes, _ = audioop.ratecv(
                            pcm_bytes,
                            2,
                            1,
                            frame_rate,
                            SAMPLE_RATE,
                            None,
                        )
                    return pcm_bytes
            except Exception:
                continue

        return _build_fallback_tts_audio(cleaned)
    finally:
        try:
            os.remove(wav_path)
        except Exception:
            pass


def play_tts_audio(text):
    """Encola el TTS en el canal de audio del monitor para que salga por la misma salida."""
    cleaned = (text or "").strip()
    if not cleaned:
        logger.info("TTS vacío, se omite")
        return False

    logger.info("TTS solicitado: %s", cleaned)
    start_talkback_feeder()

    chunks = build_tts_chunks(cleaned)
    if not chunks:
        logger.warning("No se pudo generar el audio TTS")
        return False

    for chunk in chunks:
        talkback_queue.put(chunk)

    logger.info("TTS encolado para el monitor: %d chunks", len(chunks))
    return True


def build_tts_chunk(text):
    """Devuelve un chunk PCM listo para el FIFO."""
    audio = build_tts_audio(text)
    if not audio:
        return SILENCE
    return audio[:CHUNK_BYTES].ljust(CHUNK_BYTES, b"\x00")


def build_tts_chunks(text, chunk_count=24):
    """Divide el audio TTS en chunks para enviarlo por el canal del intercom."""
    if not (text or "").strip():
        return [SILENCE] * max(1, chunk_count)

    audio = build_tts_audio(text)
    if not audio:
        return [SILENCE] * max(1, chunk_count)

    chunks = []
    for offset in range(0, len(audio), CHUNK_BYTES):
        chunk = audio[offset:offset + CHUNK_BYTES]
        if len(chunk) < CHUNK_BYTES:
            chunk = chunk.ljust(CHUNK_BYTES, b"\x00")
        chunks.append(chunk)

    return chunks or [SILENCE]


def ensure_fifo():
    if os.path.exists(FIFO_PATH):
        return
    if hasattr(os, "mkfifo"):
        os.mkfifo(FIFO_PATH)
        return
    try:
        open(FIFO_PATH, "wb").close()
    except Exception:
        pass


def talkback_feeder():
    """Escribe silencio o audio real a la FIFO cada 20ms con reloj monotónico."""
    ensure_fifo()
    fifo = None
    frame_duration = CHUNK_BYTES / (48000 * 2)
    next_time = time.monotonic()
    while True:
        try:
            if fifo is None:
                fifo = open(FIFO_PATH, "wb")

            try:
                chunk = talkback_queue.get_nowait()
            except queue.Empty:
                chunk = SILENCE

            if len(chunk) < CHUNK_BYTES:
                chunk = chunk.ljust(CHUNK_BYTES, b"\x00")
            elif len(chunk) > CHUNK_BYTES:
                chunk = chunk[:CHUNK_BYTES]

            fifo.write(chunk)
            fifo.flush()

            next_time += frame_duration
            sleep_time = next_time - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_time = time.monotonic()
        except BrokenPipeError:
            try:
                if fifo is not None:
                    fifo.close()
            except Exception:
                pass
            fifo = None
            time.sleep(0.05)
        except Exception:
            try:
                if fifo is not None:
                    fifo.close()
            except Exception:
                pass
            fifo = None
            time.sleep(0.05)


def start_talkback_feeder():
    global feeder_thread
    if feeder_thread and feeder_thread.is_alive():
        return feeder_thread
    feeder_thread = threading.Thread(target=talkback_feeder, daemon=True, name="talkback-feeder")
    feeder_thread.start()
    return feeder_thread


def try_acquire(client_id):
    with talk_state_lock:
        now = time.time()
        holder = talk_state.holder_id
        if holder and now - talk_state.last_audio_at > TALK_TIMEOUT:
            holder = None
        if holder is None or holder == client_id:
            talk_state.holder_id = client_id
            talk_state.last_audio_at = now
            return True
        return False


def release(client_id):
    with talk_state_lock:
        if talk_state.holder_id == client_id:
            talk_state.holder_id = None


def touch(client_id):
    with talk_state_lock:
        if talk_state.holder_id == client_id:
            talk_state.last_audio_at = time.time()
