import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

class InternalCineMenu:
    def __init__(self):
        self.selected = 0
        # Opciones con valores simulados para que parezca real
        self.options = [
            ("RECORD", "ProRes 422"),
            ("RESOLUTION", "4K DCI"),
            ("FPS", "24 fps"),
            ("SHUTTER", "180°"),
            ("ISO", "800"),
            ("WHITE BALANCE", "5600K"),
            ("MONITOR", "LUT On"),
            ("EXIT", "Return to Live")
        ]
        self.ACCENT = (255, 204, 21) # Amarillo Pro
        self.BG_COLOR = (12, 12, 12) # Negro casi puro

    def draw_menu(self, w, h):
        # Crear lienzo negro sólido
        img = Image.new("RGB", (w, h), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # --- 1. Header (Encabezado) ---
        header_h = int(h * 0.12)
        draw.rectangle([0, 0, w, header_h], fill=(25, 25, 25))
        
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_title = ImageFont.truetype(font_path, int(header_h * 0.4))
            font_label = ImageFont.truetype(font_path, int(h * 0.04))
            font_value = ImageFont.truetype(font_path, int(h * 0.03))
        except:
            font_title = font_label = font_value = ImageFont.load_default()

        draw.text((30, header_h // 3), "CAMERA SETTINGS", font=font_title, fill=self.ACCENT)

        # --- 2. Grid de Botones (2 columnas) ---
        margin = 40
        gap = 20
        cols = 2
        rows = 4
        
        btn_w = (w - (margin * 2) - gap) // cols
        btn_h = (h - header_h - (margin * 2) - (gap * (rows-1))) // rows

        for i, (label, value) in enumerate(self.options):
            col = i % cols
            row = i // cols
            
            x0 = margin + col * (btn_w + gap)
            y0 = header_h + margin + row * (btn_h + gap)
            x1 = x0 + btn_w
            y1 = y0 + btn_h

            # Estilo del botón
            if self.selected == i:
                # Botón seleccionado: borde amarillo y fondo gris oscuro
                draw.rectangle([x0, y0, x1, y1], fill=(40, 40, 40), outline=self.ACCENT, width=3)
                label_color = self.ACCENT
            else:
                # Botón normal: fondo negro con borde fino gris
                draw.rectangle([x0, y0, x1, y1], fill=(20, 20, 20), outline=(60, 60, 60), width=1)
                label_color = (200, 200, 200)

            # Dibujar textos dentro del botón
            draw.text((x0 + 20, y0 + 15), label.upper(), font=font_label, fill=label_color)
            draw.text((x0 + 20, y1 - 40), value, font=font_value, fill=(150, 150, 150))

        # --- 3. Footer de estado (Abajo) ---
        draw.text((w - 250, h - 30), "BATT 98% | SSD 124GB", font=font_value, fill=(100, 100, 100))

        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def main():
    menu_sim = InternalCineMenu()
    # Definimos una resolución estándar de pantalla (ej. 800x480 o 1280x720)
    width, height = 800, 480

    print("Controles del Menú Interno:")
    print("[W, A, S, D] Navegar | [Q] Salir")

    while True:
        # Generamos el menú directamente sobre el fondo negro
        output = menu_sim.draw_menu(width, height)

        cv2.imshow("Cinema Dashboard Simulator", output)

        key = cv2.waitKey(0) & 0xFF # waitKey(0) para esperar pulsación
        
        # Lógica de navegación en cuadrícula (grid)
        if key == ord('w') and menu_sim.selected >= 2:
            menu_sim.selected -= 2
        elif key == ord('s') and menu_sim.selected < len(menu_sim.options) - 2:
            menu_sim.selected += 2
        elif key == ord('a') and menu_sim.selected % 2 != 0:
            menu_sim.selected -= 1
        elif key == ord('d') and menu_sim.selected % 2 == 0:
            menu_sim.selected += 1
        elif key == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()