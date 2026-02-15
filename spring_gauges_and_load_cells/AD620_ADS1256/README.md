# ADS1256 + AD620 Load Cell Reader for Raspberry Pi

This is a complete replacement for your HX711-based load cell setup, using higher-precision components:
- **ADS1256**: 24-bit ADC with 8 differential channels (vs HX711's 24-bit 1-channel)
- **AD620**: Precision instrumentation amplifier (vs HX711's built-in amp)

## Quick Start

### 1. Install Dependencies
```bash
./install_dependencies.sh
```

### 2. Enable SPI (if not already enabled)
```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
sudo reboot
```

### 3. Connect Hardware
Follow the wiring diagram in `SETUP_INSTRUCTIONS.md`

### 4. Test Communication
```bash
python3 test_ads1256.py
```
This verifies the ADS1256 is responding correctly.

### 5. Run Load Cell Reader
```bash
python3 ads1256_load_cells.py
```

### 6. Calibrate for Weight Measurements (Optional)
```bash
python3 calibrate_load_cells.py
```
This helps you convert raw ADC values to actual weight in kg.

## Key Differences from HX711 Setup

| Feature | HX711 Setup | ADS1256 + AD620 Setup |
|---------|-------------|----------------------|
| **Interface** | Custom serial protocol | SPI (standard) |
| **Channels** | 1 per chip (need 2 chips) | 8 differential (1 chip) |
| **Sample Rate** | ~80 SPS max | Up to 30,000 SPS |
| **Amplifier** | Built-in, fixed gain | External AD620, adjustable |
| **Precision** | 24-bit | 24-bit |
| **Noise** | Higher | Lower (better components) |
| **Complexity** | Simpler wiring | More complex, better control |
| **Cost** | Lower | Higher |

## Files Included

- **ads1256_load_cells.py** - Main script (replaces your HX711 script)
- **test_ads1256.py** - Test ADS1256 communication
- **calibrate_load_cells.py** - Interactive calibration tool
- **install_dependencies.sh** - Install required packages
- **SETUP_INSTRUCTIONS.md** - Detailed wiring and setup guide
- **README.md** - This file

## Architecture

```
Load Cell 1 ──→ AD620 Board #1 ──→ AIN0 ┐
                                         ├──→ ADS1256 ──SPI──→ Raspberry Pi
Load Cell 2 ──→ AD620 Board #2 ──→ AIN1 ┘
```

### Signal Flow
1. **Load Cell**: Generates tiny voltage change (~mV) when force applied
2. **AD620**: Amplifies signal by 100-1000x (adjustable via potentiometer)
3. **ADS1256**: Converts analog voltage to 24-bit digital value
4. **Raspberry Pi**: Reads digital values via SPI, processes data

## Configuration

In `ads1256_load_cells.py`, you can adjust:

```python
CS_PIN = 22           # Chip Select GPIO
DRDY_PIN = 17         # Data Ready GPIO
CHANNEL_1 = 0         # First load cell (AIN0)
CHANNEL_2 = 1         # Second load cell (AIN1)
DATA_RATE = DRATE_100 # Sample rate (100 SPS)
GAIN = GAIN_1         # ADC gain (usually 1x with AD620)
```

## Troubleshooting

### No readings / "Failed to read during tare"
1. Check SPI is enabled: `lsmod | grep spi`
2. Verify power to ADS1256 and AD620 boards
3. Check all ground connections
4. Run `python3 test_ads1256.py`

### Readings not changing
1. Check load cell is connected to AD620
2. Check AD620 output is connected to ADS1256 AIN0/AIN1
3. Adjust AD620 gain potentiometer (blue trimpot)
4. Verify load cell is working (measure with multimeter)

### Very noisy readings
1. Reduce sample rate: `DATA_RATE = DRATE_10`
2. Add averaging: `SAMPLES_PER_PRINT = 10`
3. Check for loose connections
4. Ensure good power supply (stable 5V)
5. Check grounding

### Wrong channel readings
The ADS1256 has 8 single-ended inputs (AIN0-AIN7):
- If using AIN0 and AIN1: `CHANNEL_1 = 0, CHANNEL_2 = 1`
- If using AIN2 and AIN3: `CHANNEL_1 = 2, CHANNEL_2 = 3`
- etc.

## Pin Reference

### Raspberry Pi GPIO (BCM Numbering)
- GPIO 9 (Pin 21): SPI0 MISO (DOUT)
- GPIO 10 (Pin 19): SPI0 MOSI (DIN)
- GPIO 11 (Pin 23): SPI0 SCLK
- GPIO 22 (Pin 15): CS (configurable)
- GPIO 17 (Pin 11): DRDY (configurable)

### ADS1256 Channels
- AIN0-AIN7: Analog inputs
- AINCOM: Common ground for single-ended mode

## Performance Tips

### For Maximum Speed
```python
DATA_RATE = DRATE_30000  # 30,000 SPS
SAMPLES_PER_PRINT = 1
```

### For Minimum Noise
```python
DATA_RATE = DRATE_10     # 10 SPS
SAMPLES_PER_PRINT = 10
GAIN = GAIN_1            # Lower gain = less noise
```

### For Balanced Performance
```python
DATA_RATE = DRATE_100    # 100 SPS (default)
SAMPLES_PER_PRINT = 5
```

## Next Steps

1. **Get basic readings working** - Run `ads1256_load_cells.py` and verify you see changing values
2. **Adjust AD620 gain** - Turn the blue potentiometers to get good signal levels
3. **Calibrate** - Use `calibrate_load_cells.py` to convert to real weights
4. **Integrate into your project** - Use the ADS1256 class in your own code

## Support

If you encounter issues:
1. Check `SETUP_INSTRUCTIONS.md` for detailed wiring
2. Run `test_ads1256.py` to verify basic communication
3. Check the troubleshooting section above
4. Verify all connections with a multimeter

## License

This code is provided as-is for your use. Based on standard ADS1256 communication protocols.
