import spidev
import time
import statistics

# =========================================================
# SETTINGS  (the knobs that control speed vs. noise)
# =========================================================

# FILTER SPEED.  This is THE setting that decides the sample rate.
#   chip output rate   ODR = 614400 / (32 * FS_WORD)   Hz
#   each channel needs ~4 conversions' worth of settling (sinc4 filter),
#   and we cycle through 2 gauges, so:
#   rate PER GAUGE  ~=  ODR / (4 * 2)  =  2400 / FS_WORD
#
#     FS_WORD = 384  -> ~6 Hz per gauge   (old chip default: way too slow)
#     FS_WORD = 48   -> ~50 Hz per gauge
#     FS_WORD = 30   -> ~80 Hz per gauge
#     FS_WORD = 24   -> ~100 Hz per gauge   <-- target (Hassan: 80-100 Hz)
#
# Smaller FS_WORD = faster but NOISIER (less averaging inside the ADC).
FS_WORD = 24

SPI_SPEED_HZ = 500000   # was 100 kHz. Not the main fix, just extra timing margin
                        # (AD7124 allows up to 5 MHz). If the ID check ever
                        # fails or data gets glitchy, drop this back to 100000.

POLL_DELAY = 0.0005     # was 0.01 / 0.02 s. Must be MUCH shorter than the time
                        # between conversions (~5 ms) or we miss samples.

DISPLAY_PERIOD = 0.25   # Print only 4x per second. Printing every sample
                        # (hundreds per second) slows the loop and drops data.

BASELINE_SECONDS = 5
DEADBAND = 1500         # Counts. Higher FS speed = more noise, so you may need
                        # to raise this. Check the "noise" printed at baseline.


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
REG_FILTER0  = 0x21     # NEW: we now set the filter ourselves


# =========================================================
# SPI Setup
# =========================================================
spi = spidev.SpiDev()

# SPI0, CE0 / GPIO8
spi.open(0, 0)

spi.max_speed_hz = SPI_SPEED_HZ

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


def read_sample():
    """
    Returns (channel, raw_value) if a new conversion is ready, else None.

    CHANGE: we now enable DATA_STATUS in ADC_CONTROL (see below), so a DATA
    read returns 4 bytes = 3 data bytes + a copy of the STATUS byte taken at
    the same moment. The channel number therefore always belongs to THIS data.
    The old code read STATUS and DATA separately. At ~5 ms per conversion a new
    sample can finish between those two reads, which could label a sample with
    the wrong gauge.
    """
    status = read_reg(REG_STATUS, 1)[0]

    # Bit 7 = RDY, active LOW. 1 = nothing new yet.
    if status & 0x80:
        return None

    frame = read_reg(REG_DATA, 4)     # [data_hi, data_mid, data_lo, status]
    raw = bytes_to_int(frame[0:3])
    channel = frame[3] & 0x0F
    return channel, raw


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
# Order changed: channels / config / filter first, ADC_CONTROL LAST.
# Writing ADC_CONTROL (continuous mode) is what starts conversions, so this
# way the ADC never converts with a half-finished setup.
# =========================================================

# ---------------------------------------------------------
# CHANNEL 0  -  Gauge 1  -  AIN7 - AIN6  -  ENABLED
# ---------------------------------------------------------
write_reg(
    REG_CH0,
    [0x80, 0xE6]
)

# ---------------------------------------------------------
# CHANNEL 1  -  Gauge 2  -  AIN5 - AIN4  -  ENABLED
# ---------------------------------------------------------
write_reg(
    REG_CH1,
    [0x80, 0xA4]
)

# ---------------------------------------------------------
# SETUP 0:  Bipolar, input buffers on, internal reference, Gain = 128
# ---------------------------------------------------------
write_reg(
    REG_CFG0,
    [0x08, 0x77]
)

# ---------------------------------------------------------
# FILTER 0   (NEW - THE MAIN FIX)
#
# Before: left at the power-on default (FS = 384 -> ~50 Hz output rate,
#         ~6 Hz per gauge once two channels share it).
# Now:    0x060000 | FS_WORD keeps the same filter type (sinc4) and only
#         changes the speed. FS_WORD = 24 -> 800 Hz output rate.
# ---------------------------------------------------------
write_reg(
    REG_FILTER0,
    [0x06, (FS_WORD >> 8) & 0xFF, FS_WORD & 0xFF]
)

