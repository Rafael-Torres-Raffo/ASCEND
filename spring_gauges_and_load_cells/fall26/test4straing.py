#!/usr/bin/env python3
"""
ASCEND - 4-channel strain gauge reader / logger
Raspberry Pi  <--SPI-->  AD7124

What this script does
  1. Resets the AD7124 and verifies SPI communication (reads the ID register)
  2. Configures 4 differential channels (one per gauge / Wheatstone bridge)
  3. Zeroes ("tares") every gauge with a baseline average, and prints the noise
  4. Streams readings to the terminal AND logs them to a timestamped CSV
  5. Lets you type event notes (e.g. "wheel turn") while logging; they land in the CSV

Run:    python3 strain_gauge_4ch_logger.py
Stop:   Ctrl+C   (the CSV is flushed every row, so nothing is lost)
"""

import csv
import os
import select
import statistics
import sys
import time
from datetime import datetime

import spidev


# =============================================================================
# 1) USER SETTINGS  -- the things you will actually want to edit
# =============================================================================

# One entry per physical strain gauge / bridge.
#   name : used as the CSV column label. RENAME these to the physical location
#          (e.g. "front_left_strut") so the data is self-explanatory later.
#   ainp : AD7124 input pin wired to the bridge's OUT+  (positive signal)
#   ainm : AD7124 input pin wired to the bridge's OUT-  (negative signal)
#   sign : +1 or -1. Flips the direction of the reading. Your original code used
#          "baseline - raw", which is sign = -1. After you apply a known load
#          (Project Step 3.4) and find a gauge reads backwards, flip its sign here.
#
# The ORDER of this list matters: list position = channel number = the CHANNEL
# register that gets used (index 0 -> CHANNEL_0, index 1 -> CHANNEL_1, ...).
CHANNELS = [
    {"name": "Gauge1", "ainp": 7, "ainm": 6, "sign": -1},   # AIN7 - AIN6 (existing)
    {"name": "Gauge2", "ainp": 5, "ainm": 4, "sign": -1},   # AIN5 - AIN4 (existing)
    {"name": "Gauge3", "ainp": 3, "ainm": 2, "sign": -1},   # AIN3 - AIN2 (NEW)
    {"name": "Gauge4", "ainp": 1, "ainm": 0, "sign": -1},   # AIN1 - AIN0 (NEW)
]

BASELINE_SECONDS = 10     # How long to average for zeroing. More channels = fewer
                          # samples per channel per second, so we use 10 s not 5 s.

DISPLAY_DEADBAND = 1500   # Counts. Readings smaller than this show as 0 ON SCREEN ONLY.
                          # The CSV always stores the real, unmodified numbers.

# --- Filter speed vs noise --------------------------------------------------
# FS_WORD sets the digital filter. Output data rate (per conversion) is
#       ODR = 614400 / (32 * FS_WORD)   Hz   (full-power mode, internal clock)
# 384 is the chip's power-on default (~50 Hz) -> same behavior as your old code.
# SMALLER FS_WORD = FASTER readings but MORE NOISE. LARGER = slower but quieter.
# With 4 channels being cycled, each gauge gets only a fraction of that ODR,
# so if the logged rate is too slow for vehicle testing, try FS_WORD = 96 or 48.
FS_WORD = 384

# --- Electrical constants used for converting counts -> microvolts ----------
VREF = 2.5                # Internal reference voltage (volts)
GAIN = 128                # Must match the PGA bits written to CONFIG_0 below

LOG_DIR = "strain_logs"   # Folder (created next to this script's working dir)


# =============================================================================
# 2) AD7124 REGISTER ADDRESSES (from the datasheet register map)
# =============================================================================
REG_STATUS   = 0x00   # 8-bit  : RDY flag (bit 7, active LOW) + active channel (bits 3:0)
REG_ADC_CTRL = 0x01   # 16-bit : power mode, conversion mode, reference on/off, etc.
REG_DATA     = 0x02   # 24-bit : the conversion result (+ optional status byte, see below)
REG_ID       = 0x05   # 8-bit  : chip ID, used to prove SPI is working

REG_CH0      = 0x09   # 16-bit : CHANNEL_0.  CHANNEL_n is at address 0x09 + n
REG_CFG0     = 0x19   # 16-bit : CONFIG_0 (gain, bipolar, reference, buffers)
REG_FILTER0  = 0x21   # 24-bit : FILTER_0 (filter type + FS word)

