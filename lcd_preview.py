import time, os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math
from lcd_driver import show_frame, LCD_WIDTH, LCD_HEIGHT, bl, clear_screen, get_touch, touch_read_raw
import threading

_last_touch = None
_touch_running = True

# Variables
monitorState = True
InMenu = False
lcd_preview = None

def changeMonitorState():
    global monitorState
    
    monitorState = not monitorState
    
    if monitorState:
        bl.value = 1.0
    else:
        bl.value = 0.0

def getMonitorState():
    return monitorState

def getInMenuState():
    return InMenu

def changeMenuState():
    global InMenu
    
    InMenu = not InMenu
    
    if not InMenu:
        clear = Image.new("RGB", (LCD_HEIGHT, LCD_WIDTH), (0, 0, 0,255))
        show_frame(np.array(clear))
    
# --- Variables de estado ---
current_menu = "main"
itemsMenu = []
menu_stack = []  # para volver atrás
last_restart_time = 0
debounce_delay = 0.5  # segundos

MENUS = {
    "main": ["START", "MUTE", "MONITOR", "CAMERA", "EXIT"],
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
    img_final = img_resized.transpose(Image.FLIP_LEFT_RIGHT)
    arr = np.array(img_final)
    arr = arr[..., ::-1]  # Invierte RGB → BGR
    show_frame(arr) #show on LCD

def draw_text_outline(draw, position, text, font, fill="white", outline="black"):
    x, y = position
    # dibujar contorno negro en 8 direcciones
    for dx in [-1,0,1]:
        for dy in [-1,0,1]:
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline)
    # texto principal
    draw.text((x, y), text, font=font, fill=fill)

def procesarTactil():
    global last_restart_time
    
    now = time.time()
    if now - last_restart_time < debounce_delay:
        #print("⏳ Ignorado: debounce activo.")
        return
    last_restart_time = now
    
    if not monitorState:
        changeMonitorState()
        print("MONITOR ON")
        return
        
    from camera_config import CONFIG, load_config, save_config
    from video_stream import restart_video_thread, apply_config_to_active_camera, zoom_state
    from foto_capture import capture_foto, apply_config_to_active_camera_foto
    from video_rec import capture_rec, apply_config_to_active_camera_rec
        
    x, y = _last_touch
    if not InMenu:
        if 270 <= x <= 330 and 270 <= y <= 337:
            changeMenuState()
            time.sleep(0.1)
            lcd_preview.selected = 0
            DrawMenu("main")
            print("MENU")
            return
        if 270 <= x <= 330 and 205 <= y <= 250:
            CONFIG = load_config()
            if CONFIG.get("AwbEnable"):
                CONFIG["AwbEnable"] = False
            else:
                CONFIG["AwbEnable"] = True
            save_config(CONFIG)
            apply_config_to_active_camera(True)
            apply_config_to_active_camera_foto(True)
            apply_config_to_active_camera_rec(True)
            print("WB")
            return
        if 270 <= x <= 330 and 117 <= y <= 170:
            CONFIG = load_config()
            if CONFIG.get("AeEnable"):
                CONFIG["AeEnable"] = False
            else:
                CONFIG["AeEnable"] = True
            save_config(CONFIG)
            apply_config_to_active_camera(True)
            apply_config_to_active_camera_foto(True)
            apply_config_to_active_camera_rec(True)
            print("AE")
            return
        if 0 <= x <= 60 and 270 <= y <= 337:
            zoom_state['direction'] = +1
            print("ZOOM+")
            return
        if 0 <= x <= 60 and 205 <= y <= 250:
            zoom_state['direction'] = 0
            zoom_state['factor'] = 1.0
            print("ZOOM=")
            return
        if 0 <= x <= 60 and 117 <= y <= 170:
            zoom_state['direction'] = -1
            print("ZOOM-")
            return
    else:
        if itemsMenu:
            idx = lcd_preview.hit_menu(x, y, itemsMenu)
            if idx:
                lcd_preview.selected = len(itemsMenu) - 1 - idx
                ButtonClick()

def touch_thread_loop():
    global _last_touch

    while _touch_running:
        p = touch_read_raw()
        if p:
            raw_x, raw_y = p

            x = int((raw_x / 4095) * LCD_WIDTH)
            y = int((raw_y / 4095) * LCD_HEIGHT)

            # Ajustar rotación según tu MADCTL (0xA8)
            x = LCD_WIDTH - 1 - x

            _last_touch = (x, y)
        else:
            _last_touch = None

        if _last_touch:
            #print("LCD Tactil:", _last_touch)
            procesarTactil()
        time.sleep(0.01)  # 10ms, no carga CPU

touch_thread = threading.Thread(target=touch_thread_loop, daemon=True)
touch_thread.start()

