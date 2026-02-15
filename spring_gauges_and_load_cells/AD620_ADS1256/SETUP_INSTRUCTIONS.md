# ADS1256 + AD620 Load Cell Setup Instructions

## Hardware Setup

### Components
- 2x Load Cells (strain gauges)
- 2x AD620 Instrumentation Amplifier Boards
- 1x ADS1256 24-bit ADC Board
- 1x Raspberry Pi

### Wiring Connections

#### Load Cells to AD620 Boards
Each load cell connects to one AD620 board:
- **Load Cell Red (E+)** → AD620 board V+
- **Load Cell Black (E-)** → AD620 board GND
- **Load Cell White (S+)** → AD620 board S+
- **Load Cell Green (S-)** → AD620 board S-

#### AD620 Boards to ADS1256
- **AD620 #1 Output** → ADS1256 AIN0
- **AD620 #2 Output** → ADS1256 AIN1
- **AD620 GND** → ADS1256 AGND

#### ADS1256 to Raspberry Pi (SPI Connection)
- **ADS1256 VCC** → Raspberry Pi 5V (Pin 2 or 4)
- **ADS1256 GND** → Raspberry Pi GND (Pin 6, 9, 14, 20, 25, 30, 34, or 39)
- **ADS1256 SCLK** → Raspberry Pi GPIO 11 (Pin 23, SPI0 SCLK)
- **ADS1256 DIN** → Raspberry Pi GPIO 10 (Pin 19, SPI0 MOSI)
- **ADS1256 DOUT** → Raspberry Pi GPIO 9 (Pin 21, SPI0 MISO)
- **ADS1256 CS** → Raspberry Pi GPIO 22 (Pin 15)
- **ADS1256 DRDY** → Raspberry Pi GPIO 17 (Pin 11)

### Power Supply
- Ensure all components share a common ground
- The AD620 boards need power (typically 5V)
- The ADS1256 needs 5V power
- Use a stable power supply for best results

## Software Setup

### 1. Enable SPI on Raspberry Pi
```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
# Reboot: sudo reboot
```

### 2. Install Required Packages
```bash
sudo apt-get update
sudo apt-get install -y python3-spidev python3-rpi.gpio
```

### 3. Verify SPI is Working
```bash
ls /dev/spi*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

### 4. Run the Script
```bash
python3 ads1256_load_cells.py
```

## Configuration Options

In the `main()` function, you can adjust:

```python
CS_PIN = 22           # Chip Select GPIO pin
DRDY_PIN = 17         # Data Ready GPIO pin
CHANNEL_1 = 0         # First load cell on AIN0
CHANNEL_2 = 1         # Second load cell on AIN1
DATA_RATE = DRATE_100 # Sampling rate (100 SPS)
GAIN = GAIN_1         # ADC gain (1x, since AD620 amplifies)
```

### Available Data Rates
- `DRATE_30000` = 30,000 SPS (max speed)
- `DRATE_100` = 100 SPS (good balance)
- `DRATE_10` = 10 SPS (low noise)

### Available Gains
- `GAIN_1` = 1x (recommended when using AD620)
- `GAIN_2` = 2x
- `GAIN_64` = 64x (max)

## Calibration

### AD620 Gain Adjustment
The blue potentiometers (M 103, M 104) on your AD620 boards adjust the amplification:
1. Start with mid-position
2. Apply known weight to load cell
3. Adjust potentiometer to get readable values
4. Typical gain: 100-1000x depending on load cell sensitivity

### Software Taring
The script automatically tares (zeros) both load cells on startup:
- Keep both load cells unloaded during the tare phase
- The script takes 20 samples from each channel
- Tare values are subtracted from subsequent readings

## Troubleshooting

### "Failed to read during tare"
- Check SPI is enabled: `lsmod | grep spi`
- Verify wiring connections
- Check power supply to ADS1256 and AD620 boards
- Ensure common ground between all components

### Readings are zero or unchanging
- Check AD620 output is connected to correct AIN channel
- Verify load cell is properly connected to AD620
- Adjust AD620 gain potentiometers
- Try different ADS1256 channels

### Noisy readings
- Reduce data rate: `DATA_RATE = DRATE_10`
- Increase ADC gain if signal is very small
- Check for proper grounding
- Shield cables if in electrically noisy environment
- Ensure stable power supply

### SPI errors
- Verify SPI is enabled in raspi-config
- Check `/dev/spidev0.0` exists
- Verify GPIO pin numbers match your wiring
- Run with sudo if permission errors

## Expected Output

```
=== TWO LOAD CELLS with AD620 + ADS1256 ===

Configuration:
  CS Pin: GPIO 22
  DRDY Pin: GPIO 17
  Channel 1 (Load Cell 1): AIN0
  Channel 2 (Load Cell 2): AIN1

Calibrating ADC...
Calibration complete.

Taring both load cells... keep unloaded for ~1 second.
Tare1 (AIN0): 154230
Tare2 (AIN1): 162450

Reading load cells... (Ctrl+C to stop)

LC1 (AIN0): 154245 (Δ +15)   |   LC2 (AIN1): 162438 (Δ -12)
LC1 (AIN0): 154892 (Δ +662)  |   LC2 (AIN1): 162401 (Δ -49)
```

## Converting to Physical Units

To convert raw ADC values to weight (kg, lbs), you'll need to calibrate:

1. Record tare value (no load)
2. Apply known weight (e.g., 10 kg)
3. Record loaded value
4. Calculate scale factor: `scale = known_weight / (loaded_value - tare_value)`
5. Multiply delta values by scale factor to get weight

Example calibration code snippet:
```python
# After calibration with known weights
SCALE_FACTOR_1 = 0.000123  # kg per raw unit
SCALE_FACTOR_2 = 0.000119  # kg per raw unit

weight_1_kg = (r1 - tare1) * SCALE_FACTOR_1
weight_2_kg = (r2 - tare2) * SCALE_FACTOR_2
```
