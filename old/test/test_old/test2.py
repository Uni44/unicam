from picamera2 import Picamera2
import time

def capture_max_resolution(output_file="test_hdr_max.jpg"):
    print("📸 Captura de prueba en máxima resolución con HDR y colores corregidos.")

    time.sleep(2)

    picam2 = Picamera2()

    WIDTH, HEIGHT = 4608, 2592  

    # Usar salida de still en JPEG ya procesado por el ISP
    config = picam2.create_still_configuration(
        main={"format": "BGR888", "size": (WIDTH, HEIGHT)},
        buffer_count=2
    )
    picam2.configure(config)
    
    picam2.set_controls({
        "AwbEnable": True,        # auto white balance
        "AeEnable": True,         # auto exposure
        "NoiseReductionMode": 2,
        "HdrMode": 1              # HDR (si está soportado)
    })
    picam2.set_controls({"AfMode": 2, "LensPosition": 0})
    picam2.start()
    time.sleep(2)

    # Opción A: dejar que ISP genere JPEG con colores corregidos
    picam2.capture_file(output_file)

    picam2.close()
    print("✅ Foto guardada en", output_file)


# Test
if __name__ == "__main__":
    capture_max_resolution()