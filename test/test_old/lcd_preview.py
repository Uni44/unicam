import time, os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math

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

    def show(self, frame_yuv420, width=1920, height=1080, fps=30, recording=False, elapsed_seconds=0, af_mode="AUTO", wb_mode="AUTO", zm=1, recording=False, stream_active=False, mode="REC"):
        # Convertir a RGB
        if frame_yuv420.ndim == 1:
            frame_yuv420 = frame_yuv420.reshape((height * 3 // 2, width))
        rgb = cv2.cvtColor(frame_yuv420, cv2.COLOR_YUV2RGB_I420)
        img = Image.fromarray(rgb)

        # Redimensionar a LCD
        img_resized = img.resize((480, 320), Image.LANCZOS)

        # Dibujar overlays
        draw = ImageDraw.Draw(img_resized)
        self.draw_rule_of_thirds(draw, img_resized)
        self.draw_center_info(draw, img_resized, resolution=(width,height), fps=fps)
        self.draw_bottom_status(draw, af_mode=af_mode, wb_mode=wb_mode, zm=zm)
        self.draw_recording_indicator(draw, recording=recording, stream_active=stream_active, mode=mode, frame_count=self.frame_counter, elapsed_seconds=elapsed_seconds)
        self.draw_exposure_bar(draw, img_resized)

        # Guardar o mostrar en LCD
        if self.test_mode:
            self.frame_counter += 1
            if True:#test
                ts = int(time.time())
                os.makedirs("preview_out", exist_ok=True)
                img_resized.save(f"preview_out/frame_{ts}.jpg")
        else:
            self.disp.show_image(img_resized)

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
        
    def draw_center_info(self, draw, img, resolution=(1920,1080), fps=30):
        w, h = img.size
        aspect = f"{resolution[0]//math.gcd(resolution[0], resolution[1])}:{resolution[1]//math.gcd(resolution[0], resolution[1])}"
        text = f"{aspect} | {resolution[0]}x{resolution[1]} | {fps} FPS"
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

        status_text = f"AF: {af_mode}    WB: {wb_mode}                                                                                                                                                                           ZM: {zm}x"

        bbox = draw.textbbox((0,0), status_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = 10
        y = h - text_height - 10

        draw_text_outline(draw, (x, y), status_text, font)

    def draw_exposure_bar(self, draw, img):
        w, h = img.size
        gray = np.array(img.convert("L"))
        lum_avg = gray.mean()
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