ADC_FULL_SCALE_MID = 2 ** 23   # In bipolar mode, 0V input reads as 0x800000 (8,388,608)

# Volts represented by ONE ADC count at our gain/reference:
#   full scale is +/-(VREF/GAIN) spread over 2^23 counts on each side
VOLTS_PER_COUNT = (VREF / GAIN) / ADC_FULL_SCALE_MID


# =============================================================================
# 3) SPI SETUP
# =============================================================================
spi = spidev.SpiDev()
spi.open(0, 0)             # SPI bus 0, chip-select 0 (GPIO8 / CE0)
spi.max_speed_hz = 100000  # 100 kHz is slow but very robust (good for long wires)
spi.mode = 0b11            # AD7124 requires SPI MODE 3 (CPOL=1, CPHA=1)


# =============================================================================
# 4) LOW-LEVEL HELPERS
# =============================================================================
def read_reg(addr, nbytes):
    """
    Read `nbytes` from register `addr`.

    Every AD7124 transaction starts with a 'communications byte':
        bit 7   = WEN  (must be 0)
        bit 6   = R/W  (1 = READ, 0 = WRITE)
        bits5:0 = register address
    So a read command is 0x40 | addr. We then clock out `nbytes` dummy zeros;
    the chip's answer comes back DURING those dummy bytes. The very first byte
    we receive was clocked in while we were still sending the command, so it is
    meaningless -> we drop it with [1:].
    """
    response = spi.xfer2([0x40 | addr] + [0x00] * nbytes)
    return response[1:]


def write_reg(addr, data):
    """Write a list of bytes (MOST significant byte first) to register `addr`.
    R/W bit is 0 here, so the comms byte is just the address."""
    spi.writebytes([addr] + data)


def bytes_to_int(data):
    """Combine bytes (MSB first) into one integer: [0x80, 0xE6] -> 0x80E6."""
    value = 0
    for byte in data:
        value = (value << 8) | byte
    return value


def channel_register_value(ainp, ainm):
    """
    Build the 16-bit CHANNEL register value.
        bit 15     ENABLE  = 1  (include this channel in the sequence)
        bits 14:12 SETUP   = 0  (use CONFIG_0 / FILTER_0 for this channel)
        bits 9:5   AINP    = positive input pin number
        bits 4:0   AINM    = negative input pin number
    Example: AIN7-AIN6 -> 0x8000 | (7<<5) | 6 = 0x80E6  (matches your old code)
    """
    return 0x8000 | (ainp << 5) | ainm


def read_sample():
    """
    Try to read one conversion. Returns (channel_index, raw_24bit) or None.

    How it works:
      * STATUS bit 7 is RDY and is ACTIVE LOW: 0 means "new data is ready".
      * We turned on DATA_STATUS in ADC_CONTROL, so reading DATA returns
        4 bytes: 3 data bytes followed by a copy of the STATUS byte.
        That status byte was captured WITH the sample, so the channel number
        we get is guaranteed to belong to this exact data. (Your old code read
        STATUS and DATA separately, which could in theory mislabel a sample if
        a new conversion finished in between.)
    """
    status = read_reg(REG_STATUS, 1)[0]
    if status & 0x80:                 # RDY = 1 -> no new conversion yet
        return None

    frame = read_reg(REG_DATA, 4)     # [data_hi, data_mid, data_lo, status]
    raw = bytes_to_int(frame[0:3])    # 24-bit conversion result
    channel = frame[3] & 0x0F         # lower 4 bits = which channel made this sample
    return channel, raw


def check_for_event():
    """
    Non-blocking check for a typed note. If you type text and press Enter while
    the script runs, it's returned (and gets written in the CSV 'event' column).
    Pressing Enter on an empty line logs the word MARK.
    """
    if select.select([sys.stdin], [], [], 0)[0]:
        text = sys.stdin.readline().strip()
        return text if text else "MARK"
    return ""


# =============================================================================
# 5) RESET AND VERIFY COMMUNICATION
# =============================================================================
print("Resetting AD7124...")
# Holding DIN high for 64+ clock cycles = reset. 8 bytes x 8 bits = 64 ones.
spi.writebytes([0xFF] * 8)
time.sleep(0.01)

adc_id = read_reg(REG_ID, 1)
print("AD7124 ID =", [hex(x) for x in adc_id])

# Upper nibble = which AD7124 variant, lower nibble = silicon revision.
# If this fails, the problem is SPI wiring / mode / power -- NOT the gauges.
if adc_id[0] != 0x17:
    print("ERROR: ADC ID is not 0x17 -> check SPI wires, power, ground, SPI mode.")
    spi.close()
    raise SystemExit
