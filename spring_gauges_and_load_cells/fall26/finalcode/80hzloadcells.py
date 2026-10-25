#!/usr/bin/env python3
"""
4-cell load cell test at ~80 Hz PER CELL: AD7124 + Raspberry Pi
(auto-start version: runs unattended from a systemd service at boot)

Wiring (connector P3):  green = Signal(+) = ainp,  white = Signal(-) = ainm
    Load Cell 4: green AIN15, white AIN14
    Load Cell 3: green AIN13, white AIN12
    Load Cell 2: green AIN11, white AIN10
    Load Cell 1: green AIN9,  white AIN8

How the 80 Hz is set:
    ODR = 614400 / (32 * FS_WORD)
    rate per cell ~= ODR / (4 * N) = 4800 / (N * FS_WORD)      (sinc4 settling)
    N = 4 cells, FS_WORD = 15  ->  ODR 1280 Hz  ->  80 Hz per cell

The script MEASURES the real rate and counts missed conversions, so you can
see whether Python is keeping up instead of trusting the formula.

Startup: no keypress needed. After STARTUP_DELAY seconds the script zeroes
itself (all cells must be UNLOADED at power-on), then streams live deltas.

Run by hand:   sudo systemctl stop loadcell && python3 multi_loadcell_80hz.py
Stop:          Ctrl+C (manual) or systemctl stop loadcell (service)
"""

import signal
import statistics
import time

import spidev

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
CHANNELS = [
    {"name": "LoadCell4", "ainp": 15, "ainm": 14},
    {"name": "LoadCell3", "ainp": 13, "ainm": 12},
    {"name": "LoadCell2", "ainp": 11, "ainm": 10},
    {"name": "LoadCell1", "ainp": 9,  "ainm": 8},
]

N = len(CHANNELS)
TARGET_HZ = 80
FS_WORD = round(4800 / (N * TARGET_HZ))   # = 15 for 4 cells at 80 Hz

SPI_SPEED_HZ = 100000     # known-good. If "skipped" below is not ~0, try 500000
POLL_DELAY = 0.0002       # conversions arrive every ~3 ms, so poll much faster than that
STARTUP_DELAY = 10        # seconds after boot to let the ADC and wiring settle
BASELINE_SECONDS = 5
DISPLAY_PERIOD = 0.25
VREF = 2.5
GAIN = 128

# ----------------------------------------------------------------------------
# Registers
# ----------------------------------------------------------------------------
REG_STATUS, REG_ADC_CTRL, REG_DATA, REG_ID = 0x00, 0x01, 0x02, 0x05
REG_CH0, REG_CFG0, REG_FILTER0 = 0x09, 0x19, 0x21

MID = 2 ** 23
UV_PER_COUNT = (VREF / GAIN) / MID * 1e6
EXPECTED_HZ = 4800.0 / (N * FS_WORD)

# ----------------------------------------------------------------------------
# SPI setup + helpers
# ----------------------------------------------------------------------------
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = SPI_SPEED_HZ
spi.mode = 0b11


def _sigterm(signum, frame):
    """systemctl stop sends SIGTERM: turn it into Ctrl+C so 'finally' runs."""
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, _sigterm)


def read_reg(addr, n):
    return spi.xfer2([0x40 | addr] + [0x00] * n)[1:]


def write_reg(addr, data):
    spi.writebytes([addr] + data)


def to_int(b):
    v = 0
    for x in b:
        v = (v << 8) | x
    return v


def chan_value(ainp, ainm):
    return 0x8000 | (ainp << 5) | ainm


def read_sample():
    """(channel_index, raw) or None. DATA_STATUS appends the STATUS byte so the
    channel number always belongs to the data it came with."""
    if read_reg(REG_STATUS, 1)[0] & 0x80:      # RDY active LOW
        return None
    f = read_reg(REG_DATA, 4)
    return f[3] & 0x0F, to_int(f[0:3])


class SkipCounter:
    """Channels come out in order 0,1,2,3,0,1,... A jump means a missed conversion."""
    def __init__(self):
        self.prev = None
        self.skipped = 0
        self.total = 0

    def see(self, ch):
        if ch >= N:
            return
        if self.prev is not None and ch != (self.prev + 1) % N:
            self.skipped += 1
        self.prev = ch
        self.total += 1


# ----------------------------------------------------------------------------
# 1) Reset + ID
# ----------------------------------------------------------------------------
print("Resetting AD7124...")
spi.writebytes([0xFF] * 8)
time.sleep(0.01)
adc_id = read_reg(REG_ID, 1)[0]
print(f"AD7124 ID = {adc_id:#04x}")
if (adc_id & 0xF0) != 0x10:
    print("ERROR: no valid ADC response (0x00 / 0xFF = chip not answering).")
    spi.close()
    raise SystemExit(1)          # non-zero so systemd restarts us
print("SPI communication OK.\n")

# ----------------------------------------------------------------------------
# 2) Configure (ADC_CONTROL last, it starts conversions)
# ----------------------------------------------------------------------------
write_reg(REG_CFG0, [0x08, 0x77])       # bipolar, buffers on, internal ref, gain 128
write_reg(REG_FILTER0, [0x06, (FS_WORD >> 8) & 0xFF, FS_WORD & 0xFF])
for i, ch in enumerate(CHANNELS):
    v = chan_value(ch["ainp"], ch["ainm"])
    write_reg(REG_CH0 + i, [(v >> 8) & 0xFF, v & 0xFF])
