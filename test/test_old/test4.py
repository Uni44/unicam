import RPi.GPIO as GPIO
import time

led_pin = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(led_pin, GPIO.OUT)

# Encender
GPIO.output(led_pin, GPIO.HIGH)
time.sleep(2)

# Apagar
GPIO.output(led_pin, GPIO.LOW)
time.sleep(2)

GPIO.cleanup()