print("SPI communication OK!\n")


# =============================================================================
# 6) CONFIGURE THE ADC
#    Order matters: set up channels/config/filter FIRST, then write ADC_CONTROL
#    LAST. Writing ADC_CONTROL in continuous mode is what starts conversions,
#    so this way the ADC never converts with a half-finished configuration.
# =============================================================================

# --- CONFIG_0 = 0x0877 -------------------------------------------------------
#   bit 11    BIPOLAR = 1    -> reads +/- voltage (0 V input = 0x800000)
#   bits 6,5  AIN buffers on -> high input impedance so we don't load the bridge
#   bits 4:3  REF_SEL = 10   -> use the INTERNAL 2.5 V reference
#   bits 2:0  PGA = 111      -> gain = 128 (amplifies the mV bridge signal)
# At gain 128 and 2.5 V ref, full scale is only about +/-19.5 mV. That is fine
# for a bridge but means the bridge must be well balanced to avoid railing.
write_reg(REG_CFG0, [0x08, 0x77])

# --- FILTER_0 ----------------------------------------------------------------
# 0x060000 | FS_WORD keeps the default filter type (sinc4) and only changes the
# speed. With FS_WORD = 384 this equals the chip's default 0x060180.
write_reg(REG_FILTER0, [0x06, (FS_WORD >> 8) & 0xFF, FS_WORD & 0xFF])

# --- CHANNEL registers (one per gauge) --------------------------------------
for index, ch in enumerate(CHANNELS):
    value = channel_register_value(ch["ainp"], ch["ainm"])
    write_reg(REG_CH0 + index, [(value >> 8) & 0xFF, value & 0xFF])

# --- ADC_CONTROL = 0x0580 (written LAST) ------------------------------------
#   bit 10    DATA_STATUS = 1 -> append the STATUS byte to every DATA read
#   bit 8     REF_EN = 1      -> turn on the internal reference
#   bits 7:6  POWER_MODE = 10 -> full power
#   bits 5:2  MODE = 0000     -> continuous conversion (sequencer cycles through
#                                all enabled channels automatically)
#   bits 1:0  CLK_SEL = 00    -> internal clock
write_reg(REG_ADC_CTRL, [0x05, 0x80])

time.sleep(0.1)

# --- Read everything back so we KNOW the chip took our settings -------------
print("----- REGISTER CHECK -----")
print(f"ADC_CTRL = 0x{bytes_to_int(read_reg(REG_ADC_CTRL, 2)):04X}  (expect 0x0580)")
print(f"CFG0     = 0x{bytes_to_int(read_reg(REG_CFG0, 2)):04X}  (expect 0x0877)")
for index, ch in enumerate(CHANNELS):
    expected = channel_register_value(ch["ainp"], ch["ainm"])
    actual = bytes_to_int(read_reg(REG_CH0 + index, 2))
    flag = "OK" if actual == expected else "MISMATCH!"
    print(f"CH{index} {ch['name']:<8} = 0x{actual:04X}  (expect 0x{expected:04X}) {flag}")
print("--------------------------\n")


# =============================================================================
# 7) BASELINE (ZEROING)
#    Each bridge has a small static offset even with no load (resistor
#    tolerances, wiring, etc.). We average readings while UNLOADED and
#    subtract that average later, so "0" means "no load".
# =============================================================================
N = len(CHANNELS)

input("Make sure NOTHING is loading the gauges, then press Enter to zero... ")
print(f"Collecting baselines for {BASELINE_SECONDS} s. Do not touch anything.\n")

baseline_samples = {i: [] for i in range(N)}
start = time.time()
while time.time() - start < BASELINE_SECONDS:
    sample = read_sample()
    if sample is not None:
        channel, raw = sample
        if channel in baseline_samples:       # ignore anything unexpected
            baseline_samples[channel].append(raw)
    time.sleep(0.01)

# Every gauge must have produced data, otherwise we stop and say WHICH one.
for i, ch in enumerate(CHANNELS):
    if len(baseline_samples[i]) == 0:
        print(f"ERROR: no samples from {ch['name']} (AIN{ch['ainp']}-AIN{ch['ainm']}).")
        print("       Check that channel's wiring and register settings.")
        spi.close()
        raise SystemExit

