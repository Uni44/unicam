import st7796
from PIL import Image, ImageOps

if __name__=='__main__':
    
    disp = st7796.st7796()
    print("st7796 LCD:", disp.width, "x", disp.height)
    disp.clear()

    # Read image from "images" sub-folder
    ImagePath = "test.jpg"
    image = Image.open(ImagePath)
    print("Open image:", ImagePath)

    print("image:", image.width, "x", image.height)
    img_resized = image.resize((426, 320), Image.LANCZOS)
    print("img_resized:", img_resized.width, "x", img_resized.height)
    img_rotated = img_resized.rotate(270, expand=True)
    print("img_rotated:", img_rotated.width, "x", img_rotated.height)
    img_expanded = ImageOps.expand(img_rotated, border=(0, 27), fill='black')
    print("img_expanded:", img_expanded.width, "x", img_expanded.height)
    img_transposed = img_expanded.transpose(Image.FLIP_TOP_BOTTOM)
    print("img_transposed:", img_transposed.width, "x", img_transposed.height)
    print("of type:", type(img_transposed))
    
    disp.show_image(img_transposed) #show on LCD