class LCDPreview:
    def __init__(self):
        self.frame_counter = 0
        self.font = ImageFont.load_default()  # Fuente PIL básica
        self.selected = None
        self.orientation = "vertical"
        self.last_time = time.time()
        self.frames = 0
        
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

        # Correcciones de orientación para tu pantalla
        arr = np.array(img)
        arr = np.fliplr(arr)   # invertir horizontal
        arr = arr[..., ::-1]  # Invierte RGB → BGR
        img_final = Image.fromarray(arr)
        show_frame(img_final)

    def hit_menu(self, x, y, itemsMenu):
        """Detecta qué botón fue presionado según coordenadas táctiles"""
        w, h = LCD_WIDTH, LCD_HEIGHT
        spacing = int(h * 0.02)
        btn_h = int((h - spacing * (len(itemsMenu) + 1)) / len(itemsMenu))
        btn_w = int(w * 0.8)
        x_center = w // 2

        for i, label in enumerate(itemsMenu):
            y0 = spacing + i * (btn_h + spacing)
            y1 = y0 + btn_h
            x0 = x_center - btn_w // 2
            x1 = x_center + btn_w // 2
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def show(self, frame, width=1920, height=1080, fps=30, elapsed_seconds=0,
         af_mode="AUTO", wb_mode="AUTO", zm=1, recording=False,
         stream_active=False, mode="REC", Alevel=0, mute=False,
         bitrate="0M"):
        if self.frame_counter <= 0:
            clear = Image.new("RGB", (LCD_HEIGHT, LCD_WIDTH), (0, 0, 0,255))
            show_frame(np.array(clear))
        VIDEO_WIDTH = 320
        VIDEO_HEIGHT = 180
        yuv = np.frombuffer(frame, dtype=np.uint8)
        yuv = yuv.reshape((height * 3 // 2, width))  # formato I420
        rgb = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)
        rgb_small = cv2.resize(rgb, (VIDEO_WIDTH, VIDEO_HEIGHT), interpolation=cv2.INTER_AREA)
        rgb_small = np.fliplr(rgb_small)
        img_resized = Image.fromarray(rgb_small)
        draw = ImageDraw.Draw(img_resized)
        self.draw_rule_of_thirds(draw, img_resized)
        arr = np.array(img_resized)
        VIDEO_X = 80
        VIDEO_Y = 70
        arr = arr[..., ::-1]  # Invierte RGB → BGR
        show_frame(arr, x=VIDEO_X, y=VIDEO_Y)

        now = time.time()
        if now - self.last_time >= 1.0:
            # Dibujar banners por separado
            # Banner superior
            banner_top = Image.new("RGB", (LCD_HEIGHT, 50), (0, 0, 0,255))
            draw_top = ImageDraw.Draw(banner_top)
            self.draw_center_info(draw_top, banner_top, resolution=(width,height), fps=fps, bitrate=bitrate)
            self.draw_recording_indicator(draw_top, recording=recording, stream_active=stream_active, mode=mode, frame_count=self.frame_counter, elapsed_seconds=elapsed_seconds)
            self.draw_exposure_bar(draw_top, banner_top, img_resized)
            banner_top = np.array(banner_top)
            banner_top = np.fliplr(banner_top)

            # Banner inferior
            banner_bottom = Image.new("RGB", (LCD_HEIGHT, 50), (0,0,0,255))
            draw_bottom = ImageDraw.Draw(banner_bottom)
            self.draw_bottom_status(draw_bottom, af_mode=af_mode, wb_mode=wb_mode, zm=zm)
            self.draw_volume_bar(draw_bottom, banner_bottom, Alevel, mute)
            banner_bottom = np.array(banner_bottom)
            banner_bottom = np.fliplr(banner_bottom)
            
            # Enviar todo al LCD
            banner_top = banner_top[..., ::-1]
            banner_bottom = banner_bottom[..., ::-1]
            show_frame(banner_top, x=0, y=0)
            show_frame(banner_bottom, x=0, y=LCD_WIDTH-50)
            
            # Enviar botones al LCD
            side_img = Image.new("RGBA", (50, LCD_WIDTH-150), (0,0,0,255))
            self.draw_side_buttons(side_img, buttons=["MENU", "WB", "AE"])
            arr = np.array(side_img)
            arr = np.fliplr(arr)
            arr = arr[..., ::-1]
            show_frame(arr, x=0, y=90)
            side_img = Image.new("RGBA", (50, LCD_WIDTH-150), (0,0,0,255))
            self.draw_side_buttons(side_img, buttons=["Z+", "Z=", "Z-"],flip=True)
            arr = np.array(side_img)
            arr = np.fliplr(arr)
            arr = arr[..., ::-1]
            show_frame(arr, x=420, y=90)

        # Contador de frames
        self.frame_counter += 1
        #self.frames += 1
        #now = time.time()
        #if now - self.last_time >= 1.0:
        #    print(f"FPS LCD: {self.frames}")
        #    self.frames = 0
        #    self.last_time = now

    def draw_side_buttons(self, base_img, buttons=[],flip=False):
        draw = ImageDraw.Draw(base_img)

        w, h = base_img.size
        margin = 0
        if flip:
            margin = -20
        btn_w = 70
        btn_h = 35
        spacing = 20

        font = self.font
        
        y = 0
        for label in buttons:
            draw.rounded_rectangle(
                [margin, y, margin + btn_w, y + btn_h],
                radius=8, fill=(20,20,20,200),
                outline=(80,80,80), width=2
            )
            if flip:
                draw.text((margin + 50, y + 8), label, fill="white", font=font)
            else:
                draw.text((margin + 10, y + 8), label, fill="white", font=font)
            y += btn_h + spacing
        return base_img

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

    def draw_exposure_bar(self, draw, img, foto):
        w, h = img.size
        #gray = np.array(img.convert("L"))
        #lum_avg = gray.mean()
        hist = foto.convert("L").histogram()
        lum_avg = sum(i * hist[i] for i in range(256)) / sum(hist)
        norm = lum_avg / 255.0
        perc = int(norm * 100)

        bar_w = 40
        bar_h = 6
        x0 = w - bar_w - 30
        y0 = 12
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

        bar_w = 35
        bar_h = 6
        x0 = w - bar_w - 50
        y0 = 30
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
        
lcd_preview = LCDPreview()