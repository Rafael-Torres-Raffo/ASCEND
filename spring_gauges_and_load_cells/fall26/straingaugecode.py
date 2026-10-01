import spidev
import time

# =========================================================
# AD7124 Register Addresses
# =========================================================
REG_STATUS   = 0x00
REG_ADC_CTRL = 0x01
REG_DATA     = 0x02
REG_ID       = 0x05

REG_CH0      = 0x09
REG_CH1      = 0x0A

REG_CFG0     = 0x19


# =========================================================
# SPI Setup
# =========================================================
spi = spidev.SpiDev()

# SPI0, CE0 / GPIO8
spi.open(0, 0)

spi.max_speed_hz = 100000

# AD7124 = SPI Mode 3
spi.mode = 0b11


# =========================================================
# Helper Functions
# =========================================================
def read_reg(addr, nbytes):
    response = spi.xfer2(
        [0x40 | addr] + [0x00] * nbytes
    )
    return response[1:]


def write_reg(addr, data):
    spi.writebytes([addr] + data)


def bytes_to_int(data):
    value = 0

    for byte in data:
        value = (value << 8) | byte

    return value


# =========================================================
# Reset ADC
# =========================================================
print("Resetting AD7124...")

spi.writebytes([0xFF] * 8)

time.sleep(0.01)


# =========================================================
# Verify SPI Communication
# =========================================================
adc_id = read_reg(REG_ID, 1)

print("AD7124 ID =", [hex(x) for x in adc_id])

if adc_id[0] != 0x17:

    print("ERROR: ADC ID is not 0x17")
    spi.close()
    raise SystemExit

print("SPI communication OK!")
print()


# =========================================================
# Configure ADC
# =========================================================

# Full power
# Continuous conversion
# Internal reference enabled
write_reg(
    REG_ADC_CTRL,
    [0x01, 0x80]
)


# ---------------------------------------------------------
# CHANNEL 0
#
# Gauge 1
# AIN7 - AIN6
# ENABLED
# ---------------------------------------------------------
write_reg(
    REG_CH0,
    [0x80, 0xE6]
)


# ---------------------------------------------------------
# CHANNEL 1
#
# Gauge 2
# AIN5 - AIN4
# ENABLED
# ---------------------------------------------------------
write_reg(
    REG_CH1,
    [0x80, 0xA4]
)


# ---------------------------------------------------------
# SETUP 0
#
# Bipolar
# Input buffers enabled
# Internal reference
# Gain = 128
# ---------------------------------------------------------
write_reg(
    REG_CFG0,
    [0x08, 0x77]
)


# Leave FILTER0 at its default setting for now.

time.sleep(0.1)


# =========================================================
# Register Check
# =========================================================
print("----- REGISTER CHECK -----")

adc_ctrl = bytes_to_int(
    read_reg(REG_ADC_CTRL, 2)
)

ch0 = bytes_to_int(
    read_reg(REG_CH0, 2)
)

ch1 = bytes_to_int(
    read_reg(REG_CH1, 2)
)

cfg0 = bytes_to_int(
    read_reg(REG_CFG0, 2)
)


print(f"ID       = 0x{adc_id[0]:02X}")
print(f"ADC_CTRL = 0x{adc_ctrl:04X}")
print(f"CH0      = 0x{ch0:04X}")
print(f"CH1      = 0x{ch1:04X}")
print(f"CFG0     = 0x{cfg0:04X}")

print("--------------------------")
print()


# =========================================================
# Collect Separate Baselines
# =========================================================
print("Collecting baselines...")
print("DO NOT touch either load cell for about 5 seconds.")
print()


gauge1_baseline_samples = []
gauge2_baseline_samples = []

start_time = time.time()

while time.time() - start_time < 5:

    status = read_reg(REG_STATUS, 1)[0]

    # Bit 7 = RDY
    # RDY = 0 means conversion ready
    if (status & 0x80) == 0:

        # Lower STATUS bits tell us which ADC channel
        # produced the current conversion
        channel = status & 0x0F

        data = read_reg(REG_DATA, 3)

        raw = bytes_to_int(data)

        if channel == 0:

            gauge1_baseline_samples.append(raw)

        elif channel == 1:

            gauge2_baseline_samples.append(raw)

    time.sleep(0.01)


# =========================================================
# Make Sure Both Channels Produced Data
# =========================================================
if len(gauge1_baseline_samples) == 0:

    print("ERROR: No Gauge 1 baseline samples received.")
    spi.close()
    raise SystemExit


if len(gauge2_baseline_samples) == 0:

    print("ERROR: No Gauge 2 baseline samples received.")
    spi.close()
    raise SystemExit


# Calculate average baseline for each gauge
baseline1 = (
    sum(gauge1_baseline_samples)
    / len(gauge1_baseline_samples)
)

baseline2 = (
    sum(gauge2_baseline_samples)
    / len(gauge2_baseline_samples)
)


print(f"Gauge 1 baseline = {baseline1:.0f}")
print(f"Gauge 2 baseline = {baseline2:.0f}")

print()
print("Both gauges are now ZEROED.")
print("Apply force to either/both gauges.")
print()


# =========================================================
# Measurement Settings
# =========================================================

DEADBAND = 1500

latest_gauge1 = 0
latest_gauge2 = 0


# =========================================================
# Read BOTH Gauges
# =========================================================
try:

    while True:

        status = read_reg(REG_STATUS, 1)[0]

        # Conversion ready?
        if (status & 0x80) == 0:

            # Determine which enabled channel
            # generated this sample
            channel = status & 0x0F

            data = read_reg(REG_DATA, 3)

            raw = bytes_to_int(data)


            # -----------------------------------------
            # Gauge 1
            # -----------------------------------------
            if channel == 0:

                # Flip polarity so strain/load
                # normally increases positively
                delta1 = baseline1 - raw

                if abs(delta1) < DEADBAND:
                    delta1 = 0

                latest_gauge1 = delta1


            # -----------------------------------------
            # Gauge 2
            # -----------------------------------------
            elif channel == 1:

                delta2 = baseline2 - raw

                if abs(delta2) < DEADBAND:
                    delta2 = 0

                latest_gauge2 = delta2


            # -----------------------------------------
            # Display both gauges
            # -----------------------------------------
            print(
                f"Gauge 1 = {latest_gauge1:+9.0f}   |   "
                f"Gauge 2 = {latest_gauge2:+9.0f}"
            )

        time.sleep(0.02)


except KeyboardInterrupt:

    print("\nStopping...")


finally:

    spi.close()