write_reg(REG_ADC_CTRL, [0x05, 0x80])   # DATA_STATUS on, ref on, full power, continuous
time.sleep(0.1)

# ----------------------------------------------------------------------------
# 3) Register readback
# ----------------------------------------------------------------------------
print("----- REGISTER CHECK -----")
all_ok = True
for name, addr, n, expected in [
    ("ADC_CTRL", REG_ADC_CTRL, 2, 0x0580),
    ("CFG0", REG_CFG0, 2, 0x0877),
    ("FILTER0", REG_FILTER0, 3, 0x060000 | FS_WORD),
]:
    actual = to_int(read_reg(addr, n))
    ok = actual == expected
    all_ok &= ok
    print(f"{name:<10}= 0x{actual:0{n * 2}X}  (expect 0x{expected:0{n * 2}X})  "
          f"{'OK' if ok else 'MISMATCH!'}")
for i, ch in enumerate(CHANNELS):
    expected = chan_value(ch["ainp"], ch["ainm"])
    actual = to_int(read_reg(REG_CH0 + i, 2))
    ok = actual == expected
    all_ok &= ok
    print(f"CH{i} {ch['name']:<10}= 0x{actual:04X}  (expect 0x{expected:04X})  "
          f"{'OK' if ok else 'MISMATCH!'}")
print(f"Expected rate: ~{EXPECTED_HZ:.0f} Hz per cell (FS_WORD = {FS_WORD}, "
      f"ODR = {614400 / (32 * FS_WORD):.0f} Hz)")
print("--------------------------\n")
if not all_ok:
    print("WARNING: a register did not take its value. Link may be unstable.\n")

# ----------------------------------------------------------------------------
# 4) Baseline (automatic, no keypress)
# ----------------------------------------------------------------------------
print(f"Auto-zeroing in {STARTUP_DELAY} s. Keep all cells unloaded...")
time.sleep(STARTUP_DELAY)
print(f"Collecting baselines for {BASELINE_SECONDS} s...\n")

samples = {i: [] for i in range(N)}
skips = SkipCounter()
t_end = time.time() + BASELINE_SECONDS
while time.time() < t_end:
    s = read_sample()
    if s is not None and s[0] in samples:
        samples[s[0]].append(s[1])
        skips.see(s[0])
    time.sleep(POLL_DELAY)

baseline = {}
print(f"{'cell':<11}{'AINp-AINm':<12}{'rate Hz':>8}{'offset mV':>11}{'noise uV':>10}  verdict")
for i, ch in enumerate(CHANNELS):
    s = samples[i]
    pair = f"AIN{ch['ainp']}-AIN{ch['ainm']}"
    rate = len(s) / BASELINE_SECONDS
    if len(s) < 5:
        print(f"{ch['name']:<11}{pair:<12}{rate:>8.1f}  NO DATA: channel not converting")
        continue
    mean, sd = statistics.mean(s), statistics.pstdev(s)
    baseline[i] = mean
    off_mv = (mean - MID) * UV_PER_COUNT / 1000
    noise_uv = sd * UV_PER_COUNT
    if abs(mean - MID) > 0.95 * MID:
        verdict = "RAILED: open signal wire or no excitation"
    elif noise_uv > 50:
        verdict = "VERY NOISY: floating input or loose wire"
    elif abs(off_mv) > 15:
        verdict = "large offset: bridge unbalanced or a leg badly wired"
    else:
        verdict = "ok"
    print(f"{ch['name']:<11}{pair:<12}{rate:>8.1f}{off_mv:>+11.3f}{noise_uv:>10.2f}  {verdict}")

print(f"\nMeasured rate: ~{min(len(samples[i]) for i in range(N)) / BASELINE_SECONDS:.0f} Hz per cell "
      f"(target {TARGET_HZ}).  Skipped conversions: {skips.skipped} of {skips.total}.")
if skips.total and skips.skipped > 0.01 * skips.total:
    print("  -> Python is missing conversions. Raise SPI_SPEED_HZ to 500000, or raise FS_WORD.")

if len(baseline) < N:
    print("\nSome channels produced no data. Fix those before continuing.")
    spi.close()
    raise SystemExit(1)          # non-zero so systemd restarts us

# ----------------------------------------------------------------------------
# 5) Live display
# ----------------------------------------------------------------------------
print("\nLive deltas in microvolts. Press ONE cell at a time: only its column should move.")
print("Positive = raw above baseline. Ctrl+C to stop.\n")
print("".join(f"{ch['name']:>14}" for ch in CHANNELS))

latest = dict(baseline)
skips = SkipCounter()
rows = 0
t0 = time.monotonic()
last_print = t0
try:
    while True:
        s = read_sample()
        if s is not None and s[0] in latest:
            latest[s[0]] = s[1]
            skips.see(s[0])
            if s[0] == N - 1:
                rows += 1          # one full sweep = one sample per cell
        now = time.monotonic()
        if now - last_print >= DISPLAY_PERIOD:
            print("".join(f"{(latest[i] - baseline[i]) * UV_PER_COUNT:>+12.1f}uV"
                          for i in range(N)))
            last_print = now
        time.sleep(POLL_DELAY)
except KeyboardInterrupt:
    print("\nStopping...")
finally:
    spi.close()
    elapsed = time.monotonic() - t0
    if elapsed > 0:
        print(f"Measured: ~{rows / elapsed:.1f} Hz per cell over {elapsed:.0f} s, "
              f"skipped conversions: {skips.skipped} of {skips.total}")
