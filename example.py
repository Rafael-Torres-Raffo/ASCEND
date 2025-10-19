import time
from hx711 import HX711

DT_PIN = 5   # Change to your GPIO pin
CLK_PIN = 6  # Change to your GPIO pin

hx = HX711(DT_PIN, CLK_PIN)

print("Taring... Remove any weight from the scale.")
hx.tare()
print("Tare complete.")

try:
    while True:
        weight = hx.read_weight(reference_unit=10)  # Adjust this value based on calibration
        print(f"Weight: {weight:.2f} g")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Exiting...")
    hx.cleanup()