# ---------------------------------------------------------
# ADC_CONTROL = 0x0580
#   bit 10 DATA_STATUS = 1  (NEW: append STATUS byte to every DATA read)
#   bit 8  REF_EN      = 1  internal reference on
#   bits 7:6 = 10           full power
#   bits 5:2 = 0000         continuous conversion
# (old value was 0x0180; only DATA_STATUS was added)
# ---------------------------------------------------------
write_reg(
    REG_ADC_CTRL,
    [0x05, 0x80]
)

time.sleep(0.1)


# =========================================================
# Register Check
# =========================================================
print("----- REGISTER CHECK -----")

adc_ctrl = bytes_to_int(read_reg(REG_ADC_CTRL, 2))
ch0      = bytes_to_int(read_reg(REG_CH0, 2))
ch1      = bytes_to_int(read_reg(REG_CH1, 2))
cfg0     = bytes_to_int(read_reg(REG_CFG0, 2))
filt0    = bytes_to_int(read_reg(REG_FILTER0, 3))

print(f"ID       = 0x{adc_id[0]:02X}")
print(f"ADC_CTRL = 0x{adc_ctrl:04X}   (expect 0x0580)")
print(f"CH0      = 0x{ch0:04X}   (expect 0x80E6)")
print(f"CH1      = 0x{ch1:04X}   (expect 0x80A4)")
print(f"CFG0     = 0x{cfg0:04X}   (expect 0x0877)")
print(f"FILTER0  = 0x{filt0:06X} (expect 0x{0x060000 | FS_WORD:06X})")

print("--------------------------")
print()


# =========================================================
# Collect Separate Baselines
# =========================================================
print("Collecting baselines...")
print("DO NOT touch either load cell for about 5 seconds.")
print()

gauge_baseline_samples = [[], []]     # index 0 = Gauge 1, index 1 = Gauge 2

start_time = time.time()

while time.time() - start_time < BASELINE_SECONDS:

    sample = read_sample()

    if sample is not None:
        channel, raw = sample

        if channel in (0, 1):
            gauge_baseline_samples[channel].append(raw)

    # Was 0.01 s. With a new sample every ~5 ms, waiting 10 ms between polls
    # would skip about half of them.
    time.sleep(POLL_DELAY)


# =========================================================
# Make Sure Both Channels Produced Data
# =========================================================
for i in range(2):
    if len(gauge_baseline_samples[i]) == 0:
        print(f"ERROR: No Gauge {i + 1} baseline samples received.")
        spi.close()
        raise SystemExit

baseline = [
    sum(s) / len(s) for s in gauge_baseline_samples
]

print(f"{'':8}{'baseline':>12}{'noise(std)':>12}{'samples':>9}{'rate':>10}")
for i in range(2):
    samples = gauge_baseline_samples[i]
    noise = statistics.pstdev(samples)
    rate = len(samples) / BASELINE_SECONDS
    print(f"Gauge {i + 1}{baseline[i]:>12.0f}{noise:>12.1f}{len(samples):>9}{rate:>8.1f} Hz")

print()
print("Both gauges are now ZEROED.")
print("(noise = standard deviation in counts. If it is bigger than DEADBAND,")
print(" raise DEADBAND or slow the filter down by raising FS_WORD.)")
print("Apply force to either/both gauges.")
print()


# =========================================================
# Read BOTH Gauges
# =========================================================
latest_gauge = [0, 0]
sample_count = [0, 0]

loop_start = time.time()
last_print = loop_start

try:

    while True:

        sample = read_sample()

        if sample is not None:
            channel, raw = sample

            if channel in (0, 1):

                # Flip polarity so strain/load normally increases positively
                delta = baseline[channel] - raw

                if abs(delta) < DEADBAND:
                    delta = 0

                latest_gauge[channel] = delta
                sample_count[channel] += 1

        # -------------------------------------------------
        # Display (throttled).  We still READ every sample at full speed;
        # we just don't PRINT every one, because printing is slow.
        # The Hz shown is the real measured rate per gauge since start.
        # -------------------------------------------------
        now = time.time()

        if now - last_print >= DISPLAY_PERIOD:
            elapsed = now - loop_start

            print(
                f"Gauge 1 = {latest_gauge[0]:+9.0f} ({sample_count[0] / elapsed:5.1f} Hz)   |   "
                f"Gauge 2 = {latest_gauge[1]:+9.0f} ({sample_count[1] / elapsed:5.1f} Hz)"
            )

            last_print = now

        time.sleep(POLL_DELAY)


except KeyboardInterrupt:

    print("\nStopping...")


finally:

    spi.close()
