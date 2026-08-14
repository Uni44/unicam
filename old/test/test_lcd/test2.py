import spidev
import RPi.GPIO as GPIO
import time

T_CS = 7
T_IRQ = 17

spi = spidev.SpiDev()
spi.open(0, 1)       # Bus 0, CE1
spi.max_speed_hz = 2000000

GPIO.setmode(GPIO.BCM)
GPIO.setup(T_IRQ, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def read_touch():
    if GPIO.input(T_IRQ) == 0:
        # Leer X
        x = spi.xfer2([0x90, 0, 0])
        x_data = ((x[1] << 8) | x[2]) >> 3

        # Leer Y
        y = spi.xfer2([0xD0, 0, 0])
        y_data = ((y[1] << 8) | y[2]) >> 3

        return x_data, y_data
    return None

while True:
    pos = read_touch()
    if pos:
        print("Touch:", pos)
    time.sleep(0.02)
