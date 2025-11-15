import time, os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math
import st7796

# Inicializar LCD
DISPLAY = st7796.st7796()
print("st7796 LCD:", DISPLAY.width, "x", DISPLAY.height)
DISPLAY.clear()

DISPLAY.command(0x36)
DISPLAY.data(0x78)          # 0x78 es landscape normal
DISPLAY.set_windows(0, 0, DISPLAY.height, DISPLAY.width, horizontal=1)
monitorState = True
InMenu = False

def changeMonitorState():
    global monitorState
    
    monitorState = not monitorState
    
    if monitorState:
        DISPLAY.bl_DutyCycle(100)
    else:
        DISPLAY.bl_DutyCycle(0)

def getMonitorState():
    return monitorState

def getInMenuState():
    return InMenu

def changeMenuState():
    global InMenu
    
    InMenu = not InMenu
    
# --- Variables de estado ---
current_menu = "main"
itemsMenu = []
menu_stack = []  # para volver atrás
last_restart_time = 0
debounce_delay = 0.5  # segundos

MENUS = {
    "main": ["START", "WB", "EM", "MUTE", "MONITOR", "CAMERA", "EXIT"],
    "camera": ["MODE", "RESTART", "SHUTDOWN", "BACK"],
    "modo": ["PICTURE", "STREAM", "REC", "BACK"],
}

def SelecChange(change):
    global last_restart_time
    now = time.time()
    if now - last_restart_time < debounce_delay:
        return
    last_restart_time = now
    
    lcd_preview.selected = (lcd_preview.selected + change) % len(itemsMenu)
    
def ButtonClick():
    global last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        print("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now
    
    from camera_config import CONFIG, load_config, save_config
    from video_stream import restart_video_thread, apply_config_to_active_camera
    from foto_capture import capture_foto, apply_config_to_active_camera_foto
    from video_rec import capture_rec, apply_config_to_active_camera_rec
    
    buttonSelected = itemsMenu[lcd_preview.selected]
    print("Button: ", buttonSelected)
    
    # --- Menú principal ---
    if current_menu == "main":
        if buttonSelected == "START":
            if CONFIG.get("modo") == "Stream":
                restart_video_thread()
            if CONFIG.get("modo") == "Foto":
                capture_foto()
            if CONFIG.get("modo") == "Grabar":
                capture_rec()
            changeMenuState()
            
        if buttonSelected == "WB":
            CONFIG = load_config()
            if CONFIG.get("whitebalance") == "auto":
                CONFIG["whitebalance"] = "manual"
            else:
                CONFIG["whitebalance"] = "auto"
            apply_config_to_active_camera()
            apply_config_to_active_camera_foto()
            apply_config_to_active_camera_rec()
            save_config(CONFIG)
            changeMenuState()
           
        if buttonSelected == "EM":
            CONFIG = load_config()
            if CONFIG.get("exposure-mode") == "auto":
                CONFIG["exposure-mode"] = "manual"
            else:
                CONFIG["exposure-mode"] = "auto"
            apply_config_to_active_camera()
            apply_config_to_active_camera_foto()
            apply_config_to_active_camera_rec()
            save_config(CONFIG)
            changeMenuState()
            
        if buttonSelected == "MUTE":
            print("MUTE")
            changeMenuState()
            
        if buttonSelected == "MONITOR":
            changeMonitorState()
            changeMenuState()
            
        if buttonSelected == "CAMERA":
            DrawMenu("camera")
            
        if buttonSelected == "EXIT":
            changeMenuState()
   
    # --- Submenú de cámara ---
    if current_menu == "camera":
        if buttonSelected == "MODE":
            DrawMenu("modo")
            
        if buttonSelected == "RESTART":
            os.system("sudo reboot")
            
        if buttonSelected == "SHUTDOWN":
            os.system("sudo poweroff")
            
        if buttonSelected == "BACK":
            DrawMenu("main")
            
    # --- Submenú de modo ---
    if current_menu == "modo":
        if buttonSelected == "PICTURE":
            CONFIG["modo"] = "Foto"
            save_config(CONFIG)
            os.system("sudo reboot")
            
        if buttonSelected == "STREAM":
            CONFIG["modo"] = "Stream"
            save_config(CONFIG)
            os.system("sudo reboot")
            
        if buttonSelected == "REC":
            CONFIG["modo"] = "Grabar"
            save_config(CONFIG)
            os.system("sudo reboot")
            
        if buttonSelected == "BACK":
            DrawMenu("main")
def change_menu(new_menu):
    global current_menu, itemsMenu
    current_menu = new_menu
    itemsMenu = MENUS[new_menu]
    img = Image.new("RGBA", (480, 320), (0, 0, 0, 255))
    lcd_preview.selected = 0
    lcd_preview.draw_menu(itemsMenu, img)

def DrawMenu(menu_name=None):
    global current_menu, itemsMenu
    if menu_name:
        current_menu = menu_name
    itemsMenu = MENUS[current_menu]
    img = Image.new("RGBA", (480, 320), (0, 0, 0, 255))
    lcd_preview.selected = min(lcd_preview.selected, len(itemsMenu) - 1)
    lcd_preview.draw_menu(itemsMenu, img)

def PrintImageDisplay(ImagePath):
    image = Image.open(ImagePath)
    img_resized = image.resize((480, 320), Image.LANCZOS)
    img_rotated = img_resized.rotate(180, expand=True)
    img_invertida = ImageOps.invert(img_rotated)
    img_final = img_invertida.transpose(Image.FLIP_LEFT_RIGHT)
    DISPLAY.show_image_fast(img_final) #show on LCD

def draw_text_outline(draw, position, text, font, fill="white", outline="black"):
    x, y = position
    # dibujar contorno negro en 8 direcciones
    for dx in [-1,0,1]:
        for dy in [-1,0,1]:
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline)
    # texto principal
    draw.text((x, y), text, font=font, fill=fill)

