import cv2
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import time
import spidev
from gpiozero import DigitalOutputDevice, PWMOutputDevice

# --- Pines ---
DC_PIN  = 24
RST_PIN = 25
BL_PIN  = 18

# --- Resolución LCD ---
LCD_WIDTH = 320
LCD_HEIGHT = 480  # pantalla completa

# --- Mini ventana para video ---
VIDEO_WIDTH  = 320  # ajusta a gusto
VIDEO_HEIGHT = 180  # ajusta a gusto
VIDEO_X = 80         # posición X en LCD
VIDEO_Y = 70        # posición Y en LCD

# --- Inicialización GPIO ---
dc  = DigitalOutputDevice(DC_PIN)
rst = DigitalOutputDevice(RST_PIN)
bl  = PWMOutputDevice(BL_PIN, frequency=1000)
bl.value = 1.0  # brillo al 100%

# --- SPI setup ---
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 62500000
spi.mode = 0b00

# --- Funciones cortas ---
def cmd(c):
    dc.off()
    spi.writebytes([c])

def data(d):
    dc.on()
    spi.writebytes([d] if isinstance(d, int) else d)

def reset():
    rst.on(); time.sleep(0.02)
    rst.off(); time.sleep(0.02)
    rst.on(); time.sleep(0.02)

# --- Init ST7796/ILI9486 ---
def init():
    reset()
    cmd(0x11); time.sleep(0.12)
    cmd(0x36); data(0x08)
    cmd(0x3A); data(0x55)  # RGB565
    cmd(0x29)
    clear_screen()  # limpiar al inicio

def set_window(x0, y0, x1, y1):
    cmd(0x2A); data([x0>>8, x0&0xFF, x1>>8, x1&0xFF])
    cmd(0x2B); data([y0>>8, y0&0xFF, y1>>8, y1&0xFF])
    cmd(0x2C)

# --- Limpiar pantalla ---
def clear_screen(color=0x0000):  # negro por defecto
    buf = np.empty(LCD_WIDTH*LCD_HEIGHT*2, dtype=np.uint8)
    buf[0::2] = color >> 8
    buf[1::2] = color & 0xFF
    set_window(0, 0, LCD_WIDTH-1, LCD_HEIGHT-1)
    dc.on()
    max_chunk = 4096
    data_bytes = buf.tobytes()
    start = 0
    while start < len(data_bytes):
        end = min(start + max_chunk, len(data_bytes))
        spi.writebytes(list(data_bytes[start:end]))
        start = end

# --- Mostrar frame ---
def frame_to_rgb565(frame):
    rgb = frame[:, :, ::-1]  # BGR → RGB
    r = (rgb[...,0] & 0xF8).astype(np.uint16)
    g = (rgb[...,1] & 0xFC).astype(np.uint16)
    b = (rgb[...,2] & 0xF8).astype(np.uint16)
    return (r << 8) | (g << 3) | (b >> 3)

def show_frame(frame_pil, x=0, y=0):
    # Convertir a numpy RGB
    frame = np.array(frame_pil)
    frame565 = frame_to_rgb565(frame).flatten()
    buf = np.empty(frame565.size*2, dtype=np.uint8)
    buf[0::2] = frame565 >> 8
    buf[1::2] = frame565 & 0xFF

    h, w = frame.shape[:2]
    set_window(x, y, x + w - 1, y + h - 1)
    dc.on()

    # SPI write
    max_chunk = 4096
    start = 0
    data_bytes = buf.tobytes()
    while start < len(data_bytes):
        end = min(start + max_chunk, len(data_bytes))
        spi.writebytes(list(data_bytes[start:end]))
        start = end

# --- Crear imagen de texto ---
def crear_banner(texto, width=480, height=70, color_fondo=(0,0,0), color_texto=(255,255,255)):
    img = Image.new("RGB", (width, height), color_fondo)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), texto, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((width-w)/2, (height-h)/2), texto, font=font, fill=color_texto)
    arr = np.array(img)
    arr = np.fliplr(arr)
    return arr

# --- Test ---
init()
cmd(0x36)
data(0xA8)

# --- Video ---
video_path = "test.mp4"
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("❌ No se puede abrir el video")
    exit(1)

# --- FPS real ---
last_time = time.time()
frames = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Redimensionar al tamaño del mini video
        frame = cv2.resize(frame, (VIDEO_WIDTH, VIDEO_HEIGHT))
        show_frame(frame, VIDEO_X, VIDEO_Y)

        frames += 1
        now = time.time()
        if now - last_time >= 1.0:
            banner = crear_banner(f"FPS: {frames}")
            show_frame(banner, x=0, y=250)
            print(f"FPS LCD: {frames}")
            frames = 0
            last_time = now
finally:
    cap.release()
    print("✅ Video terminado")