baseline = {}
print(f"{'Gauge':<10}{'baseline':>12}{'noise (std)':>14}{'noise uV':>10}{'samples':>9}")
for i, ch in enumerate(CHANNELS):
    samples = baseline_samples[i]
    baseline[i] = sum(samples) / len(samples)

    # Standard deviation of the unloaded signal = how noisy this gauge is.
    # Use it to judge whether a real load will stand out from the noise
    # (Project Step 3.5: identify excessive noise or unstable readings).
    noise = statistics.pstdev(samples) if len(samples) > 1 else 0.0

    note = ""
    # A balanced bridge reads near 0x800000 (8,388,608). If it sits way off
    # toward 0 or 16,777,215 the input is railed: usually a missing connection,
    # a swapped wire, or a bridge that is badly unbalanced.
    if abs(baseline[i] - ADC_FULL_SCALE_MID) > 0.95 * ADC_FULL_SCALE_MID:
        note = "  <-- WARNING: near rail, check wiring!"
    print(f"{ch['name']:<10}{baseline[i]:>12.0f}{noise:>14.1f}"
          f"{noise * VOLTS_PER_COUNT * 1e6:>10.2f}{len(samples):>9}{note}")

print("\nAll gauges ZEROED.\n")


# =============================================================================
# 8) OPEN THE CSV LOG
# =============================================================================
os.makedirs(LOG_DIR, exist_ok=True)
filename = os.path.join(LOG_DIR, datetime.now().strftime("strain_%Y%m%d_%H%M%S.csv"))
csv_file = open(filename, "w", newline="")
writer = csv.writer(csv_file)

# For each gauge we store:
#   _raw   : the unmodified 24-bit ADC count
#   _delta : (raw - baseline) * sign, in counts  (0 = unloaded)
#   _uV    : delta converted to microvolts at the ADC input
header = ["timestamp_iso", "elapsed_s", "event"]
for ch in CHANNELS:
    header += [f"{ch['name']}_raw", f"{ch['name']}_delta", f"{ch['name']}_uV"]
writer.writerow(header)

print(f"Logging to: {filename}")
print("Type a note + Enter at any time to mark an event (Enter alone = MARK).")
print("Ctrl+C to stop.\n")


# =============================================================================
# 9) MAIN LOOP
#    The sequencer returns one channel per conversion. We keep the newest raw
#    value for each gauge and write ONE csv row each time all N gauges have
#    reported a fresh value ("a sweep"). Because the channels are sampled one
#    after another, the values in a row are a few tens of ms apart, and the
#    row timestamp is when the LAST gauge of that sweep finished.
# =============================================================================
latest_raw = {}                 # channel -> newest raw count
fresh = set()                   # channels updated since the last row was written
pending_event = ""              # typed note waiting for the next row
t0 = time.monotonic()           # monotonic clock for elapsed time (immune to clock changes)
last_sweep_time = t0

try:
    while True:
        # Collect any note the user typed.
        note = check_for_event()
        if note:
            pending_event = (pending_event + " | " + note) if pending_event else note

        sample = read_sample()
        if sample is not None:
            channel, raw = sample
            if channel < N:
                latest_raw[channel] = raw
                fresh.add(channel)

            # A full sweep is complete: log it and show it.
            if len(fresh) == N:
                now_mono = time.monotonic()
                elapsed = now_mono - t0
                sweep_hz = 1.0 / (now_mono - last_sweep_time) if now_mono > last_sweep_time else 0.0
                last_sweep_time = now_mono

                row = [datetime.now().isoformat(timespec="milliseconds"),
                       f"{elapsed:.3f}", pending_event]
                screen = f"{elapsed:8.2f}s "

                for i, ch in enumerate(CHANNELS):
                    delta = (latest_raw[i] - baseline[i]) * ch["sign"]
                    microvolts = delta * VOLTS_PER_COUNT * 1e6
                    row += [latest_raw[i], f"{delta:.1f}", f"{microvolts:.3f}"]

                    # Deadband is cosmetic: only affects what is PRINTED.
                    shown = 0 if abs(delta) < DISPLAY_DEADBAND else delta
                    screen += f"| {ch['name']} {shown:+9.0f} "

                writer.writerow(row)
                csv_file.flush()            # write to disk now so a crash/power loss loses nothing

                print(screen + f"| {sweep_hz:4.1f} Hz" + (f"  <-- {pending_event}" if pending_event else ""))

                pending_event = ""
                fresh.clear()

        time.sleep(0.005)

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    csv_file.close()
    spi.close()
    print(f"Log saved: {filename}")
