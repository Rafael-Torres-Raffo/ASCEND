import gpiod as GPIO
from hx711 import HX711
import os

# Manually specify SOC peripheral base address for Raspberry Pi 5
os.environ["SOC_BASE"] = "0xFE000000"

# Define GPIO pins
DT_PIN = 5   # Data pin (DT)
SCK_PIN = 6  # Clock pin (SCK)

# Initialize HX711
hx = HX711(DT_PIN, SCK_PIN)
hx.set_reading_format("MSB", "MSB")
hx.set_reference_unit(1)  # Calibration value (adjust this)
hx.reset()
hx.tare()  # Remove any offset

print("Tare done. Ready to weigh.")

try:
    while True:
        weight = hx.get_weight(5)  # Read 5 samples
        print(f"Weight: {weight} g")
        hx.power_down()
        hx.power_up()
except KeyboardInterrupt:
    print("Exiting...")
    GPIO.cleanup()
