import time
from PIL import Image
from lcd_preview import LCDPreview

test_image_path = "test2.png"  # Imagen de fondo
fps = 30
recording = True

# Inicializar preview en modo test (genera JPG en preview_out)
lcd = LCDPreview(test_mode=True)

# Cargar imagen de fondo
bg = Image.open(test_image_path)
bg = bg.convert("RGB")  # asegurar modo RGB
bg = bg.resize((1920, 1080))  # tamaño simulado 1080p

start_time = time.time()

for frame_number in range(90):  # simula 3 segundos a 30fps
    # Convertir PIL Image a numpy array tipo YUV420 (simulación)
    import numpy as np
    import cv2
    rgb = np.array(bg)
    frame_yuv420 = cv2.cvtColor(rgb, cv2.COLOR_RGB2YUV_I420)

    elapsed_seconds = int(time.time() - start_time)

    # Medir tiempo por frame
    t0 = time.time()
    lcd.show(frame_yuv420=frame_yuv420, fps=fps, recording=recording, elapsed_seconds=elapsed_seconds)
    t1 = time.time()

    frame_time = t1 - t0
    print(f"Frame {frame_number+1}: {frame_time*1000:.2f} ms")

    # Simula FPS objetivo
    sleep_time = max(0, (1/fps) - frame_time)
    time.sleep(sleep_time)