class LCDPreview:
    def __init__(self, disp=None, test_mode=False):
        self.test_mode = test_mode
        self.disp = disp  # si es None y test_mode=True, guarda imágenes
        self.frame_counter = 0
        self.font = ImageFont.load_default()  # Fuente PIL básica
        self.selected = None
        self.orientation = "vertical"
        
    def draw_menu(self, items, img):
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = img.size

        # Fondo translúcido con degradado sutil
        gradient = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(h):
            alpha = int(180 + 50 * (y / h))  # más oscuro abajo
            ImageDraw.Draw(gradient).line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        img.alpha_composite(gradient)

        # Layout dinámico
        spacing = int(h * 0.02)
        btn_h = int((h - spacing * (len(items) + 1)) / len(items))
        btn_w = int(w * 0.8)
        x_center = w // 2

        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(btn_h * 0.4))
        font_shadow = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(btn_h * 0.4))

        for i, label in enumerate(items):
            y0 = spacing + i * (btn_h + spacing)
            y1 = y0 + btn_h
            x0 = x_center - btn_w // 2
            x1 = x_center + btn_w // 2

            # Colores estilo “Pro UI”
            if self.selected == i:
                fill = (15, 15, 15, 220)
                outline = (250, 204, 21)
                text_color = (200, 200, 200)
            else:
                fill = (15, 15, 15, 220)
                outline = (70, 70, 70)
                text_color = (200, 200, 200)

            # Glow sutil alrededor del seleccionado
            if self.selected == i:
                glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
                gdraw = ImageDraw.Draw(glow)
                gdraw.rounded_rectangle([x0-3, y0-3, x1+3, y1+3], radius=int(btn_h * 0.2), fill=(255, 90, 20, 40))
                img.alpha_composite(glow)

            # Botón redondeado con borde fino
            draw.rounded_rectangle([x0, y0, x1, y1], radius=int(btn_h * 0.05), fill=fill, outline=outline, width=2)

            # Texto centrado con sombra
            tw, th = draw.textbbox((0, 0), label, font=font_title)[2:]
            tx = x_center - tw // 2
            ty = y0 + (btn_h - th) // 2
            draw.text((tx+1, ty+1), label, font=font_shadow, fill=(0, 0, 0, 180))
            draw.text((tx, ty), label, font=font_title, fill=text_color)

        # 🔁 Correcciones de orientación para tu pantalla
        arr = np.array(img)
        arr = np.flipud(arr)   # invertir vertical
        arr = np.fliplr(arr)   # invertir horizontal
        arr = np.fliplr(arr)   # invertir horizontal
        arr = 255 - arr        # invertir colores si tu pantalla lo necesita
        img_final = Image.fromarray(arr)

        self.disp.show_image_fast(img_final)


    def hit_test(self, x, y, img_size):
        """Detecta qué botón fue presionado según coordenadas táctiles"""
        w, h = img_size
        spacing = int(h * 0.02)
        btn_h = int((h - spacing * (len(self.items) + 1)) / len(self.items))
        btn_w = int(w * 0.8)
        x_center = w // 2

        for i, label in enumerate(self.items):
            y0 = spacing + i * (btn_h + spacing)
            y1 = y0 + btn_h
            x0 = x_center - btn_w // 2
            x1 = x_center + btn_w // 2
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def show(self, frame, width=1920, height=1080, fps=30, elapsed_seconds=0, af_mode="AUTO", wb_mode="AUTO", zm=1, recording=False, stream_active=False, mode="REC", Alevel=0, mute=False, bitrate="0M"):
        # 1️⃣ Convertir frame YUV420 → numpy sin copiar
        yuv = np.frombuffer(frame, dtype=np.uint8)
        yuv = yuv.reshape((height * 3 // 2, width))  # formato I420

        # 2️⃣ Convertir YUV420 → RGB
        rgb = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)

        # 3️⃣ Redimensionar a 320x480 para el LCD (más rápido)
        rgb_small = cv2.resize(rgb, (480, 320), interpolation=cv2.INTER_AREA)

        # 4️⃣ Convertir a imagen PIL
        img_resized = Image.fromarray(rgb_small)

        # Dibujar overlays
        draw = ImageDraw.Draw(img_resized)
        self.draw_rule_of_thirds(draw, img_resized)
        self.draw_center_info(draw, img_resized, resolution=(width,height), fps=fps, bitrate=bitrate)
        self.draw_bottom_status(draw, af_mode=af_mode, wb_mode=wb_mode, zm=zm)
        self.draw_recording_indicator(draw, recording=recording, stream_active=stream_active, mode=mode, frame_count=self.frame_counter, elapsed_seconds=elapsed_seconds)
        self.draw_exposure_bar(draw, img_resized)
        self.draw_volume_bar(draw, img_resized, Alevel, mute)

        # Guardar o mostrar en LCD
        if self.test_mode:
            self.frame_counter += 1
            if True:#test
                ts = int(time.time())
                os.makedirs("preview_out", exist_ok=True)
                img_resized.save(f"preview_out/frame_{ts}.jpg")
        else:
            self.frame_counter += 1
            arr = np.array(img_resized)
            arr = np.flipud(arr)
            arr = np.fliplr(arr)
            arr = np.fliplr(arr)  # reflejo horizontal
            arr = 255 - arr  # invertir
            img_final = Image.fromarray(arr)
            self.disp.show_image_fast(img_final)

    def draw_rule_of_thirds(self, draw, img):
        w, h = img.size
        alpha = 128  # transparencia real
        color = (255, 255, 255, alpha)

        # Crear overlay para líneas semi-transparentes
        overlay = Image.new("RGBA", img.size, (0,0,0,0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Líneas verticales
        overlay_draw.line([(w/3, 0), (w/3, h)], fill=color, width=2)
        overlay_draw.line([(2*w/3, 0), (2*w/3, h)], fill=color, width=2)
        # Líneas horizontales
        overlay_draw.line([(0, h/3), (w, h/3)], fill=color, width=2)
        overlay_draw.line([(0, 2*h/3), (w, 2*h/3)], fill=color, width=2)

        # Combinar overlay con imagen original
        img_alpha = img.convert("RGBA")
        img.paste(Image.alpha_composite(img_alpha, overlay))
        
    def draw_center_info(self, draw, img, resolution=(1920,1080), fps=30, bitrate="0M"):
        w, h = img.size
        aspect = f"{resolution[0]//math.gcd(resolution[0], resolution[1])}:{resolution[1]//math.gcd(resolution[0], resolution[1])}"
        text = f"{aspect} | {resolution[0]}x{resolution[1]} | {fps} FPS | {bitrate}"
        font = self.font

        # Medir texto
        bbox = draw.textbbox((0,0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # Posición: centrado horizontal, arriba (10 px)
        x = (w - tw)//2
        y = 10

        # Dibujar contorno negro (8 direcciones)
        outline_color = "black"
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), text, font=font, fill=outline_color)

        # Texto principal en blanco
        draw.text((x, y), text, fill="white", font=font)
        
    def draw_bottom_status(self, draw, af_mode="AUTO", wb_mode="AUTO", zm=1):
        w, h = draw.im.size
        font = self.font

        status_text = f"WB: {wb_mode}    EM: {af_mode}    ZM: {zm}x"

        bbox = draw.textbbox((0,0), status_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = 10
        y = h - text_height - 10

        draw_text_outline(draw, (x, y), status_text, font)

    def draw_exposure_bar(self, draw, img):
        w, h = img.size
        #gray = np.array(img.convert("L"))
        #lum_avg = gray.mean()
        hist = img.convert("L").histogram()
        lum_avg = sum(i * hist[i] for i in range(256)) / sum(hist)
        norm = lum_avg / 255.0
        perc = int(norm * 100)

        bar_w = 40
        bar_h = 6
        x0 = w - bar_w - 30
        y0 = 10
        x1 = x0 + int(bar_w * norm)
        y1 = y0 + bar_h

        draw.rectangle([x0, y0, x1, y1], fill="yellow")
        draw.rectangle([x1, y0, x0+bar_w, y1], fill=(50,50,50))

        text = f"{perc}%"
        font = self.font
        tw = draw.textbbox((0,0), text, font=font)[2] - draw.textbbox((0,0), text, font=font)[0]
        th = draw.textbbox((0,0), text, font=font)[3] - draw.textbbox((0,0), text, font=font)[1]

        draw_text_outline(draw, (x0 + bar_w + 5, y0 - 1), text, font)
        
    def draw_volume_bar(self, draw, img, volume_level, muted=False):
        w, h = img.size
        norm = volume_level / 100
        perc = int(norm * 100)
        
        if muted:
            norm = 100 / 100
            perc = int(100 * 100) 

        bar_w = 40
        bar_h = 6
        x0 = w - bar_w - 30
        y0 = 310
        x1 = x0 + int(bar_w * norm)
        y1 = y0 + bar_h

        if muted:
            draw.rectangle([x0, y0, x1, y1], fill="red")
        else:
            draw.rectangle([x0, y0, x1, y1], fill="blue")
            
        draw.rectangle([x1, y0, x0+bar_w, y1], fill=(50,50,50))

        if muted:
            text = f"MUTE"
            font = self.font
            tw = draw.textbbox((0,0), text, font=font)[2] - draw.textbbox((0,0), text, font=font)[0]
            th = draw.textbbox((0,0), text, font=font)[3] - draw.textbbox((0,0), text, font=font)[1]
        else:
            text = f"{perc}%"
            font = self.font
            tw = draw.textbbox((0,0), text, font=font)[2] - draw.textbbox((0,0), text, font=font)[0]
            th = draw.textbbox((0,0), text, font=font)[3] - draw.textbbox((0,0), text, font=font)[1]

        draw_text_outline(draw, (x0 + bar_w + 5, y0 - 1), text, font)

    def draw_recording_indicator(self, draw, recording=False, stream_active=False, mode="STR", frame_count=0, elapsed_seconds=0):
        w, h = draw.im.size
        margin = 10

        led_on = (frame_count // 15) % 2 == 0
        if recording or stream_active:
            led_color = (255, 0, 0, 255) if led_on else (128, 0, 0, 255)
            text_fill = "white"
        else:
            led_color = (100, 100, 100, 255)
            text_fill = "white"

        font = self.font
        mode_bbox = draw.textbbox((0,0), mode, font=font)
        mode_width = mode_bbox[2] - mode_bbox[0]
        mode_height = mode_bbox[3] - mode_bbox[1]

        led_radius = mode_height // 2
        led_x = margin
        led_y = margin + (mode_height - led_radius*2)//2
        draw.ellipse((led_x, led_y, led_x + led_radius*2, led_y + led_radius*2), fill=led_color)

        text_x = led_x + led_radius*2 + 5
        text_y = margin
        draw_text_outline(draw, (text_x, text_y), mode, font, fill=text_fill)

        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60
        seconds = elapsed_seconds % 60
        counter_text = f"{hours:02}:{minutes:02}:{seconds:02}"

        counter_x = text_x + mode_width + 10
        counter_y = margin
        draw_text_outline(draw, (counter_x, counter_y), counter_text, font, fill=text_fill)

    def draw_text(self, draw, text, position=(10, 30), color="white"):
        draw.text(position, text, fill=color, font=self.font)

    def draw_line(self, draw, start, end, color="white", width=1):
        draw.line([start, end], fill=color, width=width)
        
lcd_preview = LCDPreview(disp=DISPLAY, test_mode=False)