import st7796
from PIL import Image, ImageOps

disp = st7796.st7796()
print("st7796 LCD:", disp.width, "x", disp.height)
disp.clear()

# Landscape
disp.command(0x36)
disp.data(0x78)          # 0x78 es landscape normal
disp.set_windows(0, 0, disp.height, disp.width, horizontal=1)


# Read image from "images" sub-folder
ImagePath = "test2.png"
image = Image.open(ImagePath)
print("Open image:", ImagePath)

img_resized = image.resize((480, 320), Image.LANCZOS)
img_rotated = img_resized.rotate(180, expand=True)
img_invertida = ImageOps.invert(img_rotated)
img_final = img_invertida.transpose(Image.FLIP_LEFT_RIGHT)
disp.show_image_fast(img_final) #show on LCD
    
# Mantener encendido
try:
    while True:
        pass
except KeyboardInterrupt:
    pass